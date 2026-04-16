# tests/app_systems/conftest.py
import os

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from src.app_systems.main import app
from src.app_systems.api import verify_token


@pytest.fixture
def client():
    """TestClient с автоматической авторизацией для app_systems."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_check_file_exists():
    """Мок для AppDataChecker.check_file_exists с поддержкой суффиксов."""
    with patch("src.app_systems.api.AppDataChecker.check_file_exists", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(scope="module", autouse=True)
def isolate_dependencies(tmp_path_factory):
    """
    Модульная изоляция тестов app_systems:
    - Подменяет DATA_ROOT_DIR на временную директорию
    - Заглушает логирование, чтобы не засорять консоль
    """
    data_dir = tmp_path_factory.mktemp("app_systems_isolated_data")
    logger_mock = MagicMock()

    # Патчим константу там, где она используется, а не где определена.
    # Это предотвращает конфликты при параллельных импортах.
    with patch("src.app_systems.services.DATA_ROOT_DIR", data_dir), \
            patch("src.app_systems.api.DATA_ROOT_DIR", data_dir), \
            patch("src.config.logger.logger", logger_mock):
        yield data_dir


@pytest.fixture
def client():
    """TestClient с отключённой проверкой токена для тестов."""

    # ✅ Переопределяем проверку токена — всегда возвращаем True
    def override_verify_token():
        return True

    app.dependency_overrides[verify_token] = override_verify_token

    with TestClient(app) as c:
        yield c

    # ✅ Очищаем переопределения после теста, чтобы не ломать другие тесты
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_services():
    base = "src.app_systems.services.AppDataChecker"
    with patch(f"{base}.get_available_folders") as m_folders, \
            patch(f"{base}.check_comtrade_data") as m_check, \
            patch(f"{base}.extract_file_schema") as m_extract, \
            patch(f"{base}.upload_file_to_storage") as m_upload, \
            patch(f"{base}.get_max_dates_for_folders") as m_dates:
        yield {
            "folders": m_folders,
            "check": m_check,
            "extract": m_extract,
            "upload": m_upload,
            "get_max_dates_for_folders": m_dates,
        }
