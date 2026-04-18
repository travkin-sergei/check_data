# src/app_file_manager/services.py
"""
Бизнес-логика app_file_manager.
- Строгое переиспользование: logger, database, type_unifier
- Изоляция: нет прямых импортов core.*config
"""
import csv
import io
import json
import re
import asyncio
import hashlib
import duckdb
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from typing import List, Tuple, Dict, Any, Optional, Set

from src.app_file_manager.config import DATA_ROOT_DIR
from src.config.database import DBManager
from src.config.logger import logger
from src.core.data_checker import DataChecker
from src.core.type_unifier import SchemaComparator


class AppDataChecker:
    """Сервис проверки и извлечения метаданных файлов."""

    _comparator = SchemaComparator()

    EXCLUDED_FOLDERS: Set[str] = {
        '.git', '__pycache__', '.venv', 'venv', 'node_modules',
        '.idea', '.vscode', 'logs', 'tmp', 'temp', '.cache',
        '.pytest_cache', '.mypy_cache', 'dist', 'build', 'egg-info'
    }

    # === Утилиты ===
    @staticmethod
    def _paginate_list(items: list, page: int, page_size: int) -> Dict[str, Any]:
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": end < total,
            "has_prev": page > 1,
            "total_pages": max(1, (total + page_size - 1) // page_size)
        }

    @staticmethod
    @lru_cache(maxsize=256)
    def _map_duckdb_type_cached(duckdb_type: str) -> str:
        if not duckdb_type:
            return "VARCHAR"
        return AppDataChecker._comparator._normalize_type(
            duckdb_type,
            SchemaComparator.TYPE_MAPPING.get('duckdb', {})
        )

    @staticmethod
    def _detect_file_type(path: Path) -> str:
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
            if header == b'PAR1':
                return 'parquet'
        except (OSError, IOError):
            pass
        name = path.name.lower()
        for suffix in ['.sended', '.processed', '.tmp', '.bak']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        ext = Path(name).suffix.lower()
        type_map = {
            '.parquet': 'parquet',
            '.csv': 'csv', '.txt': 'csv', '.tsv': 'csv',
            '.json': 'json', '.jsonl': 'json', '.ndjson': 'json'
        }
        return type_map.get(ext, 'csv')

    @staticmethod
    def _parse_null_flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().upper() in ('YES', 'TRUE', '1', 'T')
        return True

    # === Чтение схем ===
    @staticmethod
    def _read_schema_generic(query: str) -> Dict[str, Dict[str, Any]]:
        con = duckdb.connect()
        try:
            result = con.execute(query).fetchall()
            schema = {}
            for row in result:
                col_name = row[0]
                col_type_raw = row[1]
                col_null_raw = row[2] if len(row) > 2 else 'YES'
                schema[col_name] = {
                    "type": AppDataChecker._map_duckdb_type_cached(col_type_raw),
                    "null": AppDataChecker._parse_null_flag(col_null_raw)
                }
            return schema
        finally:
            con.close()

    @staticmethod
    def _read_parquet_schema_duckdb(path: Path) -> Dict[str, Dict[str, Any]]:
        query = f"DESCRIBE (SELECT * FROM read_parquet('{path.as_posix()}'))"
        return AppDataChecker._read_schema_generic(query)

    @staticmethod
    def _read_json_schema_duckdb(path: Path) -> Dict[str, Dict[str, Any]]:
        query = f"DESCRIBE (SELECT * FROM read_json_auto('{path.as_posix()}'))"
        return AppDataChecker._read_schema_generic(query)

    @staticmethod
    def _read_csv_schema_duckdb(path: Path) -> Dict[str, Dict[str, Any]]:
        query = f"DESCRIBE (SELECT * FROM read_csv_auto('{path.as_posix()}'))"
        return AppDataChecker._read_schema_generic(query)

    @staticmethod
    def _read_text_schema_as_varchar(path: Path) -> Dict[str, Dict[str, Any]]:
        encodings = ['utf-8-sig', 'cp1251', 'windows-1252', 'latin-1']
        sample_text = None
        used_enc = 'utf-8-sig'
        for enc in encodings:
            try:
                with open(path, 'r', encoding=enc, newline='') as f:
                    sample_text = f.read(4096)
                used_enc = enc
                break
            except UnicodeDecodeError:
                continue
            except OSError as e:
                logger.error(f"Ошибка доступа к файлу {path.name}: {e}")
                raise
        if not sample_text:
            raise ValueError(f"Не удалось прочитать {path.name} в поддерживаемых кодировках")
        if used_enc != 'utf-8-sig':
            logger.warning(f"Файл {path.name} прочитан с резервной кодировкой: {used_enc}")
        sample_text = sample_text.replace('\r\n', '\n').replace('\r', '\n')
        try:
            dialect = csv.Sniffer().sniff(sample_text, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        try:
            reader = csv.reader(io.StringIO(sample_text), dialect)
            headers = next(reader, [])
            clean_headers = [h.strip().strip('"\'') for h in headers if h.strip()]
            if not clean_headers:
                raise ValueError("Файл не содержит валидных заголовков или пуст")
            logger.debug(f"Извлечены заголовки ({len(clean_headers)} полей) из {path.name}, кодировка: {used_enc}")
            return {col: {"type": "VARCHAR", "null": True} for col in clean_headers}
        except StopIteration:
            raise ValueError("Файл пуст")
        except csv.Error as e:
            raise ValueError(f"Ошибка формата CSV/TXT: {e}")

    # === Сканирование директорий ===
    @staticmethod
    async def get_available_folders(root_dir: Path,
                                    folder_path: Optional[str] = None,
                                    pattern: Optional[str] = None,
                                    page: int = 1,
                                    page_size: int = 50) -> Tuple[bool, Dict[str, Any]]:
        try:
            target_dir = (root_dir / folder_path).resolve() if folder_path else root_dir.resolve()
            if not str(target_dir).startswith(str(root_dir.resolve())):
                return False, {'error': 'Доступ запрещён: путь выходит за пределы корневой директории'}
            if not target_dir.exists() or not target_dir.is_dir():
                return False, {'error': f'Директория не найдена: {folder_path or "root"}'}
            date_regex = re.compile(pattern) if pattern else None
            items = []
            excluded_count = 0
            for item in target_dir.iterdir():
                if item.name in AppDataChecker.EXCLUDED_FOLDERS or item.name.startswith('.'):
                    excluded_count += 1
                    continue
                if date_regex and not date_regex.match(item.name):
                    continue
                items.append({"path": item.name, "type": "folder" if item.is_dir() else "file"})
            items.sort(key=lambda x: (0 if x["type"] == "folder" else 1, x["path"]))
            pagination = AppDataChecker._paginate_list(items, page, page_size)
            folders_page = [i["path"] for i in pagination["items"] if i["type"] == "folder"]
            files_page = [i["path"] for i in pagination["items"] if i["type"] == "file"]
            logger.info(f"[SCAN] path='{folder_path or 'root'}', pattern='{pattern}', "
                        f"всего: {pagination['total']}, папок: {len(folders_page)}, файлов: {len(files_page)}")
            return True, {
                'folders': folders_page, 'files': files_page, 'total': pagination['total'],
                'page': page, 'page_size': page_size, 'has_next': pagination['has_next'],
                'has_prev': pagination['has_prev'], 'excluded': excluded_count,
                'current_path': folder_path or '', 'applied_pattern': pattern, 'error': None
            }
        except re.error as e:
            logger.error(f"Невалидный regex pattern: {pattern}. Ошибка: {e}")
            return False, {'error': f'Невалидный regex: {e}'}
        except Exception as e:
            logger.error(f"Ошибка сканирования директории: {e}", exc_info=True)
            return False, {'error': str(e)}

    # === Извлечение схемы ===
    @staticmethod
    def _extract_schema_blocking(file_path: str, base: Path, detected_type: str) -> Dict[str, Dict[str, Any]]:
        full_path = (base / file_path).resolve()
        try:
            full_path.relative_to(base)
        except ValueError:
            raise PermissionError(f"Путь {file_path} выходит за пределы {base}")
        if not full_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        if not full_path.is_file():
            raise ValueError(f"Путь не является файлом: {file_path}")
        match detected_type:
            case "parquet":
                return AppDataChecker._read_parquet_schema_duckdb(full_path)
            case "csv":
                return AppDataChecker._read_csv_schema_duckdb(full_path)
            case "json":
                return AppDataChecker._read_json_schema_duckdb(full_path)
            case _:
                raise ValueError(f"Неподдерживаемый тип файла: {full_path.suffix}")

    @staticmethod
    def extract_file_schema_sync(file_path: str) -> Tuple[bool, Dict[str, Any]]:
        try:
            base = Path(DATA_ROOT_DIR).resolve()
            full_path = (base / file_path).resolve()
            detected_type = AppDataChecker._detect_file_type(full_path)
            schema = AppDataChecker._extract_schema_blocking(file_path, base, detected_type)
            logger.info(f"Схема извлечена ({detected_type}): {len(schema)} полей, файл={file_path}")
            return True, {"schema": schema, "file_type": detected_type, "field_count": len(schema)}
        except (PermissionError, FileNotFoundError, ValueError) as e:
            logger.warning(f"Ошибка валидации: {e}")
            return False, {"error": str(e)}
        except duckdb.Error as e:
            logger.error(f"Ошибка DuckDB: {e}")
            return False, {"error": f"DuckDB: {str(e)}"}
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
            return False, {"error": str(e)}

    @staticmethod
    async def _log_extraction_to_db(file_path: str, schema: dict, file_type: str) -> bool:
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                logger.debug("Нет event loop — синхронное логирование в БД пропущено")
                return False
            db_conn = DBManager.get_connection("base_01")
            if not db_conn or not db_conn.is_initialized:
                logger.debug("БД не инициализирована, логирование пропущено")
                return False
            with db_conn.get_cursor(commit=True) as cur:
                cur.execute(
                    """INSERT INTO schema_extraction_log 
                       (file_path, file_type, schema_json, extracted_at) 
                       VALUES (%s, %s, %s, NOW())""",
                    (file_path, file_type, json.dumps(schema, ensure_ascii=False))
                )
            logger.debug(f"Схема залогирована в БД: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка записи в БД: {e}", exc_info=True)
            return False

    @staticmethod
    async def extract_file_schema(file_path: str) -> Tuple[bool, Dict[str, Any]]:
        success, result = await asyncio.to_thread(
            AppDataChecker.extract_file_schema_sync, file_path
        )
        if success and result.get("schema"):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    AppDataChecker._log_extraction_to_db(
                        file_path, result["schema"], result.get("file_type", "unknown")
                    ),
                    name=f"log_schema_{Path(file_path).name}"
                )
            except RuntimeError:
                logger.debug("Нет event loop для фоновой записи в БД")
        return success, result

    # === Проверка данных (делегирование) ===
    @staticmethod
    async def check_comtrade_data(base_url: Path,
                                  folders: Optional[List[str]] = None) -> Tuple[bool, Dict[str, Any]]:
        folders = folders or None
        logger.debug(f"Проверка папок: {folders}")
        return await DataChecker.check_data_list(base_url=base_url, folders=folders)

    # === Загрузка файла ===
    @staticmethod
    async def upload_file_to_storage(file_path: str,
                                     file_content: bytes,
                                     overwrite: bool = False) -> Tuple[bool, Dict[str, Any]]:
        try:
            base_dir = Path(DATA_ROOT_DIR).resolve()
            target_path = (base_dir / file_path).resolve()
            if not str(target_path).startswith(str(base_dir)):
                raise PermissionError("Путь выходит за пределы разрешённой директории")
            if target_path.exists() and target_path.is_dir():
                return False, {"error": f"Указанный путь является директорией. Передайте полный путь до файла"}
            if target_path.exists() and not overwrite:
                return False, {"error": f"Файл уже существует: {file_path}. Установите overwrite=true"}
            target_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target_path.write_bytes, file_content)
            checksum = hashlib.sha256(file_content).hexdigest()
            logger.info(f"Файл сохранён: {target_path.relative_to(base_dir)}, "
                        f"size={len(file_content)}, checksum={checksum}")
            return True, {"file_size": len(file_content), "stored_in": "local", "checksum": checksum}
        except Exception as e:
            logger.error(f"Ошибка сохранения файла: {e}", exc_info=True)
            return False, {"error": str(e)}

    @staticmethod
    def _find_max_date_subfolder(folder_path: Path) -> Optional[str]:
        """Синхронно ищет подпапку с максимальной датой в формате YYYY-MM-DD."""
        if not folder_path.is_dir():
            return None
        max_dt, max_name = None, None
        date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        for item in folder_path.iterdir():
            if item.is_dir() and date_re.match(item.name):
                try:
                    dt = datetime.strptime(item.name, "%Y-%m-%d")
                except ValueError:
                    continue
                if max_dt is None or dt > max_dt:
                    max_dt, max_name = dt, item.name
        return max_name

    @staticmethod
    async def get_max_dates_for_folders(folders: List[str], root_dir: Path) -> Dict[str, Optional[str]]:
        """Асинхронно сканирует папки и возвращает {папка: макс_дата}."""
        if not folders:
            return {}
        tasks = [
            asyncio.to_thread(AppDataChecker._find_max_date_subfolder, root_dir / f)
            for f in folders
        ]
        results = await asyncio.gather(*tasks)
        return dict(zip(folders, results))

    @staticmethod
    async def check_file_exists(file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Проверка существования файла с защитой от Path Traversal.
        Выполняется быстро, но помечен как async для совместимости с FastAPI-роутами.
        """
        try:
            base = Path(DATA_ROOT_DIR).resolve()
            full_path = (base / file_path).resolve()

            # 1. Защита от выхода за пределы DATA_ROOT_DIR
            try:
                full_path.relative_to(base)
            except ValueError:
                logger.warning(f"Попытка проверки пути вне базы: {file_path}")
                return False, {"error": "Доступ запрещён: путь выходит за пределы разрешённой директории"}

            # 2. Проверка существования
            if not full_path.exists():
                return True, {"exists": False, "file_path": file_path, "file_size": None, "error": None}

            # 3. Проверка, что это файл, а не папка
            if not full_path.is_file():
                return False, {"error": "Указанный путь является директорией, а не файлом"}

            # 4. Успех
            size = full_path.stat().st_size
            logger.info(f"Файл найден: {file_path} ({size} B)")
            return True, {"exists": True, "file_path": file_path, "file_size": size, "error": None}

        except Exception as e:
            logger.error(f"Ошибка проверки файла: {e}", exc_info=True)
            return False, {"error": str(e)}
