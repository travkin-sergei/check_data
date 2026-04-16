# src/app_auth/config.py
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    model_config = SettingsConfigDict(env_file=str(env_path), extra="ignore")

settings = AuthSettings()
TAG_NAME = "APP Auth"
openapi_tags = {"name": TAG_NAME, "description": "Авторизация, аутентификация и управление ролями."}