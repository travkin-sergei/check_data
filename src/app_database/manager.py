# src/app_database/manager.py
import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import Optional, Dict, Any, List, AsyncGenerator
import asyncpg
import psycopg2
from src.config.logger import logger
from src.app_database.config import DBConfig
from src.core.type_unifier import SchemaComparator  # Явная зависимость


class DBManager:
    _instance: Optional["DBManager"] = None
    _pools: Dict[str, asyncpg.Pool] = {}
    _init_lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init_pool(self, alias: str, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
        """Инициализация asyncpg пула с защитой от race condition."""
        if alias in self._pools:
            return self._pools[alias]

        async with self._init_lock:
            if alias in self._pools:
                return self._pools[alias]

            url = DBConfig.get_dsn(alias).raw.replace("postgresql://", "postgresql://", 1)
            try:
                pool = await asyncpg.create_pool(url, min_size=min_size, max_size=max_size,
                                                 server_settings={"statement_timeout": "30000"})
                self._pools[alias] = pool
                logger.info(f"[DB_MANAGER] Пул '{alias}' создан (asyncpg)")
                return pool
            except Exception as e:
                logger.error(f"[DB_MANAGER] Ошибка создания пула '{alias}': {e}")
                raise

    async def fetch_all(self, alias: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Выполнение SELECT с автоматической нормализацией типов через type_unifier."""
        pool = await self.get_pool(alias)
        comparator = SchemaComparator()

        async with pool.acquire() as conn:
            records = await conn.fetch(query, *params)
            if not records:
                return []

            # Нормализация типов через core.type_unifier
            normalized = []
            for row in records:
                row_dict = dict(row)
                for k, v in row_dict.items():
                    row_dict[k] = comparator.normalize_value(v)
                normalized.append(row_dict)
            return normalized

    @asynccontextmanager
    async def transaction(self, alias: str) -> AsyncGenerator[asyncpg.Connection, None]:
        """Безопасная транзакция с автооткатом при ошибке."""
        pool = await self.get_pool(alias)
        async with pool.acquire() as conn:
            try:
                async with conn.transaction():
                    yield conn
            except Exception as e:
                logger.error(f"[DB_MANAGER] Транзакция '{alias}' отменена: {e}")
                raise

    async def get_pool(self, alias: str) -> asyncpg.Pool:
        if alias not in self._pools:
            await self.init_pool(alias)
        return self._pools[alias]

    # --- Синхронный фоллбэк для legacy/background задач ---
    @contextmanager
    def get_sync_cursor(self, alias: str):
        """Прямое psycopg2 подключение (только для фоновых задач/миграций)."""
        dsn = DBConfig.get_dsn(alias).raw.replace("postgresql+asyncpg://", "postgresql://")
        conn = None
        try:
            conn = psycopg2.connect(dsn)
            with conn.cursor() as cur:
                yield cur
                conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"[DB_MANAGER] Ошибка sync-транзакции '{alias}': {e}")
            raise
        finally:
            if conn: conn.close()

    async def close_all(self):
        for alias, pool in self._pools.items():
            await pool.close()
            logger.info(f"[DB_MANAGER] Пул '{alias}' закрыт")
        self._pools.clear()