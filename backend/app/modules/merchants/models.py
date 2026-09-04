from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin
from app.modules.categories.models import Category


class MerchantAlias(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "merchant_aliases"
    __table_args__ = (CheckConstraint("length(btrim(pattern)) > 0", name="pattern_not_empty"),)

    pattern: Mapped[str] = mapped_column(String(255), unique=True)
    normalized_merchant: Mapped[str] = mapped_column(String(255))
    default_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    default_category: Mapped[Category | None] = relationship()


class UserMerchantRule(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "user_merchant_rules"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant_key", name="uq_user_merchant_rules_user_key"),
        CheckConstraint("length(btrim(merchant_key)) > 0", name="merchant_key_not_empty"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    merchant_key: Mapped[str] = mapped_column(String(255))
    preferred_merchant_name: Mapped[str | None] = mapped_column(String(255))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    category: Mapped[Category | None] = relationship()
