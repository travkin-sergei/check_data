# src/app_comtrade/api.py
from fastapi import APIRouter, HTTPException, status
from typing import Optional, Dict, Any

from src.app_comtrade.services import ComtradeChecker
from src.app_comtrade.config import TAG_NAME

router = APIRouter(tags=[TAG_NAME])
checker = ComtradeChecker()


@router.post("/validate", response_model=Dict[str, Any])
async def validate_comtrade_file(
        file_path: str,
        rule_path: Optional[str] = None,
        rule_json: Optional[Dict[str, Any]] = None,
        file_type: str = "parquet"
):
    """Проверка файла на сопоставимость по JSON-правилу."""
    if not rule_path and not rule_json:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Укажите rule_path или rule_json")

    rule_input = rule_json or rule_path
    success, result = await checker.validate_file(file_path, rule_input, file_type)

    status_code = status.HTTP_200_OK if success else status.HTTP_422_UNPROCESSABLE_ENTITY
    if not success:
        raise HTTPException(status_code=status_code, detail=result)
    return result