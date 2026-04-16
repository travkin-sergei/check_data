# src/app_systems/api.py
"""
API приложения app_systems.
Простая изолированная авторизация по токену из .env
Строгое переиспользование: logger, database, services
Изоляция: импорты только из src.config.* и src.app_systems.*
"""
import mimetypes

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.background import BackgroundTask

from src.config.database import DBManager
from src.config.logger import logger
from src.app_systems.config import TAG_NAME, DATA_ROOT_DIR
from src.app_systems.dependencies import require_app_auth
from src.app_systems.services import AppDataChecker
from src.app_systems.schemas import (
    CheckDataResponse, CheckDataRequest,
    FoldersResponse, FileExistsResponse,
    ExtractSchemaResponse, ExtractSchemaRequest,
)

router = APIRouter(tags=[TAG_NAME])

# === Простая локальная авторизация ===
security = HTTPBearer(auto_error=False)

@router.post("/service/verify-token/")
async def verify_app_token(
    app_token: str = Depends(require_app_auth)
):
    """Проверяет токен приложения и возвращает его метаданные."""
    # Если мы здесь, токен валиден
    return {"valid": True, "message": "Токен действителен"}


@router.get(
    "/available-folders",
    response_model=FoldersResponse,
    summary="Получение содержимого директории (подпапки и файлы)",
    dependencies=[Depends(require_app_auth)],
)
async def get_available_folders(
        folder_path: Optional[str] = Query(None, description="Адрес директории относительно DATA_ROOT_DIR"),
        pattern: Optional[str] = Query(None, description="Regex для фильтрации (например, дат)"),
        page: int = Query(1, ge=1, description="Номер страницы"),
        page_size: int = Query(50, ge=1, le=1000, description="Записей на странице")
) -> FoldersResponse:
    logger.info(f"Запрос содержимого: path={folder_path or 'root'}, pattern={pattern}")
    success, result = await AppDataChecker.get_available_folders(
        root_dir=DATA_ROOT_DIR,
        folder_path=folder_path,
        pattern=pattern,
        page=page,
        page_size=page_size
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={'error': result.get('error')}
        )
    return FoldersResponse(success=success, **result)


@router.post(
    "/check-data",
    response_model=CheckDataResponse,
    dependencies=[Depends(require_app_auth)],
)
async def check_data(request: Optional[CheckDataRequest] = None):
    logger.info("Запрос на проверку данных")
    folders = request.folders if request else None

    success, result = await AppDataChecker.check_comtrade_data(
        base_url=DATA_ROOT_DIR,
        folders=folders
    )

    missing = result.get('missing', [])
    empty = result.get('empty', [])
    found_base = result.get('found', [])  # ← Список строк: ["folder1", "folder2"]

    # Сканирование дат только для найденных папок
    dates_map = await AppDataChecker.get_max_dates_for_folders(found_base, DATA_ROOT_DIR)

    # Форматирование в [{"папка": "дата"}, ...]
    found_formatted = [{f: dates_map.get(f)} for f in found_base]

    parts = []
    if missing: parts.append(f"не найдено: {len(missing)}")
    if empty: parts.append(f"пустые: {len(empty)}")
    if found_base: parts.append(f"с файлами: {len(found_base)}")
    message = " | ".join(parts) if parts else "Нет данных для проверки"

    return CheckDataResponse(
        success=success,
        message=message,
        missing=missing,
        empty=empty,
        found=found_formatted,  # ← Теперь List[Dict], соответствует схеме
        total_checked=len(folders or [])
    )


@router.post(
    "/extract-schema",
    response_model=ExtractSchemaResponse,
    summary="Получить схему данных файла",
    dependencies=[Depends(require_app_auth)],
)
async def extract_schema(request: ExtractSchemaRequest):
    logger.info(f"Запрос извлечения схемы: file={request.file_path}")
    success, result = await AppDataChecker.extract_file_schema(file_path=request.file_path)
    if not success:
        return ExtractSchemaResponse(
            success=False,
            message="Не удалось извлечь схему",
            schema={},
            file_path=request.file_path,
            file_type=result.get('file_type', 'unknown'),
            error=result.get('error', 'Неизвестная ошибка')
        )
    validated_schema = {
        k: {"type": v["type"], "null": v["null"]}
        for k, v in result.get("schema", {}).items()
    }
    return ExtractSchemaResponse(
        success=True,
        message=f"Схема извлечена: {result.get('field_count', 0)} полей",
        schema=validated_schema,
        file_path=request.file_path,
        file_type=result.get("file_type", "unknown"),
        error=None
    )


@router.get(
    "/download-file",
    summary="Скачать файл по пути",
    dependencies=[Depends(require_app_auth)],
)
async def download_file(
        file_path: str = Query(..., description="Путь к файлу относительно DATA_ROOT_DIR"),
        as_attachment: bool = Query(True, description="Скачивать как вложение")
):
    logger.info(f"Запрос на скачивание: path={file_path}, attachment={as_attachment}")
    try:
        base = Path(DATA_ROOT_DIR).resolve()
        full_path = (base / file_path).resolve()
        try:
            full_path.relative_to(base)
        except ValueError:
            logger.warning(f"Попытка доступа вне базы: {file_path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": f"Доступ запрещён: путь выходит за пределы {DATA_ROOT_DIR}"}
            )
        if not full_path.exists():
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Файл не найден: {file_path}"}
            )
        if not full_path.is_file():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Путь не является файлом: {file_path}"}
            )
        content_type, _ = mimetypes.guess_type(full_path.name)
        content_type = content_type or "application/octet-stream"

        async def log_download():
            try:
                db_conn = DBManager.get_connection("base_01")
                if db_conn and db_conn.is_initialized:
                    with db_conn.get_cursor(commit=True) as cur:
                        cur.execute(
                            """INSERT INTO file_download_log 
                            (file_path, downloaded_at, client_info)
                            VALUES (%s, NOW(), %s)""",
                            (file_path, "api_request")
                        )
            except Exception as e:
                logger.warning(f"Не удалось залогировать скачивание: {e}")

        return FileResponse(
            path=full_path,
            filename=full_path.name if as_attachment else None,
            media_type=content_type,
            background=BackgroundTask(log_download)
        )
    except PermissionError as e:
        logger.error(f"Ошибка доступа к файлу: {e}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Доступ запрещён"}
        )
    except Exception as e:
        logger.error(f"Неожиданная ошибка при скачивании: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Ошибка сервера: {type(e).__name__}"}
        )


@router.post(
    "/upload-file",
    summary="Загрузка файла в хранилище",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_app_auth)],
)
async def upload_file(file: UploadFile = File(...),
                      file_path: str = Form(..., description="Целевая директория"),
                      overwrite: bool = Form(False)):
    logger.info(f"Запрос загрузки: dir={file_path}, original_name={file.filename}")
    safe_name = (file.filename or "uploaded_file").replace("/", "_").replace("\\", "_")
    full_path = f"{file_path.rstrip('/')}/{safe_name}"
    try:
        content = await file.read()
        success, result = await AppDataChecker.upload_file_to_storage(
            file_path=full_path,
            file_content=content,
            overwrite=overwrite
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": result.get("error", "Unknown upload error")}
            )
        return {
            "success": True,
            "file_size": result.get("file_size"),
            "stored_in": result.get("stored_in"),
            "checksum": result.get("checksum")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Критическая ошибка в upload_file: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Ошибка сервера: {type(e).__name__}"}
        )


@router.get(
    "/check-file-exists",
    response_model=FileExistsResponse,
    summary="Проверка существования файла",
    description="Проверяет наличие файла по заданному пути",
    dependencies=[Depends(require_app_auth)],
)
async def check_file_exists(
        file_path: str = Query(..., description="Путь к файлу относительно DATA_ROOT_DIR")
):
    logger.info(f"Запрос проверки файла: path={file_path}")
    success, result = await AppDataChecker.check_file_exists(file_path)
    return FileExistsResponse(
        success=success,
        exists=result.get("exists", False),
        file_path=result.get("file_path", file_path),
        file_size=result.get("file_size"),
        error=result.get("error")
    )
