# src/app_systems/main.py
"""
Запуск приложения для локальной отладки (изолированно).
Не импортирует core.config напрямую — только через ENV/синглтоны.
"""
from fastapi import FastAPI

from src.app_systems.config import (
    API_PREFIX_V1,
    APP_VERSION,
    LOG_LEVEL,
    HOST,
    PORT,
    RELOAD,
    openapi_tags,
)
from src.config.logger import config_logging
from src.app_systems.api import router



# Настройка логирования
config_logging(
    level=LOG_LEVEL,
    log_base_path="src"
)

app = FastAPI(
    title=openapi_tags.get('name'),
    description=openapi_tags.get('description'),
    version=APP_VERSION,
    openapi_tags=[openapi_tags],
    swagger_ui_parameters={"docExpansion": "none"},
    security_schemes={
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Token"
        }
    }
)

app.include_router(router, prefix=API_PREFIX_V1)

if __name__ == "__main__":
    import uvicorn

    # При локальной проверке
    print(f'http://127.0.0.1:{PORT}/docs#/')
    uvicorn.run(
        "src.app_systems.main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level=LOG_LEVEL.lower(),
    )