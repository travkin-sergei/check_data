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

    # 1. Сначала проверяем БД (продакшен)
    try:
        cred = await AppCredentialDAO(session).find_by_app_name(app_name)
        if cred and cred.is_active and cred.verify_token(token):
            logger.info(f"[AUTH] Доступ (БД): {app_name}")
            return token
    except Exception as e:
        logger.debug(f"[AUTH] БД недоступна, переходим к .env: {e}")

    # 2. Фоллбэк на .env (разработка)
    valid_env = _get_valid_api_tokens()
    if valid_env and token in valid_env:
        logger.info(f"[AUTH] Доступ (.env): {app_name}")
        return token

    # 3. Отказ
    logger.warning(f"[AUTH] Отказ: {app_name}")
    raise HTTPException(status_code=401, detail="Недействительный токен приложения")
