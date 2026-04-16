# src/app_comtrade/main.py
"""
Запуск приложения для локальной отладки (изолированно)
"""
from fastapi import FastAPI
from src.config.logger import config_logging
from src.app_comtrade.config import API_PREFIX_V1, TAG_NAME, LOG_LEVEL, HOST, PORT, RELOAD
from src.app_comtrade.api import router

config_logging(level=LOG_LEVEL, log_base_path="src")

app = FastAPI(
    title="Comtrade Validation Service",
    description="Изолированный сервис проверки файлов и схем (без БД)",
    version="1.0.0",
    openapi_tags=[{"name": TAG_NAME, "description": "Универсальная валидация JSON-конфигураций"}]
)
app.include_router(router, prefix=API_PREFIX_V1)

if __name__ == "__main__":
    import uvicorn

    print(f"Docs: http://127.0.0.1:{PORT}/docs")
    uvicorn.run(
        "src.app_comtrade.main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level=LOG_LEVEL.lower()
    )
