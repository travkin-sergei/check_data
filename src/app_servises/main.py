# src/app_servises/main.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from src.config.logger import config_logging
from src.app_database.manager import DBManager  # ✅ из app_database
from src.app_servises.config import LOG_LEVEL, HOST, PORT, RELOAD, openapi_tags
from src.app_servises.api import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config_logging(level=LOG_LEVEL, log_base_path="src")

    # Инициализация пула БД (мягко, без падения если нет таблицы)
    try:
        await DBManager().init_pool("app_servises")
    except Exception as e:
        from src.config.logger import logger
        logger.warning(f"[MAIN] Пул БД не инициализирован: {e}")

    yield
    await DBManager().close_all()


app = FastAPI(
    title=openapi_tags["name"],
    description=openapi_tags["description"],
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"docExpansion": "none"}
)

app.include_router(router, prefix=f"/api/v1/{openapi_tags['name'].split()[-1].lower()}")

if __name__ == "__main__":
    import uvicorn

    print(f"🌐 Swagger: http://{HOST}:{PORT}/docs")
    uvicorn.run("src.app_servises.main:app", host=HOST, port=PORT, reload=RELOAD, log_level=LOG_LEVEL.lower())