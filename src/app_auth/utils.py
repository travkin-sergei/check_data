# src/app_auth/utils.py
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from fastapi.responses import Response

from src.config.logger import logger
from src.app_auth.config import settings

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__ident="2b"
)


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        logger.warning(f"Попытка хэширования пароля >72 байт: {len(pwd_bytes)} байт")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_tokens(data: dict) -> dict:
    now = datetime.now(timezone.utc)
    access_payload = {**data, "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
                      "type": "access"}
    refresh_payload = {**data, "exp": int((now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
                       "type": "refresh"}
    return {
        "access_token": jwt.encode(access_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM),
        "refresh_token": jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM),
    }


async def authenticate_user(user, password: str):
    if not user or not verify_password(password, user.password):
        return None
    return user


def set_tokens(response: Response, user_id: int):
    tokens = create_tokens({"sub": str(user_id)})
    response.set_cookie("user_access_token", tokens["access_token"], httponly=True, secure=True, samesite="lax")
    response.set_cookie("user_refresh_token", tokens["refresh_token"], httponly=True, secure=True, samesite="lax")
