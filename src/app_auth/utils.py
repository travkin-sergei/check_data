# src/app_auth/utils.py
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt
from fastapi.responses import Response
from src.config.logger import logger
from src.app_auth.config import settings


def get_password_hash(password: str) -> str:
    """
    Хеширует пароль с использованием bcrypt.
    Явно обрабатывает ограничение bcrypt в 72 байта.
    """
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        logger.warning(f"Пароль усечён до 72 байт (ограничение bcrypt): исходная длина {len(pwd_bytes)}")
        pwd_bytes = pwd_bytes[:72]
    # rounds=12, ident="2b" — стандарт безопасности, эквивалент вашего CryptContext
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль против хеша bcrypt. Безопасно обрабатывает усечение."""
    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception as e:
        logger.error(f"Ошибка проверки пароля: {e}")
        return False


def create_tokens(data: dict) -> dict:
    """Создаёт пару access/refresh токенов через python-jose."""
    now = datetime.now(timezone.utc)
    access_payload = {
        **data,
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "type": "access"
    }
    refresh_payload = {
        **data,
        "exp": int((now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        "type": "refresh"
    }
    return {
        "access_token": jwt.encode(access_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM),
        "refresh_token": jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM),
    }


async def authenticate_user(user, password: str):
    """Возвращает пользователя, если пароль верный, иначе None."""
    if not user or not verify_password(password, user.password):
        return None
    return user


def set_tokens(response: Response, user_id: int):
    """Устанавливает токены в httpOnly куки."""
    tokens = create_tokens({"sub": str(user_id)})
    response.set_cookie("user_access_token", tokens["access_token"], httponly=True, secure=True, samesite="lax")
    response.set_cookie("user_refresh_token", tokens["refresh_token"], httponly=True, secure=True, samesite="lax")


def generate_app_token(length: int = 256) -> str:
    """Генерирует криптографически стойкий токен для приложения."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def hash_app_token(token: str) -> str:
    """Хеширует токен приложения через bcrypt (как пароли пользователей)."""
    return get_password_hash(token)  # переиспользуем существующую функцию


def create_app_jwt_token(app_name: str, app_id: int, ttl_hours: int = 1) -> str:
    """
    Создаёт JWT токен для межсервисного взаимодействия с TTL = 1 час.
    
    :param app_name: имя приложения
    :param app_id: ID записи в app_credentials
    :param ttl_hours: время жизни токена в часах (по умолчанию 1)
    :return: JWT токен
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(app_id),
        "app_name": app_name,
        "type": "app_access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp())
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def verify_app_jwt_token(token: str) -> dict | None:
    """
    Проверяет JWT токен приложения.
    
    :param token: JWT токен
    :return: payload токена или None если невалиден
    """
    from jose import ExpiredSignatureError, JWTError
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # Дополнительная проверка времени жизни
        expire = payload.get('exp')
        if not expire or datetime.fromtimestamp(int(expire), tz=timezone.utc) < datetime.now(timezone.utc):
            logger.warning(f"[APP JWT] Токен истёк: exp={expire}")
            return None
            
        return payload
    except ExpiredSignatureError:
        logger.warning("[APP JWT] Токен истёк (ExpiredSignatureError)")
        return None
    except JWTError as e:
        logger.error(f"[APP JWT] Ошибка валидации токена: {e}")
        return None