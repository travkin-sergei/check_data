# src/app_file_manager/config.py

"""
Конфигурация app_file_manager.
Изолирована от core: использует ENV-переменные с фоллбэком.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

DATA_ROOT_DIR = Path(os.getenv("APP_SYSTEMS_DATA_ROOT", '.')).resolve()

APP_NAME = 'systems'
TAG_NAME = 'APP file manager'
APP_VERSION = '1.0.0'
APP_AUTHOR = 'travkin'
APP_TOKEN = os.getenv("APP_SYSTEMS_TOKEN", "111,222").split(',')
API_PREFIX_V1 = f"/api/v1/{APP_NAME}"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOST = os.getenv("APP_SYSTEMS_HOST", "0.0.0.0")
PORT = int(os.getenv("APP_SYSTEMS_PORT", 8001))
RELOAD = os.getenv("APP_SYSTEMS_RELOAD", "true").lower() in ("true", "1", "yes")
APP_AUTH_URL = os.getenv("APP_AUTH_URL", "http://127.0.0.1:8000")

# Теги для OpenAPI
openapi_tags = {
    "name": TAG_NAME,
    "description": "Мониторинг доступности файлов и извлечение схем данных."
}

