from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer
from src.config.logger import logger
from src.app_servises.config import API_PREFIX_V1, DATA_ROOT_DIR
from src.app_servises.schemas import CheckDataResponse, CheckSourcesRequest
from src.app_servises.services import check_folders_last_update

router = APIRouter(prefix=API_PREFIX_V1, tags=["APP Systems"])
security = HTTPBearer(auto_error=False)


@router.post(
    "/check-sources",
    response_model=CheckDataResponse,
    summary="Проверка источников из базы данных",
    description="Получает список папок из app_servises.data_sources и проверяет даты обновления",
    dependencies=[Depends(verify_token)],
)
async def check_sources_from_db(request: Optional[CheckSourcesRequest] = None):
    """Автоматическая проверка: БД → список папок → сканирование дат."""
    logger.info("[API] Запрос проверки источников из БД")

    db_alias = request.db_alias if request and request.db_alias else "app_servises"
    limit = request.limit if request else None

    success, result = await AppDataChecker.check_sources_from_db(
        base_path=DATA_ROOT_DIR,
        db_alias=db_alias,
        limit=limit
    )

    # Формируем читаемый message
    missing = result.get("missing", [])
    empty = result.get("empty", [])
    found = result.get("found", [])  # уже в формате [{"папка": "дата"}, ...]

    parts = []
    if missing: parts.append(f"не найдено: {len(missing)}")
    if empty: parts.append(f"пустые: {len(empty)}")
    if found: parts.append(f"с датами: {len(found)}")
    message = ("Проверка из БД завершена. " + ", ".join(parts)) if parts else "Источники не найдены в БД"

    return CheckDataResponse(
        success=success,
        message=message,
        missing=missing,
        empty=empty,
        found=found,  # List[Dict[str, Optional[str]]]
        total_checked=len(missing) + len(empty) + len(found)
    )
