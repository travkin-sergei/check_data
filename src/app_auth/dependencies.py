import re
from datetime import datetime, timezone
from jose import jwt, JWTError, ExpiredSignatureError
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Header, HTTPException, status, Depends, Request

from src.config.logger import logger
from src.app_database.session import get_session_factory
from src.app_auth.config import settings
from src.app_auth.dao import UsersDAO, AppCredentialDAO  # ← Добавлен AppCredentialDAO
from src.app_auth.models import User
from src.app_auth.exceptions import (
    TokenNoFound, NoJwtException, TokenExpiredException,
    NoUserIdException, ForbiddenException, UserNotFoundException
)


# === Сессии БД ===
async def get_session_with_commit() -> AsyncGenerator[AsyncSession, None]:
    """Сессия с авто-коммитом и установленным search_path."""
    factory = get_session_factory(settings.DB_ALIAS)
    async with factory() as session:
        try:
            await session.execute(text(f"SET LOCAL search_path TO {settings.APP_NAME}, public"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session_without_commit() -> AsyncGenerator[AsyncSession, None]:
    """Сессия только для чтения с search_path."""
    factory = get_session_factory(settings.DB_ALIAS)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {settings.APP_NAME}, public"))
        yield session


# === Авторизация пользователей (JWT + Cookies) ===
def get_access_token(request: Request) -> str:
    token = request.cookies.get('user_access_token')
    if not token:
        raise TokenNoFound
    return token


def get_refresh_token(request: Request) -> str:
    token = request.cookies.get('user_refresh_token')
    if not token:
        raise TokenNoFound
    return token


def _normalize_user_id(value) -> int | None:
    """Безопасно преобразует user_id из JWT payload в int."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        return int(cleaned) if cleaned.isdigit() else None
    return None


async def get_current_user(
        token: str = Depends(get_access_token),
        session: AsyncSession = Depends(get_session_without_commit)
) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError:
        raise TokenExpiredException
    except JWTError:
        raise NoJwtException

    expire = payload.get('exp')
    if not expire or datetime.fromtimestamp(int(expire), tz=timezone.utc) < datetime.now(timezone.utc):
        raise TokenExpiredException

    user_id = _normalize_user_id(payload.get("sub"))
    if not user_id:
        raise NoUserIdException

    user = await UsersDAO(session).find_one_or_none_by_id(data_id=int(user_id))
    if not user:
        raise UserNotFoundException
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role_id in [3, 4]:
        return current_user
    raise ForbiddenException


async def check_refresh_token(token: str = Depends(get_refresh_token),
                              session: AsyncSession = Depends(get_session_without_commit)) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = _normalize_user_id(payload.get("sub"))
        if not user_id:
            raise NoJwtException
        user = await UsersDAO(session).find_one_or_none_by_id(data_id=int(user_id))
        if not user:
            raise NoJwtException
        return user
    except JWTError:
        raise NoJwtException


# === M2M Аутентификация (Приложения) ===
def _get_valid_api_tokens() -> set[str]:
    """Безопасно парсит APP_AUTH_API_TOKENS из .env."""
    raw = settings.API_TOKENS
    if not raw:
        return set()
    return {t.strip() for t in re.split(r'[,;\s\n\r]+', raw) if t.strip()}


async def require_app_token(authorization: str | None = Header(None, alias="Authorization"),
                            x_app_name: str | None = Header(None, alias="x-app-name"),
                            session: AsyncSession = Depends(get_session_without_commit)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется заголовок: Authorization: Bearer <token>")

    token = authorization.replace("Bearer ", "", 1).strip()
    app_name = (x_app_name or "unknown").strip()

    # 1. Сначала проверяем JWT токен (временный, 1 час)
    from src.app_auth.utils import verify_app_jwt_token
    jwt_payload = await verify_app_jwt_token(token)
    if jwt_payload and jwt_payload.get("type") == "app_access":
        # Проверяем, что приложение существует и активно
        cred = await AppCredentialDAO(session).find_one_or_none_by_id(data_id=int(jwt_payload.get("sub")))
        if cred and cred.is_active and not cred.is_expired():
            logger.info(f"[AUTH] Доступ (JWT): {app_name}")
            return token

    # 2. Проверяем БД (долгосрочные токены для обратной совместимости)
    try:
        cred = await AppCredentialDAO(session).find_by_app_name(app_name)
        if cred and cred.is_active and cred.verify_token(token):
            logger.info(f"[AUTH] Доступ (БД): {app_name}")
            return token
    except Exception as e:
        logger.debug(f"[AUTH] БД недоступна, переходим к .env: {e}")

    # 3. Фоллбэк на .env (разработка)
    valid_env = _get_valid_api_tokens()
    if valid_env and token in valid_env:
        logger.info(f"[AUTH] Доступ (.env): {app_name}")
        return token

    # 4. Отказ
    logger.warning(f"[AUTH] Отказ: {app_name}")
    raise HTTPException(status_code=401, detail="Недействительный токен приложения")


async def get_app_token_for_service(
        app_name: str,
        session: AsyncSession = Depends(get_session_without_commit)
) -> str:
    """
    Генерирует временный JWT токен (1 час) для взаимодействия с другим сервисом.
    Используется внутри системы, когда одно приложение хочет обратиться к другому.
    
    :param app_name: имя приложения-источника
    :param session: сессия БД
    :return: JWT токен со сроком жизни 1 час
    """
    from src.app_auth.utils import create_app_jwt_token
    
    cred = await AppCredentialDAO(session).find_by_app_name(app_name)
    if not cred or not cred.is_active:
        raise HTTPException(status_code=404, detail=f"Приложение '{app_name}' не найдено или неактивно")
    
    if cred.is_expired():
        raise HTTPException(status_code=403, detail=f"Токен приложения '{app_name}' истёк")
    
    # Генерируем новый JWT токен на 1 час
    jwt_token = create_app_jwt_token(app_name=cred.app_name, app_id=cred.id, ttl_hours=1)
    logger.info(f"[SSO] Выдан временный токен для {app_name} (истекает через 1 час)")
    return jwt_token
