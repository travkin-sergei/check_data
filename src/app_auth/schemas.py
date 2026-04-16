# src/app_auth/schemas.py
import re
from typing import Self
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator, computed_field

from src.config.logger import logger
from src.app_auth.utils import get_password_hash


class EmailModel(BaseModel):
    email: EmailStr = Field(description="Электронная почта")
    model_config = ConfigDict(from_attributes=True)


class UserBase(EmailModel):
    phone_number: str = Field(description="Номер телефона в формате +7XXXXXXXXXX")
    first_name: str = Field(min_length=3, max_length=50)
    last_name: str = Field(min_length=3, max_length=50)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r'^\+\d{5,15}$', v):
            raise ValueError('Номер должен начинаться с "+" и содержать 5-15 цифр')
        return v


class SUserRegister(UserBase):
    # 🔹 Убираем max_length=50 — он вводит в заблуждение (символы ≠ байты)
    password: str = Field(min_length=5, description="Пароль (макс. 72 байта в UTF-8)")
    confirm_password: str = Field(min_length=5)

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.password != self.confirm_password:
            raise ValueError("Пароли не совпадают")

        # 🔹 Явная проверка и безопасное усечение до 72 байт
        pwd_bytes = self.password.encode("utf-8")
        if len(pwd_bytes) > 72:
            # Усекаем на границе байтов, затем декодируем с игнорированием ошибок
            self.password = pwd_bytes[:72].decode("utf-8", errors="ignore").rstrip()
            logger.warning(f"Пароль усечён до 72 байт: исходная длина {len(pwd_bytes)} байт")

        # 🔹 Хэшируем уже усечённый пароль
        self.password = get_password_hash(self.password)
        return self


class SUserAddDB(UserBase):
    password: str = Field(min_length=5, description="Хеш пароля (bcrypt)")


class SUserAuth(EmailModel):
    password: str = Field(min_length=5, max_length=50)


class RoleModel(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class SUserInfo(UserBase):
    id: int
    role: RoleModel = Field(exclude=True)

    @computed_field
    def role_name(self) -> str: return self.role.name

    @computed_field
    def role_id(self) -> int: return self.role.id
