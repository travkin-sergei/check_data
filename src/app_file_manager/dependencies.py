# src/app_file_manager/dependencies.py
"""
Зависимости авторизации app_file_manager.
Строгое переиспользование:
- src.config.logger (логирование)
- src.core.api_client (HTTP-клиент с ретраями)
Изоляция: нет прямых импортов из app_auth.*
"""

from typing import Optional
from src.app_file_manager.config import APP_TOKEN
from fastapi import Header, HTTPException, status
from src.config.logger import logger
from src.core.api_client import APIClient, APIClientHTTPError
from src.app_file_manager.config import APP_AUTH_URL


async def require_app_auth(authorization: str | None = Header(None, alias="Authorization")) -> dict:
    """
    Делегирует проверку токена в app_auth.
    Требует заголовок: Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("[SYSTEMS] Отказано: отсутствует заголовок Authorization")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок: Authorization: Bearer <token>"
        )

    token = authorization.replace("Bearer ", "", 1).strip()

    # Используем переиспользуемый APIClient из core/
    client = APIClient(
        base_url=APP_AUTH_URL.rstrip('/'),
        timeout=5.0,
        max_retries=1,
        retry_backoff=0.5
    )
    try:
        async with client:
            # Вызываем эндпоинт, который внутри использует app_auth.dependencies.require_app_token
            response = await client.get(
                "/api/v1/auth/service/shared-data/",
                headers={"Authorization": f"Bearer {token}"}
            )
            logger.info(f"[SYSTEMS] Доступ подтверждён через app_auth: type={response.get('auth_type')}")
            return response
    except APIClientHTTPError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.details.get("detail", "Ошибка авторизации в app_auth")
        )
    except Exception as e:
        logger.error(f"[SYSTEMS] Ошибка связи с сервисом app_auth: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис авторизации временно недоступен"
        )



async def verify_app_systems_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_app_name: Optional[str] = Header(None, alias="X-App-Name")
) -> bool:
    """
    FastAPI Dependency для валидации межсервисного токена.
    Логика:
      1. Делегирование проверки в app_auth через HTTP (production)
      2. Фоллбэк на локальные токены из .env (development/graceful degradation)
    """
    # 1. Извлечение Bearer токена
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("[SYSTEMS] Отказано: отсутствует заголовок Authorization")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок: Authorization: Bearer <token>"
        )

    token = authorization.replace("Bearer ", "").strip()
    app_name = (x_app_name or "app_file_manager").strip()

    # 2. Проверка через HTTP-запрос к app_auth (используем переиспользуемый APIClient)
    try:
        client = APIClient(
            base_url=APP_AUTH_URL.rstrip('/'),
            timeout=5.0,
            max_retries=1,
            retry_backoff=0.5
        )
        async with client:
            response = await client.get(
                "/api/v1/auth/service/shared-data/",
                headers={"Authorization": f"Bearer {token}", "x-app-name": app_name}
            )
            if response.get("auth_type") in ("user", "app"):
                logger.info(f"[SYSTEMS] ✅ Доступ подтверждён через app_auth: type={response['auth_type']}")
                return True
    except APIClientHTTPError as e:
        # Логгируем, но НЕ прерываем — переходим к фоллбэку
        logger.warning(f"[SYSTEMS] ⚠️ app_auth вернул {e.status_code}: {e.details.get('detail')}")
    except Exception as e:
        logger.error(f"[SYSTEMS] ⚠️ Ошибка связи с app_auth: {e}", exc_info=True)

    # 3. Фоллбэк на локальные токены (.env) для независимой разработки
    if token in APP_TOKEN:
        logger.info(f"[SYSTEMS] 🔑 Валидация пройдена (локальный .env): '{app_name}'")
        return True

    # 4. Отказ в доступе
    logger.warning(f"[SYSTEMS] 🔒 Отказано в доступе: приложение '{app_name}', токен невалиден")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный токен приложения"
    )

