# src/app_macmap/services.py
import duckdb
import json
import requests

from pathlib import Path

from config.logger import logger


def get_columns(file_path, sep=',') -> json:
    """
    Получить имена столбцов и типов данных.
    Args:
        file_path: путь к файлу
        sep: разделитель, для csv

    Returns: json

    """
    ext = Path(file_path).suffix.lower()
    match ext:
        case '.csv':
            query = f"""
                DESCRIBE SELECT * FROM read_csv(
                    '{file_path}', 
                    sep='{sep}',
                    header=True,
                    auto_detect=True,
                    all_varchar=True
                )
            """
        case '.parquet':
            query = f"DESCRIBE SELECT * FROM '{file_path}'"
        case _:
            raise ValueError(f"Неподдерживаемый формат: {ext}")

    rows = duckdb.sql(query).fetchall()
    return json.dumps({row[0]: row[1] for row in rows}, ensure_ascii=False, indent=2)


def send_folders_to_check(folders_list, base_url):
    """
    Обращение к ручки проверки наличия списка источников (папок).
    Args: список папок.
    """
    url = f"{base_url.rstrip('/')}/api/v1/systems/check-app_database"
    possible_keys = ["folders", "paths", "items", "app_database"]

    for key in possible_keys:
        payload = {key: folders_list}
        logger.debug(f"Пробуем ключ '{key}': {payload}")
        response = requests.post(url, json=payload)

        if response.status_code == 200:
            logger.debug(f"Успех! Ключ '{key}' подходит.")
            return response.json()
        else:
            logger.error(f"Ошибка {response.status_code}: {response.text[:200]}")
    return None


# Пример использования
if __name__ == "__main__":
    folders = [
        "API-COMTRADE-COUNTRY_AREAS-1",
    ]
    api_base = "http://127.0.0.1:8000"  # замените на реальный адрес
    result = send_folders_to_check(folders, api_base)
    print("Ответ:", result)
