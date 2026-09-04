from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin


class User(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(btrim(email)) AND email ~ '^[^[:space:]@]+@[^[:space:]@]+$'",
            name="email_canonical",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)

    @validates("email")
    def normalize_email(self, key, value):
        """FinSight treats the entire email as case-insensitive; no login behavior."""
        return value.strip().lower()
