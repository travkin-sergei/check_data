#src/app_macmap/main.py
"""
Запуск приложения для локальной отладки (изолированно)
"""
from fastapi import FastAPI
from src.app_systems.config import API_PREFIX_V1, LOG_LEVEL, TAG_NAME, HOST, PORT, RELOAD
from src.config.logger import config_logging
from src.app_systems.api import router

config_logging(
    level=LOG_LEVEL,
    log_base_path="src"
)

app = FastAPI(
    title="App macmap",
    description="Приложение для MacMap.",
    version="1.0.0",
    openapi_tags=[
        {
            "name": TAG_NAME,
            "description": "MacMap."
        }
    ],
    swagger_ui_parameters={"docExpansion": "none"},
)

app.include_router(router, prefix=API_PREFIX_V1)

if __name__ == "__main__":
    import uvicorn

    print(f'http://127.0.0.1:{PORT}/docs#/')
    uvicorn.run(
        "src.app_macmap.main:app_auth",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level="info",
    )
