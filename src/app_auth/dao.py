# src/app_auth/dao.py
from typing import TypeVar, Generic, Type
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy import update as sqlalchemy_update, delete as sqlalchemy_delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.logger import logger
from src.app_database.base import Base

T = TypeVar("T", bound=Base)


class BaseDAO(Generic[T]):
    model: Type[T] = None

    def __init__(self, session: AsyncSession):
        self._session = session
        if not self.model:
            raise ValueError("Модель не указана в дочернем классе")

    async def find_one_or_none_by_id(self, data_id: int):
        try:
            res = await self._session.execute(select(self.model).filter_by(id=data_id))
            return res.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка поиска по ID {data_id}: {e}")
            raise

    async def find_one_or_none(self, filters: BaseModel):
        try:
            res = await self._session.execute(select(self.model).filter_by(**filters.model_dump(exclude_unset=True)))
            return res.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка поиска: {e}")
            raise

    async def find_all(self, filters: BaseModel | None = None):
        try:
            f = filters.model_dump(exclude_unset=True) if filters else {}
            res = await self._session.execute(select(self.model).filter_by(**f))
            return res.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка поиска всех: {e}")
            raise

    async def add(self, values: BaseModel):
        try:
            inst = self.model(**values.model_dump(exclude_unset=True))
            self._session.add(inst)
            await self._session.flush()
            return inst
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка добавления: {e}")
            raise

    async def update(self, filters: BaseModel, values: BaseModel):
        try:
            f = filters.model_dump(exclude_unset=True)
            v = values.model_dump(exclude_unset=True)
            q = sqlalchemy_update(self.model).where(*[getattr(self.model, k) == val for k, val in f.items()]).values(
                **v)
            res = await self._session.execute(q)
            await self._session.flush()
            return res.rowcount
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка обновления: {e}")
            raise

    async def delete(self, filters: BaseModel):
        f = filters.model_dump(exclude_unset=True)
        if not f:
            raise ValueError("Для удаления требуется фильтр.")
        try:
            q = sqlalchemy_delete(self.model).filter_by(**f)
            res = await self._session.execute(q)
            await self._session.flush()
            return res.rowcount
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка удаления: {e}")
            raise


class UsersDAO(BaseDAO):
    model = None  # Будет переопределено при импорте, или установим здесь:

    def __init__(self, session: AsyncSession):
        from src.app_auth.models import User
        self.model = User
        super().__init__(session)


class RoleDAO(BaseDAO):
    def __init__(self, session: AsyncSession):
        from src.app_auth.models import Role
        self.model = Role
        super().__init__(session)


class AppCredentialDAO(BaseDAO):
    def __init__(self, session: AsyncSession):
        from src.app_auth.models import AppCredential
        self.model = AppCredential
        super().__init__(session)

    async def find_by_app_name(self, app_name: str):
        """Поиск учётных данных по имени приложения."""
        try:
            res = await self._session.execute(
                select(self.model).filter_by(app_name=app_name)
            )
            return res.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка поиска AppCredential: {e}")
            raise
