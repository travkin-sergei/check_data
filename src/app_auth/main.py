# src/app_auth/main.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends
from fastapi.security import HTTPBearer
from src.config.logger import config_logging
from src.app_auth.config import settings, openapi_tags
from src.app_auth.api import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Инициализация логгера (строгая зависимость от src.config.logger)
    config_logging(level=settings.LOG_LEVEL, log_base_path="src")

    # 2. Инициализация пула БД через app_database (строго соответствует src/config/database.py)
    from src.app_database.manager import DBManager
    await DBManager().init_pool(settings.DB_ALIAS)
    yield
    # 3. Корректное закрытие пула
    await DBManager().close_all()


security = HTTPBearer()

app = FastAPI(
    title=openapi_tags["name"],
    description=openapi_tags["description"],
    version=settings.APP_VERSION,
    openapi_tags=[openapi_tags],
    lifespan=lifespan,
    swagger_ui_parameters={"docExpansion": "none"},
    openapi_security_schemes={
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    },
    security=[{"HTTPBearer": []}]
)

app.include_router(router, prefix=settings.API_PREFIX_V1, dependencies=[Depends(security)])

if __name__ == "__main__":
    import uvicorn

    print(f"http://127.0.0.1:{settings.PORT}/docs#/")
    uvicorn.run(
        "src.app_auth.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )
