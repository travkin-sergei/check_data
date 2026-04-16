"""
Реестр источников для динамического подключения.
Позволяет запускать источники по имени без жестких импортов.
"""
from typing import Dict, Type, Optional
from app_comtrade.services import DataSourceBase


class SourceRegistry:
    """Реестр доступных источников данных."""
    _sources: Dict[str, Type[DataSourceBase]] = {}

    @classmethod
    def register(cls, name: str, source_class: Type[DataSourceBase]):
        """Регистрация источника."""
        cls._sources[name.lower()] = source_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[DataSourceBase]]:
        """Получение класса источника по имени."""
        return cls._sources.get(name.lower())

    @classmethod
    def list_available(cls) -> list:
        """Список зарегистрированных источников."""
        return list(cls._sources.keys())


# === Авто-регистрация при импорте модулей ===
def _auto_register():
    """Автоматическая регистрация известных источников."""
    # Импорт внутри функции для избежания циклических зависимостей
    from src.app_comtrade.download_data.sources import world_trade

    SourceRegistry.register("world_trade", world_trade.WorldTradeSource)
    # Добавляйте новые источники здесь


_auto_register()
