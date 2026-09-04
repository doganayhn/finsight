"""Provider-neutral, temporary financial candidates; never raw document storage."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, IdentityMixin
from app.db.types import Money, currency_check, enum_check, enum_type, finite_money_check
from app.modules.transactions.enums import TransactionType


class ImportTransactionCandidate(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "import_transaction_candidates"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "source_row_number"),
        currency_check(),
        finite_money_check("amount"),
        enum_check("transaction_type", TransactionType),
        CheckConstraint("source_row_number > 0", name="source_row_positive"),
        CheckConstraint("source_page_number > 0", name="source_page_positive"),
    )

    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date)
    posted_date: Mapped[date | None] = mapped_column(Date)
    description_raw: Mapped[str] = mapped_column(Text)
    merchant_raw: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Money())
    currency: Mapped[str] = mapped_column(String(3))
    transaction_type: Mapped[TransactionType] = mapped_column(
        enum_type(TransactionType, "transaction_type")
    )
    source_transaction_id: Mapped[str | None] = mapped_column(Text)
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_page_number: Mapped[int | None] = mapped_column(Integer)
