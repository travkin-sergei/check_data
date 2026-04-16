# src/app_comtrade/config.py
"""
Список всех статических переменных в приложении
"""
import os

from src.core.config import CORE_BASE_URL  # Или ваш глобальный конфиг

APP_NAME = "comtrade"
APP_VERSION = "1.0.0"
API_PREFIX_V1 = f"/api/v1/{APP_NAME}"
BASE_URL = CORE_BASE_URL
TAG_NAME = "APP Comtrade Validation"
HOST = "0.0.0.0"
PORT = 8002
RELOAD = True
APP_NAME = 'comtrade'

APP_AUTHOR = 'travkin'

LOG_LEVEL = os.getenv('LOG_LEVEL')  # GLOBAL_LOG_LEVEL
