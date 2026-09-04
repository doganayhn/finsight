from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin


class Category(IdentityMixin, TimestampMixin, Base):
    """Shared catalog; is_system is provenance, not a private-user ownership flag."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z][A-Z0-9_]*$'", name="code_format"),
        CheckConstraint("parent_id != id", name="not_own_parent"),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    parent: Mapped["Category | None"] = relationship(remote_side="Category.id")
