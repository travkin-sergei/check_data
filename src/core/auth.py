# src/core/auth.py
"""
Статическая валидация API-токенов из .env
Строгое переиспользование:
  - src.config.logger.logger
  - src.config.database.DBManager
  - src.core.type_unifier (нормализация/валидация строк)
Изоляция: не импортирует роуты/схемы приложений.
"""
import os
import re
from typing import Optional
from fastapi import HTTPException, status, Header, Depends

from src.config.logger import logger
from src.config.database import DBManager

# Адаптация под ваш type_unifier.py (безопасный fallback)
try:
    from src.core.type_unifier import unify_token, is_valid_token_format
except ImportError:
    def unify_token(t: str) -> str:
        return t.strip().lower()


    def is_valid_token_format(t: str) -> bool:
        return 200 <= len(t) <= 300


class TokenRegistry:
    """Реестр валидных токенов (загружается из TOKENS_AC* при старте)."""
    _tokens: set[str] = set()
    _loaded: bool = False
    # Список переменных окружения для загрузки
    ENV_TOKEN_VARS = [
        "TOKENS_ADMIN",
        "TOKENS_AC",
    ]

    @classmethod
    def load_from_env(cls) -> None:
        if cls._loaded:
            return

        raw_tokens = []
        for var_name in cls.ENV_TOKEN_VARS:
            val = os.getenv(var_name, "").strip()
            if val:
                # Разделители: запятая, точка с запятой, пробел, перевод строки
                raw_tokens.extend(re.split(r'[,;\s\n\r]+', val))
                logger.debug(f"[AUTH] Обработка переменной {var_name}")

        if not raw_tokens:
            logger.critical("[AUTH] Ни одна из переменных TOKENS_AC* не задана. Доступ будет заблокирован.")
            cls._loaded = True
            return

        valid = set()
        for raw_token in raw_tokens:
            token = raw_token.strip()
            if not token:
                continue
            if is_valid_token_format(token):
                valid.add(unify_token(token))
            else:
                logger.warning(f"[AUTH] Отклонён некорректный токен: '{token[:10]}...'")

        cls._tokens = valid
        cls._loaded = True
        logger.info(f"[AUTH] Загружено активных токенов: {len(cls._tokens)} (из {', '.join(cls.ENV_TOKEN_VARS)})")

    @classmethod
    def check(cls, token: str) -> bool:
        return unify_token(token) in cls._tokens

    @classmethod
    def audit_access(cls, token_prefix: str, endpoint: str, success: bool) -> None:
        """Опциональная запись аудита в БД через DBManager."""
        try:
            db_conn = DBManager.get_connection("base_01")
            if not db_conn or not db_conn.is_initialized:
                return
            with db_conn.get_cursor(commit=True) as cur:
                cur.execute(
                    """INSERT INTO auth_audit_log 
                    (token_prefix, endpoint, accessed_at, success)
                    VALUES (%s, %s, NOW(), %s)""",
                    (token_prefix, endpoint, success)
                )
        except Exception as e:
            logger.debug(f"[AUTH] Аудит в БД пропущен: {e}")


# Инициализация при импорте модуля
TokenRegistry.load_from_env()


async def require_valid_token(
        authorization: Optional[str] = Header(None),
        x_endpoint: str = Header(None, alias="x-endpoint")
) -> str:
    """FastAPI Dependency для проверки статического токена."""
    if not authorization:
        TokenRegistry.audit_access("none", x_endpoint or "unknown", False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок: Authorization: Bearer <token>"
        )

    token = authorization.replace("Bearer ", "").strip()
    prefix = token[:10] if len(token) >= 10 else "****"

    if not TokenRegistry.check(token):
        logger.warning(f"[AUTH] Отказано: невалидный токен ({prefix}...) для {x_endpoint}")
        TokenRegistry.audit_access(prefix, x_endpoint or "unknown", False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    logger.debug(f"[AUTH] Доступ разрешён: токен ({prefix}...) для {x_endpoint}")
    TokenRegistry.audit_access(prefix, x_endpoint or "unknown", True)
    return token
