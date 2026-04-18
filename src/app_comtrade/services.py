# src/app_comtrade/services.py
from typing import Dict, Any, Tuple, Union, Optional
from pathlib import Path

from core.type_unifier import SchemaComparator
from src.app_file_manager.validators.json_rule_validator import JsonRuleValidator
from src.config.database import DBManager
from src.config.logger import logger


class CheckRule:
    pass


class ComtradeCheckEngine:
    pass


class ComtradeChecker:
    def __init__(self, db_name: str = "base_01"):
        self.validator = JsonRuleValidator()
        self.db = DBManager.get_connection(db_name)

    async def validate_file(
            self,
            file_path: str,
            rule: Union[str, Dict, Path],
            file_type: str = "parquet"
    ) -> Tuple[bool, Dict[str, Any]]:
        """Выполняет валидацию и сохраняет метаданные в БД (PostgreSQL 15)"""
        is_valid, result = await self.validator.validate(rule, file_path, file_type)

        # Сохраняем результат валидации в БД (демонстрация зависимости от database.py)
        self._log_to_db(file_path, result.get("rule_id"), is_valid, len(result.get("errors", [])))
        return is_valid, result

    def _log_to_db(self, file_path: str, rule_id: Optional[str], is_valid: bool, error_count: int) -> None:
        if not self.db or not self.db.is_initialized:
            return
        try:
            with self.db.get_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO validation_logs (file_path, rule_id, is_valid, error_count, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (file_path) DO UPDATE SET 
                        is_valid = EXCLUDED.is_valid,
                        error_count = EXCLUDED.error_count,
                        updated_at = NOW();
                """, (file_path, rule_id, is_valid, error_count))
            logger.debug(f"Лог валидации сохранён в БД: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось сохранить лог валидации: {e}")

    @staticmethod
    async def _dispatch(rule: CheckRule, base_path: Path) -> Tuple[bool, Dict[str, Any]]:
        match rule.type:
            case "schema_match":
                return await ComtradeCheckEngine._check_schema(rule)
            case "folder_exists":
                return await ComtradeCheckEngine._check_folder(rule, base_path)
            case "file_exists":
                return await ComtradeCheckEngine._check_file(rule, base_path)
            case _:
                return False, {"error": f"Неподдерживаемый тип: {rule.type}"}

    @staticmethod
    async def _check_schema(rule: CheckRule) -> Tuple[bool, Dict[str, Any]]:
        comparator = SchemaComparator()
        src = rule.params.get("source_schema")
        tgt = rule.params.get("target_schema")
        src_type = rule.params.get("source_type", "parquet")
        tgt_type = rule.params.get("target_type", "postgresql")

        if not src or not tgt:
            return False, {"error": "Требуются params.source_schema и params.target_schema"}

        ok, mismatches = comparator.compare(src, src_type, tgt, tgt_type)
        return ok, {"mismatches": mismatches, "message": "Схемы совпадают" if ok else "Обнаружены несовпадения"}

    @staticmethod
    async def _check_folder(rule: CheckRule, base_path: Path) -> Tuple[bool, Dict[str, Any]]:
        path = base_path / rule.target
        exists = path.is_dir()
        return exists, {"path": str(path), "exists": exists}

    @staticmethod
    async def _check_file(rule: CheckRule, base_path: Path) -> Tuple[bool, Dict[str, Any]]:
        path = base_path / rule.target
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        min_size = rule.params.get("min_size_bytes", 0)
        valid_size = size >= min_size

        return exists and valid_size, {
            "path": str(path),
            "exists": exists,
            "size_bytes": size,
            "meets_min_size": valid_size
        }