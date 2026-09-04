from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin
from app.db.types import currency_check, enum_check, enum_type
from app.modules.accounts.enums import AccountType
from app.modules.auth.models import User


class Account(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_accounts_id_user"),
        currency_check(),
        enum_check("account_type", AccountType),
        CheckConstraint("account_number_masked ~ '^\\*{4}[0-9]{4}$'", name="masked_suffix_only"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Open provider code; CASH accounts need not have an institution.
    institution_code: Mapped[str | None] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[AccountType] = mapped_column(enum_type(AccountType, "account_type"))
    currency: Mapped[str] = mapped_column(String(3))
    # Only a canonical ****1234 suffix is accepted, never a full account/card number.
    account_number_masked: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    user: Mapped[User] = relationship()
