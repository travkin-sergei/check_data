# tests/app_systems/test_api.py
"""
Тесты для эндпоинта /check-file-exists с поддержкой суффиксов.
Изоляция: моки сервиса, переопределение авторизации.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from src.app_systems.main import app
from src.app_systems.api import verify_token


# === Фикстуры (добавить в conftest.py или в начало файла) ===
@pytest.fixture
def client():
    """TestClient с отключённой проверкой токена для тестов."""

    def override_verify_token():
        return True

    app.dependency_overrides[verify_token] = override_verify_token
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_check_file_exists():
    """Мок для AppDataChecker.check_file_exists."""
    with patch("src.app_systems.api.AppDataChecker.check_file_exists", new_callable=AsyncMock) as mock:
        yield mock


class TestCheckFileExists:
    """Тесты эндпоинта /check-file-exists с поддержкой суффиксов."""

    def test_check_file_exists_basic_backward_compatible(self, client, mock_check_file_exists):
        """Базовая проверка: файл существует, суффиксы не переданы (обратная совместимость)."""
        mock_check_file_exists.return_value = (
            True,
            {"exists": True, "file_path": "app_database/test.parquet", "file_size": 1024, "error": None}
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={"file_path": "app_database/test.parquet"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["exists"] is True
        assert data["file_path"] == "app_database/test.parquet"
        assert data.get("found_suffix") is None  # ✅ Новое поле, опциональное
        assert data["file_size"] == 1024
        assert data["error"] is None

        # Проверяем вызов сервиса: suffixes=None для обратной совместимости
        mock_check_file_exists.assert_called_once_with("app_database/test.parquet", suffixes=None)

    def test_check_file_exists_not_found_no_suffixes(self, client, mock_check_file_exists):
        """Файл не найден, суффиксы не переданы."""
        mock_check_file_exists.return_value = (
            True,
            {"exists": False, "file_path": "app_database/missing.parquet", "file_size": None, "error": None}
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={"file_path": "app_database/missing.parquet"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["exists"] is False
        assert data["file_path"] == "app_database/missing.parquet"
        assert data["error"] is None

    def test_check_file_exists_found_with_single_suffix(self, client, mock_check_file_exists):
        """Файл найден с одним суффиксом: test.parquet → test.parquet.extendet."""
        mock_check_file_exists.return_value = (
            True,
            {
                "exists": True,
                "file_path": "app_database/test.parquet.extendet",  # ✅ Актуальный путь
                "found_suffix": "extendet",  # ✅ Какой суффикс сработал
                "file_size": 2048,
                "error": None
            }
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/test.parquet",
                "suffix": "extendet"  # ✅ FastAPI: один суффикс
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["file_path"] == "app_database/test.parquet.extendet"
        assert data["found_suffix"] == "extendet"
        assert data["file_size"] == 2048

        mock_check_file_exists.assert_called_once_with(
            "app_database/test.parquet",
            suffixes=["extendet"]  # ✅ Список из одного элемента
        )

    def test_check_file_exists_found_with_multiple_suffixes_first_match(self, client, mock_check_file_exists):
        """Файл найден по первому суффиксу из списка: extendet сработал, rrrr не проверялся."""
        mock_check_file_exists.return_value = (
            True,
            {
                "exists": True,
                "file_path": "app_database/test.parquet.extendet",
                "found_suffix": "extendet",
                "file_size": 1500,
                "error": None
            }
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/test.parquet",
                "suffix": ["extendet", "rrrr", "tmp"]  # ✅ FastAPI соберёт ?suffix=a&suffix=b&suffix=c
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["found_suffix"] == "extendet"

        mock_check_file_exists.assert_called_once_with(
            "app_database/test.parquet",
            suffixes=["extendet", "rrrr", "tmp"]
        )

    def test_check_file_exists_not_found_even_with_suffixes(self, client, mock_check_file_exists):
        """Файл не найден ни по оригиналу, ни по суффиксам."""
        mock_check_file_exists.return_value = (
            True,
            {"exists": False, "file_path": "app_database/missing.parquet", "found_suffix": None, "error": None}
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/missing.parquet",
                "suffix": ["extendet", "rrrr"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["exists"] is False
        assert data["found_suffix"] is None
        assert data["error"] is None

    def test_check_file_exists_path_traversal_blocked_with_suffix(self, client, mock_check_file_exists):
        """Защита от Path Traversal: даже с суффиксами путь вне базы блокируется."""
        mock_check_file_exists.return_value = (
            False,
            {"error": "Доступ запрещён: путь выходит за пределы разрешённой директории"}
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "../../../etc/passwd",
                "suffix": "bak"
            }
        )

        assert response.status_code == 200  # ✅ API возвращает 200, но success=False
        data = response.json()
        assert data["success"] is False
        assert data["exists"] is False
        assert "Доступ запрещён" in data["error"]

    def test_check_file_exists_service_exception_handled(self, client, mock_check_file_exists):
        """Исключение в сервисе перехватывается — возвращается безопасный ответ."""
        mock_check_file_exists.side_effect = PermissionError("Доступ запрещён")

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/secret.parquet",
                "suffix": "enc"
            }
        )

        # ✅ API не падает с 500, а возвращает корректный ответ
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["exists"] is False
        assert data["error"] == "Доступ запрещён"
        assert data["found_suffix"] is None

    def test_check_file_exists_suffix_normalization_dot_stripped(self, client, mock_check_file_exists):
        """Суффикс с ведущей точкой нормализуется: '.tmp' → 'tmp' в ответе."""
        mock_check_file_exists.return_value = (
            True,
            {
                "exists": True,
                "file_path": "app_database/file.parquet.tmp",
                "found_suffix": "tmp",  # ✅ Без точки в ответе
                "file_size": 100,
                "error": None
            }
        )

        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/file.parquet",
                "suffix": ".tmp"  # ✅ Клиент может передать с точкой
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["found_suffix"] == "tmp"  # ✅ В ответе всегда без ведущей точки
        assert data["file_path"] == "app_database/file.parquet.tmp"

    def test_check_file_exists_empty_suffix_list_treated_as_none(self, client, mock_check_file_exists):
        """Пустой список суффиксов эквивалентен отсутствию суффиксов."""
        mock_check_file_exists.return_value = (
            True,
            {"exists": True, "file_path": "app_database/f.parquet", "file_size": 500, "error": None}
        )

        # FastAPI: ?suffix= без значения → []
        response = client.get(
            "/api/v1/systems/check-file-exists",
            params={
                "file_path": "app_database/f.parquet",
                "suffix": []  # ✅ Пустой список
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True

        # Сервис должен получить suffixes=None или [] — оба варианта допустимы
        call_args = mock_check_file_exists.call_args
        assert call_args[0][0] == "app_database/f.parquet"
        assert call_args[1]["suffixes"] in (None, [])
