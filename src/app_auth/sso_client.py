# src/app_auth/sso_client.py
import httpx
from typing import Optional, Tuple
from src.config.logger import logger
from src.app_auth.config import settings


class SSOClient:
    """Клиент для внешнего SSO-провайдера (Roox-style OAuth2)."""

    def __init__(self):
        self.token_url = settings.SSO_TOKEN_URL
        self.client_id = settings.SSO_CLIENT_ID
        self.client_secret = settings.SSO_CLIENT_SECRET
        self.realm = settings.SSO_REALM
        self.service = settings.SSO_SERVICE

    async def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Выполняет двухшаговую аутентификацию пользователя через SSO.
        Возвращает (успех, access_token, payload_данные_пользователя).
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Шаг 1: получение execution
            payload1 = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'realm': self.realm,
                'grant_type': 'urn:roox:params:oauth:grant-type:m2m',
                'service': self.service,
            }
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            try:
                resp1 = await client.post(self.token_url, data=payload1, headers=headers)
                resp1.raise_for_status()
                data1 = resp1.json()
                execution = data1.get('execution')
                if not execution:
                    logger.error(f"[SSO] Не получен execution: {data1}")
                    return False, None, None
            except Exception as e:
                logger.error(f"[SSO] Ошибка шага 1: {e}")
                return False, None, None

            # Шаг 2: отправка учётных данных пользователя
            payload2 = {
                **payload1,
                '_eventId': 'next',
                'username': username,
                'password': password,
                'execution': execution
            }

            try:
                resp2 = await client.post(self.token_url, data=payload2, headers=headers)
                resp2.raise_for_status()
                data2 = resp2.json()
                access_token = data2.get('access_token')
                if not access_token:
                    logger.error(f"[SSO] Нет access_token в ответе: {data2}")
                    return False, None, None

                # Дополнительно можно извлечь информацию о пользователе (если есть)
                user_info = {
                    'external_id': data2.get('user_id'),
                    'username': username,
                    # другие поля из ответа SSO
                }

                logger.info(f"[SSO] Пользователь {username} успешно аутентифицирован")
                return True, access_token, user_info

            except httpx.HTTPStatusError as e:
                logger.warning(f"[SSO] Неверные учётные данные для {username}: {e.response.status_code}")
                return False, None, None
            except Exception as e:
                logger.error(f"[SSO] Ошибка шага 2: {e}")
                return False, None, None

    async def validate_token(self, token: str) -> bool:
        """
        Проверяет валидность внешнего токена.
        Если SSO предоставляет эндпоинт /introspect — использовать его.
        В данном примере заглушка.
        """
        # В вашем примере нет интроспекции, поэтому просто считаем, что токен валиден,
        # если он не пустой и имеет префикс sso_1.0_
        return token.startswith('sso_1.0_') and len(token) > 20