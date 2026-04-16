# src/core/schemas.py
"""
Простой валидатор: файл + схема → результат соответствия.
Использует SchemaComparator из type_unifier.py.
"""
import json
from pathlib import Path
from typing import Union, Dict, Any, Tuple
from src.core.type_unifier import SchemaComparator


def validate_file_schema(
    schema_description: Union[Dict[str, str], str, Path],
    file_path: Union[str, Path],
    file_type: str = "parquet",  # parquet, csv, json
    strict_mode: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Проверяет, соответствует ли файл заданному описанию схемы.

    Args:
        schema_description: Описание схемы в виде:
            - dict: {"id": "INTEGER", "name": "VARCHAR"}
            - str: JSON-строка или путь к файлу со схемой
            - Path: путь к файлу со схемой
        file_path: Путь к проверяемому файлу (parquet, csv, json)
        file_type: Тип файла: 'parquet', 'csv', 'json'
        strict_mode: Если True — поля должны совпадать точно (без лишних/недостающих)

    Returns:
        Tuple[bool, Dict]:
            - True, {} — если файл соответствует схеме
            - False, {описание проблем} — если есть несовпадения
    """
    # === 1. Извлекаем ожидаемую схему из описания ===
    comparator = SchemaComparator()
    expected_schema = comparator._load_schema(schema_description)

    # === 2. Извлекаем фактическую схему из файла ===
    actual_schema = _extract_schema_from_file(file_path, file_type)
    if not actual_schema:
        return False, {"error": f"Не удалось прочитать схему из файла: {file_path}"}

    # === 3. Сравниваем схемы ===
    is_match, errors = comparator.compare(
        source_schema=expected_schema,
        source_type="json",  # наша схема — это уже нормализованный JSON
        target_schema=actual_schema,
        target_type=file_type
    )

    # === 4. Строгий режим: запрещаем лишние/недостающие поля ===
    if strict_mode and is_match:
        expected_fields = set(expected_schema.keys())
        actual_fields = set(actual_schema.keys())
        if expected_fields != actual_fields:
            missing = expected_fields - actual_fields
            extra = actual_fields - expected_fields
            return False, {
                "issue": "strict_mode_mismatch",
                "missing_fields": list(missing),
                "extra_fields": list(extra)
            }

    return is_match, errors if not is_match else {"message": "Схема соответствует описанию"}


# === Вспомогательные функции для извлечения схемы из файлов ===

def _extract_schema_from_file(file_path: Union[str, Path], file_type: str) -> Dict[str, str]:
    """Извлекает схему (имя поля → тип) из файла."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    match file_type.lower():
        case "parquet":
            return _read_parquet_schema(path)
        case "csv":
            return _read_csv_schema(path)
        case "json":
            return _read_json_schema(path)
        case _:
            raise ValueError(f"Неподдерживаемый тип файла: {file_type}")


def _read_parquet_schema(path: Path) -> Dict[str, str]:
    """Читает схему Parquet-файла (без внешних зависимостей — через pyarrow)."""
    try:
        import pyarrow.parquet as pq
        parquet_file = pq.ParquetFile(path)
        schema = parquet_file.schema_arrow
        return {field.name: _map_pyarrow_type(field.type) for field in schema}
    except ImportError:
        # Если pyarrow недоступен — пробуем через pandas (менее точно)
        try:
            import pandas as pd
            df = pd.read_parquet(path, engine="pyarrow")
            return {col: _map_pandas_dtype(str(dtype)) for col, dtype in df.dtypes.items()}
        except Exception:
            raise RuntimeError("Для чтения Parquet требуется pyarrow или pandas+pyarrow")


def _read_csv_schema(path: Path) -> Dict[str, str]:
    """Читает заголовки CSV и определяет типы по первой строке данных."""
    import csv
    with open(path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        headers = next(reader)
        first_row = next(reader, None)

    schema = {}
    for header, value in zip(headers, first_row or []):
        schema[header.strip()] = _infer_type_from_value(value)
    return schema


def _read_json_schema(path: Path) -> Dict[str, str]:
    """Извлекает схему из первого объекта JSON-файла (массив объектов или один объект)."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Если массив — берём первый элемент
    if isinstance(data, list) and data:
        sample = data[0]
    elif isinstance(data, dict):
        sample = data
    else:
        raise ValueError("JSON должен содержать объект или массив объектов")

    return {key: _infer_type_from_value(value) for key, value in sample.items()}


# === Утилиты для маппинга типов ===

def _map_pyarrow_type(pa_type) -> str:
    """Преобразует тип PyArrow в нормализованное строковое представление."""
    type_str = str(pa_type).lower()
    if 'int32' in type_str:
        return 'INTEGER'
    elif 'int64' in type_str:
        return 'BIGINT'
    elif 'float' in type_str or 'double' in type_str:
        return 'DOUBLE PRECISION'
    elif 'string' in type_str or 'utf8' in type_str:
        return 'VARCHAR'
    elif 'bool' in type_str:
        return 'BOOLEAN'
    elif 'date32' in type_str or 'date64' in type_str:
        return 'DATE'
    elif 'timestamp' in type_str:
        return 'TIMESTAMPTZ' if 'tz=' in type_str else 'TIMESTAMP'
    return 'VARCHAR'  # fallback


def _map_pandas_dtype(dtype: str) -> str:
    """Преобразует pandas dtype в нормализованный тип."""
    dtype = dtype.lower()
    if 'int' in dtype:
        return 'INTEGER'
    elif 'float' in dtype:
        return 'DOUBLE PRECISION'
    elif 'bool' in dtype:
        return 'BOOLEAN'
    elif 'datetime' in dtype or 'timestamp' in dtype:
        return 'TIMESTAMP'
    elif 'object' in dtype:
        return 'VARCHAR'
    return 'VARCHAR'


def _infer_type_from_value(value: str) -> str:
    """Определяет тип по строковому значению (для CSV/JSON)."""
    if value is None or value == '':
        return 'VARCHAR'
    if value.lower() in ('true', 'false'):
        return 'BOOLEAN'
    try:
        int(value)
        return 'INTEGER'
    except ValueError:
        pass
    try:
        float(value)
        return 'DOUBLE PRECISION'
    except ValueError:
        pass
    # Простая эвристика для дат
    if len(value) == 10 and value[4] == '-' and value[7] == '-':
        return 'DATE'
    return 'VARCHAR'