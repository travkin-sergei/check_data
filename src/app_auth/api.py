# src/app_auth/api.py
from typing import List
from fastapi import APIRouter, Response, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from src.app_auth.models import User, AppCredential
from src.app_auth.utils import authenticate_user, set_tokens, generate_app_token, hash_app_token, get_password_hash
from src.app_auth.dao import UsersDAO, AppCredentialDAO
from src.app_auth.exceptions import UserAlreadyExistsException, IncorrectEmailOrPasswordException
from src.app_auth.dependencies import (
    get_current_user, get_current_admin_user, check_refresh_token,
    get_session_with_commit, get_session_without_commit, require_app_token
)
from src.app_auth.schemas import (
    SUserRegister, SUserAuth, EmailModel, SUserAddDB, SUserInfo,
    SAppCredentialCreate, SAppCredentialResponse, SAppCredentialList
)
from src.config.logger import logger
from src.app_auth.config import settings

router = APIRouter(tags=["APP Auth"])


@router.post("/register/", summary="Регистрация пользователя")
async def register_user(user_data: SUserRegister, session: AsyncSession = Depends(get_session_with_commit)):
    if await UsersDAO(session).find_one_or_none(filters=EmailModel(email=user_data.email)):
        raise UserAlreadyExistsException
    await UsersDAO(session).add(values=SUserAddDB(**user_data.model_dump()))
    return {"message": "Вы успешно зарегистрированы!"}


@router.post("/login/", summary="Авторизация")
async def auth_user(response: Response, user_data: SUserAuth,
                    session: AsyncSession = Depends(get_session_without_commit)):
    # 1. Пробуем локальную БД
    user = await UsersDAO(session).find_one_or_none(filters=EmailModel(email=user_data.email))
    if user and await authenticate_user(user=user, password=user_data.password):
        set_tokens(response, user.id)
        return {"ok": True, "message": "Авторизация успешна (локальная)"}

    # 2. Если локально не найден или пароль не подошёл — пробуем внешний SSO
    if settings.SSO_ENABLED:
        from src.app_auth.sso_client import SSOClient
        sso = SSOClient()
        success, sso_token, sso_user_info = await sso.authenticate_user(
            username=user_data.email,
            password=user_data.password
        )
        if success:
            local_user = await UsersDAO(session).find_one_or_none(filters=EmailModel(email=user_data.email))
            if not local_user:
                import secrets
                random_password = secrets.token_urlsafe(32)
                hashed = get_password_hash(random_password)
                new_user = User(
                    email=user_data.email,
                    phone_number=sso_user_info.get('phone', '+70000000000'),
                    first_name=sso_user_info.get('first_name', 'SSO'),
                    last_name=sso_user_info.get('last_name', 'User'),
                    password=hashed,
                    role_id=1
                )
                session.add(new_user)
                await session.flush()
                local_user = new_user
                logger.info(f"[AUTH] Создан новый пользователь через SSO: {user_data.email}")
            set_tokens(response, local_user.id)
            return {"ok": True, "message": "Авторизация успешна (SSO)"}

    raise IncorrectEmailOrPasswordException


@router.post("/logout", summary="Выход из системы")
async def logout(response: Response):
    response.delete_cookie("user_access_token")
    response.delete_cookie("user_refresh_token")
    return {"message": "Пользователь успешно вышел из системы"}


@router.get("/me/", summary="Получить данные текущего пользователя")
async def get_me(user_data: User = Depends(get_current_user)) -> SUserInfo:
    return SUserInfo.model_validate(user_data)


@router.get("/all_users/", summary="Список всех пользователей (только админ)")
async def get_all_users(session: AsyncSession = Depends(get_session_with_commit),
                        _: User = Depends(get_current_admin_user)) -> List[SUserInfo]:
    return await UsersDAO(session).find_all()


@router.post("/refresh", summary="Обновление токенов")
async def process_refresh_token(response: Response, user: User = Depends(check_refresh_token)):
    set_tokens(response, user.id)
    return {"message": "Токены успешно обновлены"}


@router.get("/service/shared-data/")
async def get_shared_data(
        user: User | None = Depends(get_current_user),
        app_token: str | None = Depends(require_app_token)
):
    if not user and not app_token:
        raise HTTPException(status_code=401, detail="Требуется авторизация (JWT cookie или Bearer token)")
    auth_type = "user" if user else "app"
    return {"message": "Доступ разрешён", "auth_type": auth_type}


@router.post(
    "/service/register-app/",
    response_model=SAppCredentialResponse,
    summary="Зарегистрировать новое приложение и выдать токен",
    description="Только для администраторов. Возвращает токен ОДИН РАЗ — сохраните его!"
)
async def register_app(app_data: SAppCredentialCreate,
                       current_admin: User = Depends(get_current_admin_user),
                       session: AsyncSession = Depends(get_session_with_commit)) -> SAppCredentialResponse:
    existing = await AppCredentialDAO(session).find_by_app_name(app_data.app_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Приложение '{app_data.app_name}' уже зарегистрировано"
        )
    raw_token = generate_app_token()
    token_hash = await hash_app_token(raw_token)
    new_cred = AppCredential(
        app_name=app_data.app_name,
        app_description=app_data.app_description,
        token_hash=token_hash,
        is_active=True,
        created_by=current_admin.id
    )
    session.add(new_cred)
    await session.flush()
    logger.info(f"[AUTH] Зарегистрировано приложение: {app_data.app_name} (создатель: {current_admin.email})")
    return SAppCredentialResponse(
        success=True,
        message=f"Приложение '{app_data.app_name}' зарегистрировано. Токен показан один раз!",
        app_name=app_data.app_name,
        app_token=raw_token,
        created_at=new_cred.created_at,
        created_by=current_admin.email
    )


@router.get(
    "/service/apps/",
    response_model=List[SAppCredentialList],
    summary="Список зарегистрированных приложений (только админ)",
    description="Возвращает публичную информацию БЕЗ токенов"
)
async def list_registered_apps(current_admin: User = Depends(get_current_admin_user),
                               session: AsyncSession = Depends(get_session_without_commit)) -> List[SAppCredentialList]:
    creds = await AppCredentialDAO(session).find_all()
    result = []
    for cred in creds:
        creator_email = cred.creator.email if cred.creator else "unknown"
        result.append(SAppCredentialList(
            id=cred.id,
            app_name=cred.app_name,
            app_description=cred.app_description,
            is_active=cred.is_active,
            created_at=cred.created_at,
            created_by=creator_email
        ))
    return result


@router.post(
    "/service/apps/{app_name}/get-temporary-token/",
    summary="Получить временный токен (1 час) для межсервисного взаимодействия",
    description="Генерирует JWT токен со сроком жизни 1 час для обращения к другим сервисам."
)
async def get_temporary_token(
        app_name: str,
        current_admin: User = Depends(get_current_admin_user),
        session: AsyncSession = Depends(get_session_without_commit)
):
    """Выдаёт временный JWT токен для приложения."""
    from src.app_auth.dependencies import get_app_token_for_service
    
    jwt_token = await get_app_token_for_service(app_name, session)
    
    return {
        "success": True,
        "app_name": app_name,
        "token_type": "Bearer",
        "access_token": jwt_token,
        "expires_in": 3600  # 1 час в секундах
    }


@router.post(
    "/service/verify-token/",
    summary="Проверить токен приложения (для внутреннего использования)",
    description="Используется другими сервисами для валидации токенов."
)
async def verify_app_token(
        app_token: str = Depends(require_app_token)
):
    logger.debug("[AUTH] Запрос верификации токена успешен")
    return {"valid": True, "message": "Токен действителен"}


@router.post("/sso/exchange-token/")
async def exchange_sso_token(
        response: Response,
        sso_token: str = Header(..., alias="X-SSO-Token"),
        session: AsyncSession = Depends(get_session_without_commit)
):
    """Обменивает валидный внешний SSO-токен на внутренние JWT."""
    if not settings.SSO_ENABLED:
        raise HTTPException(status_code=503, detail="SSO не настроен")

    from src.app_auth.sso_client import SSOClient
    sso = SSOClient()
    if not await sso.validate_token(sso_token):
        raise HTTPException(status_code=401, detail="Недействительный SSO-токен")

    # В реальном проекте извлеките user_id из токена SSO
    # Здесь для примера ищем фиксированного пользователя
    user = await UsersDAO(session).find_one_or_none(filters=EmailModel(email="sso_user@example.com"))
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    set_tokens(response, user.id)
    return {"message": "Токены выпущены"}


@router.post("/service/apps/{app_name}/rotate-token/")
async def rotate_app_token(
        app_name: str,
        ttl_days: int = 365,
        current_admin: User = Depends(get_current_admin_user),
        session: AsyncSession = Depends(get_session_with_commit)
):
    """Генерирует новый токен для приложения. Старый токен деактивируется."""
    cred = await AppCredentialDAO(session).find_by_app_name(app_name)
    if not cred:
        raise HTTPException(status_code=404, detail="Приложение не найдено")

    # Генерируем новый токен
    raw_token = generate_app_token()
    token_hash = await hash_app_token(raw_token)

    # Обновляем запись
    cred.token_hash = token_hash
    cred.expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    cred.is_active = True
    await session.flush()

    logger.info(f"Токен приложения '{app_name}' обновлён администратором {current_admin.email}")

    return {
        "success": True,
        "message": f"Токен для '{app_name}' обновлён. Новый токен показан один раз!",
        "app_name": app_name,
        "app_token": raw_token,
        "expires_at": cred.expires_at.isoformat()
    }
