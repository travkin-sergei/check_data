# src/config/database.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config.logger import logger

_engines = {}
_factories = {}


def get_engine(alias: str, dsn: str) -> create_async_engine:
    if alias not in _engines:
        url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        _engines[alias] = create_async_engine(url, echo=False, pool_pre_ping=True, pool_size=5, max_overflow=10)
        logger.info(f"[DB] Engine создан: {alias}")
    return _engines[alias]


def get_session_factory(alias: str, dsn: str) -> async_sessionmaker[AsyncSession]:
    if alias not in _factories:
        engine = get_engine(alias, dsn)
        _factories[alias] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _factories[alias]


async def get_async_session(alias: str, dsn: str) -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory(alias, dsn)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
