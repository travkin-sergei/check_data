# src/app_comtrade/schemas.py
# src/app_comtrade/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

class BaseSchema(BaseModel):
    """Базовая схема с настройками (строгое переиспользование паттерна app_file_manager)."""
    model_config = ConfigDict(
        from_attributes=True,
        extra='ignore',
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

class SchemaCheckRequest(BaseSchema):
    """Запрос на проверку соответствия файла схеме."""
    file_path: str = Field(..., description="Абсолютный или относительный путь к файлу")
    schema_description: Dict[str, str] = Field(..., description="Ожидаемая схема: {'field_name': 'TYPE'}")
    file_type: str = Field("parquet", description="Тип файла: parquet, csv, json")
    strict_mode: bool = Field(False, description="Строгое совпадение: запрещает лишние/недостающие поля")

class SchemaCheckResponse(BaseSchema):
    """Ответ проверки схемы."""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = Field(None, description="Детали ошибок или отчёт о совпадении")