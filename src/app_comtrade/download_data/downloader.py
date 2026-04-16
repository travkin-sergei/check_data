"""
Общая логика скачивания и загрузки файлов.
Используется всеми источниками через вызов process_files_batch().
Изоляция: только стандартные библиотеки + httpx + src.config.*
"""

import requests as r

from app_comtrade.config import API_TOKEN
from core.config import ECOMRU_API_URL


def get_ecomru_api_v1_entities() -> list[dict]:
    """Получить список ссылок."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_TOKEN}",
    }
    endpoint = "api/v1/updates"
    url = ECOMRU_API_URL
    req = r.get(f"{url}/{endpoint}", headers=headers)

    data = []
    for item in req.json():
        if isinstance(item, dict):
            data.extend(item.get("loadLinks", []))
        else:
            print(f"Пропущен элемент не-словаря: {item}")
    return data


def get_ecomru_api_v1_updates(source: str) -> list[dict]:
    """Получить список ссылок."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_TOKEN}",
    }
    endpoint = "api/v1/updates"
    url = ECOMRU_API_URL
    params = {"entity": source, }
    req = r.get(f"{url}/{endpoint}", params, headers=headers)

    data = []
    for item in req.json():
        if isinstance(item, dict):
            data.extend(item.get("loadLinks", []))
        else:
            print(f"Пропущен элемент не-словаря: {item}")
    return data


info = "API-COMTRADE-WORLD_TRADE-1"

list_link = get_ecomru_api_v1_updates(info)

for item in list_link:
    print(item)
