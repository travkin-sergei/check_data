"""
Бизнес-логика app_servises.
Строгое переиспользование: logger, DBManager, DataChecker
Изоляция: импорты только из src.config.* и src.app_servises.*
"""
import re
import asyncio
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

# 🔹 Строгое переиспользование зависимостей проекта
from src.config.logger import logger
from src.app_database.manager import DBManager  # ✅ asyncpg пулы
from src.core.data_checker import DataChecker  # ✅ общая логика проверки

# Компилируем паттерн один раз для производительности
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AppDataChecker:
    """Сервис проверки источников данных для app_servises."""

    @staticmethod
    async def check_folders_last_update(
            folders: List[str],
            base_path: Path
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Асинхронно проверяет папки и ищет подпапки с датами YYYY-MM-DD.
        Возвращает максимальную найденную дату для каждой папки.
        Формат ответа: [{"folder": "...", "last_update_date": "YYYY-MM-DD", "status": "..."}]
        """
        results = []

        for folder_name in folders:
            full_path = base_path / folder_name

            if not full_path.exists() or not full_path.is_dir():
                logger.warning(f"[SERVICES] Папка не найдена: {folder_name}")
                results.append({"folder": folder_name, "last_update_date": None, "status": "missing"})
                continue

            max_date = None
            try:
                # Сканируем в пуле потоков, чтобы не блокировать event loop
                def scan_dates():
                    nonlocal max_date
                    for item in full_path.iterdir():
                        if item.is_dir() and DATE_RE.match(item.name):
                            try:
                                dt = datetime.strptime(item.name, "%Y-%m-%d")
                                if max_date is None or dt > max_date:
                                    max_date = dt
                            except ValueError:
                                continue

                await asyncio.to_thread(scan_dates)

            except PermissionError as e:
                logger.error(f"[SERVICES] Ошибка доступа к {folder_name}: {e}")
                results.append({"folder": folder_name, "last_update_date": None, "status": "error"})
                continue

            if max_date:
                results.append({
                    "folder": folder_name,
                    "last_update_date": max_date.strftime("%Y-%m-%d"),
                    "status": "found"
                })
            else:
                logger.info(f"[SERVICES] В папке {folder_name} нет подпапок с датами")
                results.append({"folder": folder_name, "last_update_date": None, "status": "empty"})

        return True, results

    @staticmethod
    async def get_sources_from_db(db_alias: str = "app_servises") -> List[str]:
        """
        Получает список активных источников из БД.
        Таблица: app_servises.data_sources(folder_path, is_active)
        """
        try:
            pool = await DBManager().get_pool(db_alias)
            query = """
                SELECT folder_path 
                FROM app_servises.data_sources 
                WHERE is_active = TRUE 
                  AND folder_path IS NOT NULL 
                  AND folder_path != ''
                ORDER BY name
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(query)
                # Возвращаем уникальные непустые пути
                sources = list({row["folder_path"].strip() for row in rows if row["folder_path"]})
                logger.info(f"[SERVICES] Загружено {len(sources)} источников из БД '{db_alias}'")
                return sources
        except Exception as e:
            logger.error(f"[SERVICES] Ошибка получения источников из БД: {e}")
            return []

    @staticmethod
    async def check_sources_from_db(
            base_path: Path,
            db_alias: str = "app_servises",
            limit: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Получает источники из БД и проверяет их через общую логику.
        Возвращает формат, совместимый с CheckDataResponse.
        """
        # 1. Получаем список из БД
        folders = await AppDataChecker.get_sources_from_db(db_alias)
        if not folders:
            logger.warning("[SERVICES] В БД нет активных источников для проверки")
            return True, {"missing": [], "empty": [], "found": [], "from_db": True}

        # 2. Применяем лимит
        if limit and limit > 0:
            folders = folders[:limit]

        # 3. Делегируем общей логике (строгое переиспользование core/data_checker)
        logger.info(f"[SERVICES] Проверка {len(folders)} источников из БД")
        success, result = await DataChecker.check_data_list(base_url=base_path, folders=folders)

        # 4. Добавляем даты для найденных папок (как в /check-data)
        found_with_dates = await AppDataChecker._get_dates_for_found(result.get("found", []), base_path)
        result["found"] = found_with_dates
        result["from_db"] = True

        return success, result

    @staticmethod
    async def _get_dates_for_found(
            folders: List[str],
            root_dir: Path
    ) -> List[Dict[str, Optional[str]]]:
        """Возвращает [{папка: дата_или_None}, ...] для найденных папок."""
        if not folders:
            return []

        async def find_max_date(folder: str) -> Dict[str, Optional[str]]:
            full_path = root_dir / folder
            if not full_path.is_dir():
                return {folder: None}
            max_dt, max_name = None, None
            for item in full_path.iterdir():
                if item.is_dir() and DATE_RE.match(item.name):
                    try:
                        dt = datetime.strptime(item.name, "%Y-%m-%d")
                        if max_dt is None or dt > max_dt:
                            max_dt, max_name = dt, item.name
                    except ValueError:
                        continue
            return {folder: max_name}  # возвращаем имя подпапки-даты

        tasks = [find_max_date(f) for f in folders]
        return await asyncio.gather(*tasks)
