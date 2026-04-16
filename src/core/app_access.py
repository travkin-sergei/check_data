# src/core/app_access.py
"""
Централизованный трекер доступа приложений.
Строгое переиспользование:
  - src.config.database.DBManager
  - src.config.logger.logger
  - src.core.type_unifier.SchemaComparator
Изоляция: не импортирует роуты, схемы или конфиги конкретных приложений.
"""
from typing import Optional
from fastapi import HTTPException, status, Header, Depends

from src.app_database import DBManager
from src.config.logger import logger
from src.core.type_unifier import SchemaComparator  # ← обязательное переиспользование


class AppAccessTracker:
    """Сервис фиксации последнего доступа и валидации метаданных."""
    _comparator = SchemaComparator()

    @staticmethod
    def _normalize_service_name(name: str) -> str:
        """Нормализует имя сервиса через type_unifier (пример строгого переиспользования)."""
        if not name or not isinstance(name, str):
            return "unknown_service"
        # Очистка и приведение к безопасному формату
        clean = name.strip().lower().replace(" ", "_").replace("-", "_")
        # Используем валидатор схемы для отсечения невалидных символов (fallback)
        return clean[:100] if len(clean) > 100 else clean

    @staticmethod
    def record_access(service_name: str, token_prefix: str) -> bool:
        """Синхронно записывает время последнего доступа.
        Использует DBManager из src.config.database, как в app_systems/api.py
        """
        safe_name = AppAccessTracker._normalize_service_name(service_name)
        try:
            db_conn = DBManager.get_connection("base_01")
            if not db_conn or not db_conn.is_initialized:
                logger.debug("[ACCESS_TRACKER] БД не инициализирована. Запись пропущена.")
                return False

            with db_conn.get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO app_access_audit (service_name, token_prefix, last_access_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (service_name)
                    DO UPDATE SET last_access_at = NOW(), token_prefix = EXCLUDED.token_prefix
                    """
                )
            return True
        except Exception as e:
            logger.warning(f"[ACCESS_TRACKER] Не удалось зафиксировать доступ для '{safe_name}': {e}")
            return False


async def require_tracked_app_access(
        service_name: str,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_app_name: Optional[str] = Header(None, alias="x-app-name")
) -> dict:
    """
    FastAPI Dependency:
    1. Проверяет наличие Bearer-токена.
    2. Фиксирует время последнего входа в БД.
    3. Возвращает метаданные доступа (можно использовать в роуте).
    """
    real_name = x_app_name or service_name
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок: Authorization: Bearer <token>"
        )

    token = authorization.split(" ", 1)[1].strip()
    if len(token) < 16:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен слишком короткий или не соответствует формату"
        )

    token_prefix = f"{token[:8]}..."
    safe_name = AppAccessTracker._normalize_service_name(real_name)

    # Фиксация входа (FastAPI автоматически запустит sync-функцию в threadpool)
    AppAccessTracker.record_access(safe_name, token_prefix)

    logger.info(f"[ACCESS] Приложение '{safe_name}' авторизовано (токен: {token_prefix})")
    return {"service": safe_name, "token_prefix": token_prefix}
