# src/app_comtrade/download_data/sources/world_trade.py
"""
Источник: World Trade.
Простая логика: получить список → скачать → проверить → загрузить.
Путь в хранилище: ENTITY_NAME / DATE / FILENAME
"""
import asyncio
import httpx
from pathlib import Path

from src.config.logger import logger, config_logging
from src.app_comtrade.config import (
    API_URL,
    API_TOKEN,
    MAX_CONCURRENT_DOWNLOADS,
    DOWNLOAD_TIMEOUT,
)
from src.app_comtrade.services import FileUploader

ENTITY_NAME = "API-COMTRADE-WORLD_TRADE-1"
API_ENDPOINT = "/api/v1/updates"
TEST_DATE = "2026-04-11"


async def fetch_file_list(base_url: str, token: str, entity: str) -> list[dict]:
    """Получает список файлов из внешнего API."""
    full_url = f"{base_url.rstrip('/')}{API_ENDPOINT}"
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        resp = await client.get(full_url, headers={"Authorization": f"Bearer {token}"}, params={"entity": entity})
        resp.raise_for_status()

        files = []
        for ent in resp.json():
            for link in ent.get("loadLinks", []):
                url_val = link if isinstance(link, str) else (link.get("url") or link.get("link"))
                if url_val:
                    fname = Path(url_val).name if isinstance(link, str) else (link.get("filename") or Path(url_val).name)
                    files.append({"url": url_val, "filename": fname})
        return files


async def process_file(file_info: dict, date: str, uploader: FileUploader, ext_token: str, sem: asyncio.Semaphore) -> str:
    """Скачивает один файл и загружает его через FileUploader."""
    async with sem:
        try:
            async with httpx.AsyncClient(verify=False, timeout=DOWNLOAD_TIMEOUT) as client:
                resp = await client.get(file_info["url"], headers={"Authorization": f"Bearer {ext_token}"})
                resp.raise_for_status()
                content = resp.content
        except Exception as e:
            logger.error(f"Сбой скачивания {file_info['filename']}: {e}")
            return "failed"

        # extra_path=None → путь будет строго: ENTITY_NAME / DATE / FILENAME
        res = await uploader.upload(
            source=ENTITY_NAME,
            date=date,
            filename=file_info["filename"],
            file_content=content,
            extra_path=None
        )
        return "uploaded" if res["status"] == "uploaded" else ("skipped" if res["status"] == "skipped" else "failed")


async def run():
    if not all([API_URL, API_TOKEN]):
        logger.error("Не заданы API_URL или API_TOKEN в .env")
        return

    logger.info(f"Запуск: {ENTITY_NAME} за {TEST_DATE}")
    try:
        files = await fetch_file_list(API_URL, API_TOKEN, ENTITY_NAME)
    except Exception as e:
        logger.error(f"Не получен список файлов: {e}")
        return

    if not files:
        logger.warning("Список файлов пуст")
        return

    logger.info(f"Найдено файлов: {len(files)}")
    uploader = FileUploader()
    sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    tasks = [process_file(f, TEST_DATE, uploader, API_TOKEN, sem) for f in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    stats = {"uploaded": 0, "skipped": 0, "failed": 0}
    for r in results:
        if r == "uploaded": stats["uploaded"] += 1
        elif r == "skipped": stats["skipped"] += 1
        else: stats["failed"] += 1

    logger.info(f"Итог: {stats}")


if __name__ == "__main__":
    config_logging(level="INFO")
    asyncio.run(run())