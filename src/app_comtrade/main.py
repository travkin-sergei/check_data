# src/app_comtrade/download_data/downloader.py
"""
Скачивание файлов из loadLinks и загрузка через /api/v1/systems/upload-file.
Изоляция: только стандартные библиотеки + httpx + src.config.*
Перед загрузкой проверяется наличие файла через /api/v1/systems/check-file-exists
"""
import asyncio
import httpx
import os
from pathlib import Path
from src.config.logger import logger
from src.app_comtrade.config import API_TOKEN, DOWNLOAD_TIMEOUT, MAX_CONCURRENT_DOWNLOADS, API_URL, INTERNAL_API_TOKEN

# === Конфигурация ===
EXTERNAL_ENDPOINT = "/api/v1/updates"
EXTERNAL_URL = API_URL + EXTERNAL_ENDPOINT

# Внутренний API (app_systems)
INTERNAL_HOST = os.getenv("INTERNAL_API_HOST", "127.0.0.1")
INTERNAL_PORT = os.getenv("INTERNAL_API_PORT", "8001")
INTERNAL_API_BASE = f"http://{INTERNAL_HOST}:{INTERNAL_PORT}/api/v1/systems"
INTERNAL_UPLOAD_ENDPOINT = f"{INTERNAL_API_BASE}/upload-file"
INTERNAL_CHECK_ENDPOINT = f"{INTERNAL_API_BASE}/check-file-exists"  # ✅ Новый эндпоинт


async def check_file_exists(file_path: str, internal_token: str | None = None) -> bool:
    """
    Проверяет наличие файла через /api/v1/systems/check-file-exists.
    Возвращает True, если файл существует, иначе False.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {}
        if internal_token:
            headers["Authorization"] = f"Bearer {internal_token}"
        try:
            response = await client.get(
                INTERNAL_CHECK_ENDPOINT,
                headers=headers,
                params={"file_path": file_path}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("exists", False)
            logger.warning(f"⚠️ Ошибка проверки файла {file_path}: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке существования {file_path}: {e}")
            return False  # При ошибке проверки продолжаем загрузку для надёжности


async def fetch_entities(url: str, token: str, entity: str) -> list | None:
    """Получение списка сущностей с loadLinks из ВНЕШНЕГО API."""
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {"entity": entity}
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Внешний API: {response.status_code} | {response.text[:200]}")
        return None


async def upload_to_internal_api(
        file_content: bytes,
        filename: str,
        target_dir: str,
        internal_token: str | None = None
) -> dict | None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {}
        if internal_token:
            headers["Authorization"] = f"Bearer {internal_token}"
        files = {"file": (filename, file_content, "application/octet-stream")}
        data = {"file_path": target_dir, "overwrite": "true"}
        try:
            response = await client.post(INTERNAL_UPLOAD_ENDPOINT, headers=headers, files=files, data=data)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Загружено: {filename} → {target_dir}/ ({result.get('file_size', 0)} B)")
                return result
            else:
                logger.error(f"❌ Internal API {response.status_code}: {response.text[:200]}")
                return None
        except httpx.ConnectError as e:
            logger.error(f"❌ Не удалось подключиться к внутреннему API ({INTERNAL_HOST}:{INTERNAL_PORT}): {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {filename}: {type(e).__name__}: {e}")
            return None


async def download_and_upload(
        external_url: str,
        external_token: str,
        filename: str,
        target_dir: str,
        semaphore: asyncio.Semaphore,
        internal_token: str | None = None
) -> str:  # ✅ Возвращает: "success", "failed", "exists"
    async with semaphore:
        full_path = f"{target_dir.rstrip('/')}/{filename}"

        # 1️⃣ Проверка существования файла перед скачиванием
        if await check_file_exists(full_path, internal_token):
            logger.info(f"✅ Файл уже существует: {full_path}, пропуск загрузки.")
            return "exists"

        # 2️⃣ Скачивание и загрузка
        try:
            async with httpx.AsyncClient(verify=False, timeout=DOWNLOAD_TIMEOUT) as client:
                headers = {"Authorization": f"Bearer {external_token}"}
                async with client.stream("GET", external_url, headers=headers) as resp:
                    resp.raise_for_status()
                    file_content = await resp.aread()

            result = await upload_to_internal_api(file_content, filename, target_dir, internal_token)
            return "success" if result is not None else "failed"
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP {e.response.status_code} при скачивании {external_url}")
            return "failed"
        except MemoryError:
            logger.error(f"❌ Недостаточно памяти для файла {filename}")
            return "failed"
        except Exception as e:
            logger.error(f"❌ Ошибка {type(e).__name__}: {e} | {filename}")
            return "failed"


async def process_load_links(
        token: str,
        entities: list,
        source_name: str,
        source_date: str,
        source_info: str = '',
        max_concurrent: int = MAX_CONCURRENT_DOWNLOADS,
        internal_token: str | None = None
) -> dict:
    """Перебор loadLinks: проверка -> скачивание -> загрузка через внутренний API."""
    stats = {"success": 0, "failed": 0, "skipped": 0, "total": 0}
    base_target_path = f"{source_name}/{source_date}/{source_info}".strip("/")
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []

    for entity in entities:
        for link_info in entity.get("loadLinks", []):
            stats["total"] += 1
            if isinstance(link_info, str):
                url, filename = link_info, Path(link_info).name
            elif isinstance(link_info, dict):
                url = link_info.get("url") or link_info.get("link")
                filename = link_info.get("filename") or (Path(url).name if url else f"file_{stats['total']}")
            else:
                logger.warning(f"Неизвестный формат link_info: {type(link_info)}")
                stats["failed"] += 1
                continue

            if not url:
                logger.warning(f"⚠️ Нет URL в link_info: {link_info}")
                stats["failed"] += 1
                continue

            logger.info(f"[{stats['total']}] В очереди: {filename} → {base_target_path}/")
            task = asyncio.create_task(
                download_and_upload(
                    external_url=url,
                    external_token=token,
                    filename=filename,
                    target_dir=base_target_path,
                    semaphore=semaphore,
                    internal_token=internal_token
                ),
                name=f"up_{filename}"
            )
            tasks.append(task)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                stats["failed"] += 1
            elif result == "exists":
                stats["skipped"] += 1
            elif result == "success":
                stats["success"] += 1
            else:
                stats["failed"] += 1

    return stats


async def main():
    """Точка входа."""
    external_token = API_TOKEN
    internal_token = INTERNAL_API_TOKEN

    if not external_token:
        logger.error("Внешний токен (API_TOKEN) не задан")
        return

    logger.info(f"Запуск: внешний API → внутренний API ({INTERNAL_UPLOAD_ENDPOINT})")
    logger.info(f"Конкурентность: {MAX_CONCURRENT_DOWNLOADS}, таймаут: {DOWNLOAD_TIMEOUT}с")

    entities = await fetch_entities(EXTERNAL_URL, external_token, "API-COMTRADE-WORLD_TRADE-1")
    if not entities:
        logger.error("Не удалось получить список сущностей")
        return

    logger.info(f"Найдено сущностей: {len(entities)}")
    stats = await process_load_links(
        token=external_token,
        entities=entities,
        source_name="comtrade",
        source_date="2025-04-01",
        internal_token=internal_token
    )
    logger.info(
        f"Итого: всего={stats['total']}, ✅успешно={stats['success']}, ⏭️пропущено={stats['skipped']}, ❌ошибок={stats['failed']}")


if __name__ == "__main__":
    from src.config.logger import config_logging

    config_logging(level="INFO")
    asyncio.run(main())