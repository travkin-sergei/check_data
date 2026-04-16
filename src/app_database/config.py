# src/app_database/config.py
from pathlib import Path
from dotenv import load_dotenv
from src.app_database.security import load_dsn_from_env, SecureDSN
from src.config.logger import logger

# Загрузка .env из корня проекта
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DB_ALIASES = ["base_01", "local_auth", "app_systems", "app_servises"]


class DBConfig:
    """Конфигурация подключений к БД с безопасным хранением DSN."""

    _dsns: dict[str, SecureDSN] = {}

    @classmethod
    def get_dsn(cls, alias: str) -> SecureDSN:
        """Получает SecureDSN по алиасу, загружая из .env при необходимости."""
        if alias not in cls._dsns:
            env_map = {
                "base_01": "DB_LOCAL_01",
                "local_auth": "DB_LOCAL_AUTH",
                "app_systems": "APP_SYSTEMS_DB",
                "app_servises": "APP_SERVICES_DB",
            }
            env_key = env_map.get(alias)
            if not env_key:
                raise ValueError(f"Неизвестный алиас БД: {alias}")
            cls._dsns[alias] = load_dsn_from_env(env_key)
            logger.info(f"[DB_CONFIG] DSN для '{alias}' загружен")
        return cls._dsns[alias]

    @classmethod
    def to_asyncpg_url(cls, alias: str) -> str:
        """Конвертация postgresql:// → postgresql+asyncpg:// для SQLAlchemy/asyncpg"""
        raw = cls.get_dsn(alias).raw
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
