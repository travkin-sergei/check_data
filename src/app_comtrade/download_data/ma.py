from config.logger import logger
from src.app_comtrade.download_data.registry import SourceRegistry


async def run_single_source(source_name: str):
    SourceClass = SourceRegistry.get(source_name)
    if not SourceClass:
        logger.info(f"Источник '{source_name}' не найден. Доступны: {SourceRegistry.list_available()}")
        return

    import os
    internal_token = os.getenv("APP_SYSTEMS_TOKEN")

    source = SourceClass(internal_token=internal_token)

    stats = await source.run(max_concurrent=5)
    logger.info(f"Результат: {stats}")


if __name__ == "__main__":
    import asyncio, sys

    source_name = sys.argv[1] if len(sys.argv) > 1 else "world_trade"
    asyncio.run(run_single_source(source_name))
