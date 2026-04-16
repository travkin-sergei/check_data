# src/app_auth/config.py
"""
Конфигурация app_auth.
Изолирована от core: использует ENV-переменные с фоллбэком.
Строгое переиспользование: logger, database, type_unifier подключаются точечно в зависимых модулях.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class AuthSettings(BaseSettings):
    APP_NAME: str = "auth"
    APP_VERSION: str = "1.0.0"
    API_PREFIX_V1: str = f"/api/v1/{APP_NAME}"

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    HOST: str = os.getenv("APP_AUTH_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("APP_AUTH_PORT", "8000"))
    RELOAD: bool = os.getenv("APP_AUTH_RELOAD", "true").lower() in ("true", "1", "yes")

    DB_ALIAS: str = "local_auth"
    SECRET_KEY: str = os.getenv("APP_AUTH_SECRET_KEY", "supersecret_dev_key_change_me")
    ALGORITHM: str = os.getenv("APP_AUTH_ALGORITHM", "HS256")

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("APP_AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("APP_AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    API_TOKENS: str = os.getenv("APP_AUTH_API_TOKENS", "")

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )
    # Настройки внешнего SSO
    SSO_TOKEN_URL: str = os.getenv("SSO_TOKEN_URL", "")
    SSO_CLIENT_ID: str = os.getenv("SSO_CLIENT_ID", "")
    SSO_CLIENT_SECRET: str = os.getenv("SSO_CLIENT_SECRET", "")
    SSO_REALM: str = os.getenv("SSO_REALM", "")
    SSO_SERVICE: str = os.getenv("SSO_SERVICE", "")
    SSO_ENABLED: bool = os.getenv("SSO_ENABLED", "false").lower() in ("true", "1", "yes")


# Глобальный экземпляр настроек
settings = AuthSettings()

TAG_NAME = "APP Auth"
openapi_tags = {
    "name": TAG_NAME,
    "description": "Авторизация, аутентификация и управление ролями."
}
