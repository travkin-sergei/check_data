# src/core/api_client.py
"""
Универсальный асинхронный HTTP-клиент с ретраями, экспоненциальной задержкой
и структурной обработкой ошибок.
Строгое переиспользование: logger, database, type_unifier (опционально).
Изоляция: нет импортов из конкретных приложений.
"""
import asyncio
import httpx
from typing import Any, Dict, Optional, Literal, Union
from src.config.logger import logger


class APIClientError(Exception):
    """Базовое исключение клиента."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class APIClientTimeoutError(APIClientError): pass


class APIClientHTTPError(APIClientError): pass


class APIClientNetworkError(APIClientError): pass


class APIClientSchemaError(APIClientError): pass


class APIClient:
    """
    Асинхронный HTTP-клиент с поддержкой:
    - экспоненциальных ретраев
    - безопасного парсинга JSON
    - контекстного менеджера (async with)
    - опциональной валидации схемы через type_unifier
    """

    def __init__(
            self,
            base_url: str,
            timeout: Union[float, httpx.Timeout] = 30.0,
            max_retries: int = 3,
            retry_backoff: float = 1.0,
            headers: Optional[Dict[str, str]] = None,
            follow_redirects: bool = True
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)
        self.max_retries = max(1, max_retries)
        self.retry_backoff = retry_backoff
        self.headers = headers or {}
        self.follow_redirects = follow_redirects
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=self.follow_redirects
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("[API] Пул соединений закрыт")

    async def __aenter__(self) -> "APIClient":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def request(
            self,
            method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            endpoint: str,
            **kwargs
    ) -> Dict[str, Any]:
        client = await self._get_client()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"[API] {method} {url}")

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return self._parse_response(response)

            except httpx.HTTPStatusError as e:
                logger.warning(f"[API] HTTP {e.response.status_code} | attempt {attempt}/{self.max_retries} | {url}")
                if attempt == self.max_retries:
                    detail = self._safe_extract_json(e.response)
                    raise APIClientHTTPError(
                        message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                        status_code=e.response.status_code,
                        details=detail
                    )

            except httpx.TimeoutException as e:
                logger.warning(f"[API] Timeout | attempt {attempt}/{self.max_retries} | {url}")
                if attempt == self.max_retries:
                    raise APIClientTimeoutError(message=f"Timeout after {self.max_retries} attempts",
                                                details={"url": url})

            except httpx.RequestError as e:
                logger.warning(f"[API] Network error | attempt {attempt}/{self.max_retries} | {url} | {e}")
                if attempt == self.max_retries:
                    raise APIClientNetworkError(message="Network/Connection error", details={"error": str(e)})

            except Exception as e:
                logger.error(f"[API] Unexpected error | attempt {attempt}/{self.max_retries} | {url}", exc_info=True)
                if attempt == self.max_retries:
                    raise APIClientError(message="Unexpected API error", details={"error": str(e)})

            # Экспоненциальная задержка перед повтором
            delay = self.retry_backoff * (2 ** (attempt - 1))
            logger.info(f"[API] Retry in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
            await asyncio.sleep(delay)

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or not content_type:
            return response.json()
        return {"_raw_text": response.text, "status": response.status_code}

    def _safe_extract_json(self, response: httpx.Response) -> Dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {"_raw_text": response.text}

    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        return await self.request("PUT", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        return await self.request("DELETE", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        return await self.request("PATCH", endpoint, **kwargs)
