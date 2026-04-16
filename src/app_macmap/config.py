# src/app_macmap/config.py
"""
Список всех статических переменных в приложении
"""
from src.core.config import CORE_BASE_URL

APP_NAME = 'macmap'
APP_VERSION = '1.0.0'
APP_AUTHOR = 'travkin'
API_PREFIX_V1 = f"/api/v1/{APP_NAME}"
BASE_URL = CORE_BASE_URL
TAG_NAME = 'APP macmap'
LOG_LEVEL = "INFO"
HOST = "0.0.0.0"
PORT = 8000
RELOAD = True
