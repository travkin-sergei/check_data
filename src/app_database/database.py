# src/app_database/database.py
import os
import re
import asyncpg
import psycopg2

from typing import Optional, Dict
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager, asynccontextmanager
from src.config.logger import logger


class SecureString(str):
    def __str__(self): return "(********)"

    def __repr__(self): return "(********)"

    def __format__(self, format_spec): return "(********)"

    def __getattribute__(self, name):
        if name in ['__reduce__', '__reduce_ex__', '__getnewargs__', '__getstate__']:
            raise AttributeError(f"Доступ к методу '{name}' запрещён")
        return super().__getattribute__(name)

    def get_raw(self) -> str: return super().__str__()


class DBConnection:
    PASSWORD_PATTERN = re.compile(r'password=([^@\s]+)@')

    def __init__(self, db_name: Optional[str] = None):
        self.__db_name = db_name
        self.__connection_string: Optional[SecureString] = None
        self.__connection_pool = None
        self.__initialized = False
        self._initialize_connection(db_name)

    def _initialize_connection(self, db_name: Optional[str]) -> None:
        if db_name is None: return
        connection_string = self._get_connection_string(db_name)
        if connection_string:
            self.__connection_string = SecureString(connection_string)
            self.__initialized = True
            logger.info(f"Подключение к БД '{db_name}' инициализировано")
        else:
            logger.error(f"Не найдена строка подключения для БД '{db_name}'")

    def _get_connection_string(self, db_name: str) -> Optional[str]:
        mapping = {
            'base_01': os.getenv('DB_LOCAL_01'),
            'local_auth': os.getenv('DB_LOCAL_AUTH'),
            'app_file_manager': os.getenv('APP_SYSTEMS_DB'),
        }
        conn_str = mapping.get(db_name)
        if conn_str and conn_str.startswith('postgresql://'):
            parsed = urlparse(conn_str)
            params = parse_qs(parsed.query)
            dsn = f"host={parsed.hostname} port={parsed.port or 5432} dbname={parsed.path.lstrip('/')}"
            if parsed.username: dsn += f" user={parsed.username}"
            if parsed.password: dsn += f" password={parsed.password}"
            for k, v in params.items(): dsn += f" {k}={v[0]}"
            return dsn
        return conn_str

    def get_connection(self) -> Optional[psycopg2.extensions.connection]:
        if not self.__connection_string: return None
        try:
            return psycopg2.connect(self.__connection_string.get_raw())
        except Exception as e:
            logger.error(f"Ошибка подключения к БД '{self.__db_name}': {e}")
            return None

    @contextmanager
    def get_cursor(self, commit: bool = False):
        conn = self.get_connection()
        if conn is None: raise ConnectionError("Не удалось подключиться к базе данных")
        cursor = conn.cursor()
        try:
            yield cursor
            if commit: conn.commit()
        except Exception as error:
            conn.rollback()
            logger.error(f"Ошибка транзакции: {error}")
            raise
        finally:
            cursor.close()
            conn.close()

    def close_pool(self) -> None:
        if self.__connection_pool:
            try:
                self.__connection_pool.closeall()
            except Exception:
                pass
            finally:
                self.__connection_pool = None

    @property
    def is_initialized(self) -> bool:
        return self.__initialized


class AsyncDBConnection:
    def __init__(self, db_name: str = None):
        self.__db_name = db_name
        self.__connection_string: Optional[SecureString] = None
        self.__pool = None
        self.__initialized = False
        self._initialize_connection(db_name)

    def _initialize_connection(self, db_name: str):
        mapping = {
            'base_01': os.getenv('DB_LOCAL_01'),
            'local_auth': os.getenv('DB_LOCAL_AUTH'),
            'app_file_manager': os.getenv('APP_SYSTEMS_DB'),
        }
        conn_str = mapping.get(db_name)
        if conn_str and conn_str.startswith('postgresql://'):
            conn_str = conn_str.replace('postgresql://', 'postgresql+asyncpg://')
        if conn_str:
            self.__connection_string = SecureString(conn_str)
            self.__initialized = True
            logger.info(f"Async-подключение '{db_name}' инициализировано")

    async def create_pool(self, min_size=1, max_size=10):
        if not self.__connection_string: return False
        raw_url = self.__connection_string.get_raw().replace('postgresql+asyncpg://', 'postgresql://')
        self.__pool = await asyncpg.create_pool(raw_url, min_size=min_size, max_size=max_size)
        return True

    @asynccontextmanager
    async def get_cursor(self):
        if not self.__pool: await self.create_pool()
        async with self.__pool.acquire() as conn:
            yield conn

    async def close_pool(self):
        if self.__pool:
            await self.__pool.close()
            self.__pool = None

    @property
    def is_initialized(self) -> bool:
        return self.__initialized


class DBManager:
    _instance = None
    _connections: Dict[str, DBConnection] = {}
    _async_connections: Dict[str, AsyncDBConnection] = {}

    def __new__(cls):
        if cls._instance is None: cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_connection(cls, db_name: str) -> DBConnection:
        if db_name not in cls._connections: cls._connections[db_name] = DBConnection(db_name)
        return cls._connections[db_name]

    @classmethod
    def get_async_connection(cls, db_name: str) -> AsyncDBConnection:
        if db_name not in cls._async_connections: cls._async_connections[db_name] = AsyncDBConnection(db_name)
        return cls._async_connections[db_name]

    @classmethod
    def initialize_all(cls, db_names: list, async_mode: bool = False) -> None:
        for db_name in db_names:
            if async_mode:
                cls.get_async_connection(db_name)
            else:
                cls.get_connection(db_name)
        logger.info(
            f"Инициализировано подключений: {len(cls._connections) if not async_mode else len(cls._async_connections)}")

    @classmethod
    async def close_all_async(cls) -> None:
        for conn in cls._async_connections.values(): await conn.close_pool()
        cls._async_connections.clear()

    @classmethod
    def close_all(cls) -> None:
        for conn in cls._connections.values(): conn.close_pool()
        cls._connections.clear()

    @classmethod
    def get_connection_string(cls, db_name: str) -> Optional[str]:
        mapping = {'base_01': os.getenv('DB_LOCAL_01'), 'local_auth': os.getenv('DB_LOCAL_AUTH'),
                   'app_file_manager': os.getenv('APP_SYSTEMS_DB')}
        return mapping.get(db_name)