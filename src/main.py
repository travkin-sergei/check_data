# src/main.py
"""
Точка входа для общего сервиса.
Управляет жизненным циклом, инициализацией и запуском.
"""

import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import HOST, PORT, RELOAD, LOG_LEVEL
from src.api import router as system_router, include_app_routers, openapi_tags
from src.config.logger import config_logging, logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения (startup / shutdown)."""
    logger.info("Инициализация сервиса...")

    config_logging(
        level=LOG_LEVEL.upper() if isinstance(LOG_LEVEL, str) else LOG_LEVEL,
        mask_sensitive_data=True,
        log_base_path="src"
    )
    logger.info("Логирование настроено")

    yield  # ← КРИТИЧНО: разделяет startup и shutdown

    logger.info("Корректное завершение работы сервиса...")
    logger.info("Сервис остановлен")


app = FastAPI(
    title="Data Validation Service",
    description="Централизованный сервис проверки данных, схем и структуры файлов",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"docExpansion": "none"},
)

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Роутеры ===
app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
include_app_routers(app)

if __name__ == "__main__":
    logger.info(f"Swagger: http://{HOST}:{PORT}/docs")
    logger.info(f"ReDoc:   http://{HOST}:{PORT}/redoc")
    uvicorn.run(
        "src.main:app_auth",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level="info",
    )
