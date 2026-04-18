# src/core/data_checker.py
"""
Общий сервис проверки наличия данных и извлечения дат.
Переиспользуется всеми приложениями проекта.

Зависимости:
- src.config.logger (строгое переиспользование)
"""
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any, Set, Optional

from src.config.logger import logger


class DataChecker:
    """
    Общий сервис для проверки папок и извлечения метаданных.
    Переиспользуется в app_file_manager, app_macmap, app_groups и других модулях.
    """

    # === Константы ===
    DEFAULT_DATE_PATTERN: str = r'^\d{4}-\d{2}-\d{2}$'  # YYYY-MM-DD

    @staticmethod
    def _has_files_recursive(folder_path: Path) -> bool:
        """
        Рекурсивно проверяет наличие файлов в папке и подпапках.

        Args:
            folder_path: Путь к папке

        Returns:
            bool: True если найден хотя бы один файл
        """
        if not folder_path.exists() or not folder_path.is_dir():
            return False

        try:
            for item in folder_path.iterdir():
                if item.is_file():
                    return True
                if item.is_dir():
                    if DataChecker._has_files_recursive(item):
                        return True
        except PermissionError:
            logger.warning(f"Нет прав доступа: {folder_path}")
            return False
        except Exception as e:
            logger.error(f"Ошибка обхода: {e}")
            return False

        return False

    @staticmethod
    async def check_data_list(base_url: Path,
                              folders: List[str]) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверяет наличие папок и файлов в них (рекурсивно).

        Args:
            base_url: Базовый путь к данным
            folders: Список имён папок для проверки

        Returns:
            Tuple[bool, Dict]:
                - success: True если все проверки пройдены
                - result: {
                    'missing': [отсутствующие папки],
                    'empty': [пустые папки],
                    'found': [папки с файлами]
                  }
        """
        missing = []
        empty = []
        found = []

        for folder in folders:
            full_path = base_url / folder
            logger.info(f"Проверка: {full_path}")

            # === Проверка существования папки ===
            if not full_path.exists() or not full_path.is_dir():
                logger.warning(f"Папка не найдена: {folder}")
                missing.append(folder)
                continue

            # === Проверка наличия файлов (рекурсивно) ===
            has_files = DataChecker._has_files_recursive(full_path)

            if not has_files:
                logger.warning(f"📭 Папка пуста: {folder}")
                empty.append(folder)
            else:
                logger.info(f"Папка содержит файлы: {folder}")
                found.append(folder)

        # === Формируем результат ===
        success = len(missing) == 0 and len(empty) == 0
        result = {
            'missing': missing,
            'empty': empty,
            'found': found
        }

        if missing:
            logger.error(f"Не найдено: {missing}")
        if empty:
            logger.warning(f"Пустые: {empty}")
        if success:
            logger.info(f"Все {len(folders)} папок проверены")

        return success, result

    @staticmethod
    async def extract_dates_from_folders(
            base_url: Path,
            subfolder: str,
            date_pattern: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Извлекает даты из имён подпапок.

        Args:
            base_url: Базовый путь (из конфига)
            subfolder: Подпапка для сканирования (из LIST_FOLDER)
            date_pattern: Regex для поиска дат (по умолчанию ISO формат)

        Returns:
            Tuple[bool, Dict]:
                - success: True если папка найдена и доступна
                - result: {
                    'dates': [список найденных дат],
                    'total': количество,
                    'path': проверенный путь,
                    'error': сообщение об ошибке (если есть)
                  }
        """
        pattern = date_pattern or DataChecker.DEFAULT_DATE_PATTERN
        result = {
            'dates': [],
            'total': 0,
            'path': str(base_url / subfolder),
            'error': None
        }

        target_path = base_url / subfolder
        logger.info(f"Сканирование папок для дат: {target_path}")

        # === Проверка существования ===
        if not target_path.exists():
            logger.warning(f"Папка не найдена: {target_path}")
            result['error'] = f"Папка не найдена: {subfolder}"
            return False, result

        if not target_path.is_dir():
            logger.warning(f"Объект не является папкой: {target_path}")
            result['error'] = f"Не является папкой: {subfolder}"
            return False, result

        # === Поиск дат в именах подпапок ===
        dates: Set[str] = set()
        date_regex = re.compile(pattern)

        try:
            for item in target_path.iterdir():
                if item.is_dir():
                    folder_name = item.name
                    if date_regex.match(folder_name):
                        dates.add(folder_name)
                        logger.debug(f"Найдена дата: {folder_name}")
        except PermissionError:
            logger.error(f"Нет прав доступа: {target_path}")
            result['error'] = "Нет прав доступа"
            return False, result
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}")
            result['error'] = f"Ошибка: {str(e)}"
            return False, result

        # === Сортировка и возврат ===
        sorted_dates = sorted(dates)
        result['dates'] = sorted_dates
        result['total'] = len(sorted_dates)

        logger.info(f"Найдено {len(sorted_dates)} дат: {sorted_dates}")
        return True, result

    @staticmethod
    def validate_dataset(dataset: str) -> Tuple[bool, Optional[str]]:
        """
        Закладка на валидацию папки
        """

        return True, None
