# src/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
APP_NAME = 'all'
APP_VERSION = '1.0.0'
APP_AUTHOR = 'travkin'
HOST = "0.0.0.0"
PORT = 8000
RELOAD = True
LOG_LEVEL = os.getenv('LOG_LEVEL')
# переменная расположения папки с данными
CORE_BASE_URL = Path(os.getenv('EXTERNAL_FILE'))
ECOMRU_API_URL = os.getenv('ECOMRU_API_URL')
ECOMRU_API_KEY = os.getenv('ECOMRU_API_KEY')
