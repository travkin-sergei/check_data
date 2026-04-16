# src/app_systems/api.py
"""
API приложения app_systems.
Централизованная авторизация через app_auth.
Строгое переиспользование: logger, database, services, app_auth.dependencies
Изоляция: импорты только из src.config.*, src.app_systems.*, src.app_auth.dependencies
"""
import mimetypes
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

# ← ЕДИНАЯ точка входа для авторизации (из app_auth)
from src.app_auth.dependencies import require_app_access

from app_database.database import DBManager
from src.config.logger import logger
from src.app_systems.config import TAG_NAME, DATA_ROOT_DIR
from src.app_systems.services import AppDataChecker
from src.app_systems.schemas import (
    CheckDataResponse, CheckDataRequest,
    FoldersResponse, FileExistsResponse,
    ExtractSchemaResponse, ExtractSchemaRequest,
)

router = APIRouter(tags=[TAG_NAME])


# === УДАЛЕНО: локальная проверка токена ===
# Все эндпоинты теперь используют require_app_access из app_auth


@router.get(
    "/available-folders",
    response_model=FoldersResponse,
    summary="Получение содержимого директории (подпапки и файлы)",
    # ← Централизованная авторизация + автоматический аудит
    dependencies=[Depends(require_app_access)],
)
async def get_available_folders(
        # ← Контекст приложения (доступен благодаря зависимости)
        app_context: dict = Depends(require_app_access),
        folder_path: Optional[str] = Query(None, description="Адрес директории относительно DATA_ROOT_DIR"),
        pattern: Optional[str] = Query(None, description="Regex для фильтрации (например, дат)"),
        page: int = Query(1, ge=1, description="Номер страницы"),
        page_size: int = Query(50, ge=1, le=1000, description="Записей на странице")
) -> FoldersResponse:
    # ← Логирование с идентификатором приложения
    logger.info(f"[SYSTEMS] Запрос от приложения: {app_context['identifier']} "
                f"(id={app_context['app_id']}) | path={folder_path or 'root'}")

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
    "/check-app_database",
    response_model=CheckDataResponse,
    dependencies=[Depends(require_app_access)],
)
async def check_data(
        app_context: dict = Depends(require_app_access),
        request: Optional[CheckDataRequest] = None
):
    logger.info(f"[SYSTEMS] Проверка данных от приложения: {app_context['identifier']}")

    folders = request.folders if request else None
    success, result = await AppDataChecker.check_comtrade_data(
        base_url=DATA_ROOT_DIR,
        folders=folders
    )

    missing = result.get('missing', [])
    empty = result.get('empty', [])
    found_base = result.get('found', [])

    dates_map = await AppDataChecker.get_max_dates_for_folders(found_base, DATA_ROOT_DIR)
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
        found=found_formatted,
        total_checked=len(folders or [])
    )


@router.post(
    "/extract-schema",
    response_model=ExtractSchemaResponse,
    summary="Получить схему данных файла",
    dependencies=[Depends(require_app_access)],
)
async def extract_schema(
        app_context: dict = Depends(require_app_access),
        request: ExtractSchemaRequest = None
):
    logger.info(f"[SYSTEMS] Извлечение схемы от {app_context['identifier']}: file={request.file_path}")

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
    dependencies=[Depends(require_app_access)],
)
async def download_file(
        app_context: dict = Depends(require_app_access),
        file_path: str = Query(..., description="Путь к файлу относительно DATA_ROOT_DIR"),
        as_attachment: bool = Query(True, description="Скачивать как вложение")
):
    logger.info(f"[SYSTEMS] Скачивание файла: {file_path} | приложение: {app_context['identifier']}")

    try:
        base = Path(DATA_ROOT_DIR).resolve()
        full_path = (base / file_path).resolve()

        try:
            full_path.relative_to(base)
        except ValueError:
            logger.warning(f"Попытка доступа вне базы: {file_path} | app_id={app_context['app_id']}")
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
                        # ← Аудит скачивания с привязкой к приложению
                        cur.execute(
                            """INSERT INTO file_download_log 
                            (app_id, file_path, downloaded_at, client_info)
                            VALUES (%s, %s, NOW(), %s)""",
                            (app_context['app_id'], file_path, app_context['identifier'])
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
    dependencies=[Depends(require_app_access)],
)
async def upload_file(
        app_context: dict = Depends(require_app_access),
        file: UploadFile = File(...),
        file_path: str = Form(..., description="Целевая директория"),
        overwrite: bool = Form(False)
):
    logger.info(f"[SYSTEMS] Загрузка файла от {app_context['identifier']}: dir={file_path}")

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
    description=(
            "Проверяет наличие файла по заданному пути. "
            "Если файл не найден и переданы суффиксы, проверяет варианты: "
            "file.ext → file.ext.suffix1 → file.ext.suffix2"
    ),
    dependencies=[Depends(require_app_access)],
)
async def check_file_exists(
        app_context: dict = Depends(require_app_access),
        file_path: str = Query(..., description="Путь к файлу относительно DATA_ROOT_DIR"),
        suffixes: Optional[List[str]] = Query(
            None, alias="suffix",
            description="Список возможных суффиксов. Передавать как ?suffix=a&suffix=b"
        )
):
    logger.info(f"[SYSTEMS] Проверка файла от {app_context['identifier']}: path={file_path}, suffixes={suffixes}")

    try:
        # ← Обновите сервис, чтобы он принимал suffixes (см. ниже)
        success, result = await AppDataChecker.check_file_exists(file_path, suffixes=suffixes)
        return FileExistsResponse(
            success=success,
            exists=result.get("exists", False),
            file_path=result.get("file_path", file_path),
            found_suffix=result.get("found_suffix"),
            file_size=result.get("file_size"),
            error=result.get("error")
        )
    except Exception as e:
        logger.error(f"Ошибка в check_file_exists: {type(e).__name__}: {e}", exc_info=True)
        return FileExistsResponse(
            success=False, exists=False, file_path=file_path,
            found_suffix=None, file_size=None, error=str(e)
        )