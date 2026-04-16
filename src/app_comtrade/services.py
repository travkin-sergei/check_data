# src/app_comtrade/services.py
"""
Простой и надёжный инструмент для загрузки файлов в app_systems.
Логика: валидация пути → проверка существования → загрузка.
Изоляция: только httpx + src.config.*
"""
import httpx
from typing import Optional, Union

from src.config.logger import logger
from src.app_comtrade.config import (
    INTERNAL_API_BASE,
    INTERNAL_UPLOAD_ENDPOINT,
    INTERNAL_API_TOKEN,
    DOWNLOAD_TIMEOUT,
    ALLOWED_SUFFIXES, INTERNAL_CHECK_ENDPOINT,
)


class FileUploader:
    """
    Клиент для безопасной загрузки файлов в app_systems.

    Пример использования:
        uploader = FileUploader(internal_token="...")
        result = await uploader.upload(
            source="comtrade",
            date="2025-04-01",
            filename="app_database.parquet",
            file_content=b"...",  # bytes
            extra_path="world_trade"  # опционально
        )
    """

    def __init__(self):
        self.internal_token = INTERNAL_API_TOKEN
        self.base_url = INTERNAL_API_BASE
        self.upload_endpoint = INTERNAL_UPLOAD_ENDPOINT
        self.check_endpoint = INTERNAL_CHECK_ENDPOINT

    def _build_file_path(self, source: str, date: str, filename: str,
                         extra_path: Optional[str] = None) -> str:
        """
        Формирует целевой путь: {source}/{extra_path}/{date}/{filename}
        """
        parts = [source]
        if extra_path and extra_path.strip():
            parts.append(extra_path.strip("/"))
        parts.append(date)
        parts.append(filename)
        return "/".join(p for p in parts if p)

    def _validate_filename(self, filename: str) -> tuple[bool, str]:
        """Проверяет, что передано имя файла, а не путь/директория."""
        if not filename or not isinstance(filename, str):
            return False, "Имя файла не указано или не является строкой"

        # Запрещаем пути с разделителями — только имя файла
        if "/" in filename or "\\" in filename:
            return False, f"Ожидается имя файла, а не путь: '{filename}'"

        # Базовая проверка расширения
        if "." not in filename:
            return False, f"Файл должен иметь расширение: '{filename}'"

        return True, ""

    async def _check_exists(self, file_path: str) -> tuple[bool, Optional[dict]]:
        """
        Проверяет существование файла через app_systems API.
        Returns: (exists: bool, response_data: dict|None)
        """
        params = {"file_path": file_path}
        for suf in ALLOWED_SUFFIXES:
            params["suffix"] = suf

        headers = {}
        if self.internal_token:
            headers["Authorization"] = f"Bearer {self.internal_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.check_endpoint, headers=headers, params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    exists = data.get("exists", False)
                    if exists:
                        size = data.get("file_size")
                        logger.info(f"Файл уже существует: {file_path} ({size} B)")
                    return exists, data
                else:
                    logger.warning(f"HTTP {resp.status_code} при проверке {file_path}")
                    return False, None

        except httpx.ConnectError:
            logger.warning(f"Не удалось подключиться к app_systems для проверки {file_path}")
            return False, None  # Продолжаем загрузку, если проверка недоступна
        except Exception as e:
            logger.debug(f"Ошибка проверки {file_path}: {type(e).__name__}: {e}")
            return False, None

    async def _upload(self, file_path: str, file_content: bytes, filename: str,
                      overwrite: bool = False) -> tuple[bool, dict]:
        """
        Загружает файл через app_systems API.
        Returns: (success: bool, result: dict)
        """
        headers = {}
        if self.internal_token:
            headers["Authorization"] = f"Bearer {self.internal_token}"

        files = {"file": (filename, file_content, "application/octet-stream")}
        data = {"file_path": file_path, "overwrite": str(overwrite).lower()}

        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
                resp = await client.post(
                    self.upload_endpoint,
                    headers=headers,
                    files=files,
                    data=data
                )

                if resp.status_code == 200:
                    result = resp.json()
                    logger.info(f"Загружено: {filename} → {file_path}/ ({result.get('file_size', 0)} B)")
                    return True, result
                else:
                    error_text = resp.text[:200] if resp.text else "No content"
                    logger.error(f"Ошибка загрузки {filename}: HTTP {resp.status_code} | {error_text}")
                    return False, {"error": f"HTTP {resp.status_code}: {error_text}"}

        except httpx.ConnectError as e:
            logger.error(f"Не удалось подключиться к app_systems: {e}")
            return False, {"error": f"Connection error: {e}"}
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {type(e).__name__}: {e}")
            return False, {"error": f"{type(e).__name__}: {e}"}

    async def upload(self,
                     source: str,
                     date: str,
                     filename: str,
                     file_content: Union[bytes, bytearray],
                     extra_path: Optional[str] = None,
                     overwrite: bool = False) -> dict:
        """
        Полный цикл: валидация → проверка → загрузка.

        Args:
            source: Имя источника (например, "comtrade")
            date: Дата в формате "YYYY-MM-DD"
            filename: Имя файла (только имя, без пути!)
            file_content: Содержимое файла в байтах
            extra_path: Дополнительный путь (например, "world_trade")
            overwrite: Разрешить перезапись (по умолчанию False)

        Returns:
            dict с результатом:
            {
                "success": bool,
                "status": "uploaded" | "skipped" | "failed",
                "file_path": str,
                "message": str,
                "details": dict  # опционально
            }
        """
        # 1. Валидация имени файла
        valid, error_msg = self._validate_filename(filename)
        if not valid:
            logger.error(f"Валидация не пройдена: {error_msg}")
            return {
                "success": False,
                "status": "failed",
                "file_path": None,
                "message": f"Invalid filename: {error_msg}",
                "details": {"filename": filename}
            }

        # 2. Формируем целевой путь
        file_path = self._build_file_path(source, date, filename, extra_path)
        logger.debug(f"Целевой путь: {file_path}")

        # 3. Проверяем существование (только если не разрешена перезапись)
        if not overwrite:
            exists, check_data = await self._check_exists(file_path)
            if exists:
                return {
                    "success": True,
                    "status": "skipped",
                    "file_path": file_path,
                    "message": "Файл уже существует, загрузка пропущена",
                    "details": check_data
                }

        # 4. Загружаем файл
        success, result = await self._upload(file_path, file_content, filename, overwrite)

        if success:
            return {
                "success": True,
                "status": "uploaded",
                "file_path": file_path,
                "message": "Файл успешно загружен",
                "details": result
            }
        else:
            return {
                "success": False,
                "status": "failed",
                "file_path": file_path,
                "message": result.get("error", "Unknown upload error"),
                "details": result
            }
