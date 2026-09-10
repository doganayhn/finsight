from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin
from app.db.types import UTCDateTime


class User(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(btrim(email)) AND email ~ '^[^[:space:]@]+@[^[:space:]@]+$'",
            name="email_canonical",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Legacy development users deliberately remain unable to log in until credentials are set.
    password_hash: Mapped[str | None] = mapped_column(String(512))

    @validates("email")
    def normalize_email(self, key, value):
        """FinSight treats the entire email as case-insensitive; no login behavior."""
        return value.strip().lower()


class AuthSession(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at", "refresh_expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    refresh_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user: Mapped[User] = relationship()
