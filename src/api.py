# src/api.py
"""
API роутеры для общего сервиса.
Системные эндпоинты + подключение модулей приложений.
"""
from fastapi import APIRouter, status
from typing import List, Dict

from src.config.logger import logger

openapi_tags: List[Dict[str, str]] = [
    {
        "name": "System",
        "description": "Системные эндпоинты: здоровье, готовность, метрики"
    },
]


def _collect_app_openapi_tags() -> List[Dict[str, str]]:
    """
    Собирает openapi_tags из конфигов всех доступных приложений.
    Безопасно: пропускает отсутствующие модули и невалидные форматы.
    """
    collected = []

    apps = [
        ("app_systems", "src.app_systems.config"),
        ("app_comtrade", "src.app_comtrade.config"),
    ]

    for app_name, config_path in apps:
        try:

            import importlib
            config_module = importlib.import_module(config_path)

            if hasattr(config_module, 'openapi_tags'):
                tag = config_module.openapi_tags

                if isinstance(tag, dict) and tag.get("name"):
                    if not any(t["name"] == tag["name"] for t in collected):
                        collected.append(tag)
                        logger.debug(f"Добавлен тег из {app_name}: {tag['name']}")
                elif isinstance(tag, list):
                    for t in tag:
                        if isinstance(t, dict) and t.get("name"):
                            if not any(existing["name"] == t["name"] for existing in collected):
                                collected.append(t)
                                logger.debug(f"Добавлен тег из {app_name}: {t['name']}")
                else:
                    logger.warning(f"Неверный формат openapi_tags в {app_name}: {type(tag)}")

        except ImportError:
            logger.debug(f"Приложение {app_name} не найдено (пропускаем)")
        except AttributeError as e:
            logger.warning(f"Ошибка при чтении тегов из {app_name}: {e}")
        except Exception as e:
            logger.error(f"Критическая ошибка сбора тегов из {app_name}: {e}")

    return collected


# === Инициализируем теги при импорте модуля ===
openapi_tags.extend(_collect_app_openapi_tags())

# === Глобальный роутер ===
router = APIRouter(tags=["System"])


# === СИСТЕМНЫЕ ЭНДПОИНТЫ ===

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Базовая проверка — процесс запущен."""
    return {
        "status": "ok",
        "message": "Data Validation Service is running",
        "version": "1.0.0",
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Проверка готовности (Kubernetes liveness/readiness)."""
    return {"status": "ready", "message": "Service is ready to accept traffic"}


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_metrics():
    """Простые метрики для мониторинга."""
    return {
        "service": "data_validation_service",
        "version": "1.0.0",
        "apps_connected": len([t for t in openapi_tags if t["name"] != "System"]),
    }


@router.get("/", status_code=status.HTTP_200_OK)
async def root():
    """Корневой эндпоинт — справка по сервису."""
    return {
        "service": "Data Validation Service",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/api/v1/system/health",
        "applications": [
            {"name": "app_systems", "prefix": "/api/v1/systems"},
            {"name": "app_comtrade", "prefix": "/api/v1/comtrade"},
        ],
    }


# === Функция подключения роутеров приложений ===

def include_app_routers(app) -> None:
    """
    Подключает изолированные роутеры приложений.
    Каждое приложение импортируется только если существует.
    """
    # === app_systems ===
    try:
        from src.app_systems.api import router as systems_router
        from src.app_systems.config import API_PREFIX_V1
        app.include_router(systems_router, prefix=API_PREFIX_V1)
        logger.info(f"✅ Подключено приложение: app_systems → {API_PREFIX_V1}")
    except ImportError as e:
        logger.debug(f"app_systems не подключён: {e}")

    # === app_comtrade ===
    try:
        from src.app_comtrade.api import router as comtrade_router
        from src.app_comtrade.config import API_PREFIX_V1 as COMTRADE_PREFIX
        app.include_router(comtrade_router, prefix=COMTRADE_PREFIX)
        logger.info(f"✅ Подключено приложение: app_comtrade → {COMTRADE_PREFIX}")
    except ImportError as e:
        logger.debug(f"app_comtrade не подключён: {e}")

    # === Добавляйте новые приложения сюда по аналогии ===
