# src/core/app_token_validator.py
"""
Общий валидатор токенов приложений.
Строгое переиспользование: src.config.logger, src.app_database.manager
Изоляция: не импортирует app_auth напрямую, работает только с БД.
"""
import bcrypt
from typing import Optional, Tuple
from src.config.logger import logger
from src.app_database.manager import DBManager


async def verify_app_token(token: str, app_name: str, db_alias: str = "local_auth") -> Tuple[bool, Optional[str]]:
    """
    Проверяет токен приложения через БД app_auth.app_credentials.
    Возвращает: (True, app_name) или (False, error_message)
    """
    if not token or not app_name:
        return False, "Отсутствует токен или имя приложения"

    try:
        manager = DBManager()
        # Ищем запись только по имени приложения (индекс есть, запрос быстрый)
        query = """
            SELECT token_hash, is_active 
            FROM app_auth.app_credentials 
            WHERE app_name = $1
        """
        records = await manager.fetch_all(db_alias, query, (app_name,))

        if not records:
            logger.warning(f"[APP_AUTH] Приложение '{app_name}' не зарегистрировано")
            return False, "Приложение не найдено в реестре"

        cred = records[0]
        if not cred.get("is_active", False):
            logger.warning(f"[APP_AUTH] Приложение '{app_name}' заблокировано")
            return False, "Приложение деактивировано"

        # Проверка хеша (bcrypt безопасен к тайминг-атакам)
        token_bytes = token.encode("utf-8")
        hash_bytes = cred["token_hash"].encode("utf-8")

        if bcrypt.checkpw(token_bytes, hash_bytes):
            logger.info(f"[APP_AUTH] Токен для '{app_name}' валиден")
            return True, app_name

        logger.warning(f"[APP_AUTH] Неверный токен для '{app_name}'")
        return False, "Недействительный токен"

    except Exception as e:
        logger.error(f"[APP_AUTH] Ошибка валидации токена: {e}", exc_info=True)
        return False, "Внутренняя ошибка проверки доступа"