from pydantic import BaseModel, Field
from typing import List, Optional


class CheckDataRequest(BaseModel):
    folders: List[str] = Field(..., description="Список папок для проверки даты обновления")


class FolderResult(BaseModel):
    folder: str
    last_update_date: Optional[str] = Field(None, description="Дата последнего обновления (YYYY-MM-DD)")
    status: str = Field(..., description="found | empty | missing | error")


class CheckDataResponse(BaseModel):
    success: bool
    message: str
    results: List[FolderResult]


class CheckSourcesRequest(BaseSchema):
    """Запрос проверки источников из БД."""
    db_alias: Optional[str] = Field(
        "base_01",
        description="Алиас подключения к БД (из app_database/config.py)"
    )
    limit: Optional[int] = Field(
        None,
        ge=1,
        le=1000,
        description="Макс. количество источников для проверки (опционально)"
    )
