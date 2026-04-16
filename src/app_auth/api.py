# src/app_auth/api.py
from typing import List
from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.app_auth.models import User
from src.app_auth.schemas import SUserRegister, SUserAuth, EmailModel, SUserAddDB, SUserInfo
from src.app_auth.utils import authenticate_user, set_tokens
from src.app_auth.dao import UsersDAO
from src.app_auth.exceptions import UserAlreadyExistsException, IncorrectEmailOrPasswordException
from src.app_auth.dependencies import (
    get_current_user, get_current_admin_user, check_refresh_token,
    get_session_with_commit, get_session_without_commit, require_app_token
)

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
    user = await UsersDAO(session).find_one_or_none(filters=EmailModel(email=user_data.email))
    if not user or not await authenticate_user(user=user, password=user_data.password):
        raise IncorrectEmailOrPasswordException
    set_tokens(response, user.id)
    return {"ok": True, "message": "Авторизация успешна!"}


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
