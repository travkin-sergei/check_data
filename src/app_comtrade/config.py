# src/app_comtrade/config.py
"""
Список всех статических переменных в приложении
"""
import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
APP_NAME = 'comtrade'
APP_VERSION = '1.0.0'
APP_AUTHOR = 'travkin'
API_PREFIX_V1 = f"/api/v1/{APP_NAME}"

TAG_NAME = 'APP comtrade'
LOG_LEVEL = "INFO"
HOST = "0.0.0.0"
PORT = 8000
RELOAD = True
MAX_CONCURRENT_DOWNLOADS = 5
DOWNLOAD_TIMEOUT = 300.0

API_URL = os.getenv("ECOMRU_API_URL")
API_TOKEN = os.getenv("ECOMRU_API_KEY")
INTERNAL_API_TOKEN = os.getenv("APP_SYSTEMS_TOKEN")
ALLOWED_SUFFIXES = ["extendet", "rrrr", "tmp", "bak", "sended", "processed"]
EXTERNAL_ENDPOINT = "/api/v1/updates"
EXTERNAL_URL = API_URL + EXTERNAL_ENDPOINT if API_URL else ""
INTERNAL_HOST = os.getenv("INTERNAL_API_HOST", "127.0.0.1")
INTERNAL_PORT = os.getenv("INTERNAL_API_PORT", "8001")
INTERNAL_API_BASE = f"http://{INTERNAL_HOST}:{INTERNAL_PORT}/api/v1/systems"
INTERNAL_UPLOAD_ENDPOINT = f"{INTERNAL_API_BASE}/upload-file"
INTERNAL_CHECK_ENDPOINT = f"{INTERNAL_API_BASE}/check-file-exists"
