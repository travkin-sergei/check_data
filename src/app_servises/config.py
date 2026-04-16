# src/app_servises/config.py
"""
Конфигурация app_servises.
Изолирована от core и app_database: использует только ENV-переменные.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DATA_ROOT_DIR = Path(os.getenv("APP_SERVICES_DATA_ROOT", ".")).resolve()
APP_NAME = "servises"
TAG_NAME = "APP Servises"
APP_VERSION = "1.0.0"
APP_AUTHOR = "travkin"

# Авторизация (множество токенов через запятую)
APP_TOKEN = {t.strip() for t in os.getenv("APP_SERVICES_TOKEN", "dev-token-123").split(",") if t.strip()}

# API и сервер
API_PREFIX_V1 = f"/api/v1/{APP_NAME}"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOST = os.getenv("APP_SERVICES_HOST", "0.0.0.0")
PORT = int(os.getenv("APP_SERVICES_PORT", "8002"))
RELOAD = os.getenv("APP_SERVICES_RELOAD", "true").lower() in ("true", "1", "yes")

# Теги для OpenAPI
openapi_tags = {
    "name": TAG_NAME,
    "description": "Проверка источников данных и мониторинг обновлений."
}