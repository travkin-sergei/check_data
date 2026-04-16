# src/app_auth/models.py
from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr
from src.app_database.base import Base


class Role(Base):
    __tablename__ = "roles"

    @declared_attr
    def __table_args__(cls):
        return {"schema": "app_auth"}  # ← ОБЯЗАТЕЛЬНО: изоляция в схеме

    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    @declared_attr
    def __table_args__(cls):
        return {"schema": "app_auth"}  # ← ОБЯЗАТЕЛЬНО: та же схема

    phone_number: Mapped[str] = mapped_column(unique=True, nullable=False)
    first_name: Mapped[str]
    last_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    password: Mapped[str]
    # 🔹 ForeignKey ДОЛЖЕН указывать схему явно:
    role_id: Mapped[int] = mapped_column(
        ForeignKey('app_auth.roles.id'),  # ← 'app_auth.roles', а не просто 'roles'
        default=1,
        server_default=text("1")
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")