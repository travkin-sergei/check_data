# src/app_auth/models.py
from datetime import datetime, timezone
from sqlalchemy import DateTime, text, ForeignKey
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
        return {"schema": "app_auth"}

    # phone_number: Mapped[str] = mapped_column(unique=True, nullable=False)
    first_name: Mapped[str]
    last_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    password: Mapped[str]
    # ForeignKey ДОЛЖЕН указывать схему явно:
    role_id: Mapped[int] = mapped_column(
        ForeignKey('app_auth.roles.id'),  # ← 'app_auth.roles', а не просто 'roles'
        default=1,
        server_default=text("1")
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")


class AppCredential(Base):
    """Учётные данные для межсервисной авторизации."""
    __tablename__ = "app_credentials"

    @declared_attr
    def __table_args__(cls):
        return {"schema": "app_auth"}

    app_name: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    app_description: Mapped[str | None]
    token_hash: Mapped[str] = mapped_column(unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('app_auth.users.id'), nullable=False)

    creator: Mapped["User"] = relationship("User", lazy="joined")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_expired(self) -> bool:
        """Проверяет, истёк ли срок действия токена."""
        if self.expires_at is None:
            return False  # бессрочные токены (для обратной совместимости)
        return self.expires_at < datetime.now(timezone.utc)

    def verify_token(self, token: str) -> bool:
        """Проверяет токен против хеша (bcrypt)."""
        from src.app_auth.utils import verify_password
        return verify_password(token, self.token_hash)
