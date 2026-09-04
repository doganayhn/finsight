from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, IdentityMixin, TimestampMixin
from app.db.types import Money, currency_check, enum_check, enum_type, finite_money_check
from app.modules.accounts.models import Account
from app.modules.categories.models import Category
from app.modules.imports.models import ImportBatch
from app.modules.transactions.enums import CategorySource, LinkType, ReviewStatus, TransactionType


class Transaction(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="CASCADE",
            name="fk_transactions_account_owner",
        ),
        ForeignKeyConstraint(
            ["import_batch_id", "account_id", "user_id"],
            ["import_batches.id", "import_batches.account_id", "import_batches.user_id"],
            ondelete="NO ACTION",
            name="fk_transactions_import_account_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_transactions_id_user"),
        currency_check(),
        enum_check("transaction_type", TransactionType),
        enum_check("category_source", CategorySource),
        enum_check("review_status", ReviewStatus),
        finite_money_check("amount"),
        finite_money_check("balance_after"),
        CheckConstraint("installment_index > 0", name="installment_index_positive"),
        CheckConstraint("installment_count > 0", name="installment_count_positive"),
        CheckConstraint("installment_index <= installment_count", name="installment_order"),
        CheckConstraint("source_row_number > 0", name="source_row_positive"),
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
        Index("ix_transactions_account_date", "account_id", "transaction_date"),
        Index("ix_transactions_user_merchant", "user_id", "merchant_normalized"),
        Index("ix_transactions_account_source", "account_id", "source_transaction_id"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[UUID] = mapped_column()
    import_batch_id: Mapped[UUID | None] = mapped_column(index=True)
    transaction_date: Mapped[date] = mapped_column(Date)
    posted_date: Mapped[date | None] = mapped_column(Date)
    description_raw: Mapped[str] = mapped_column(Text)
    merchant_raw: Mapped[str | None] = mapped_column(Text)
    merchant_normalized: Mapped[str | None] = mapped_column(String(255))
    # Account perspective: incoming positive, outgoing negative. No parser conversion here.
    amount: Mapped[Decimal] = mapped_column(Money())
    currency: Mapped[str] = mapped_column(String(3))
    transaction_type: Mapped[TransactionType] = mapped_column(
        enum_type(TransactionType, "transaction_type"),
        default=TransactionType.UNKNOWN,
        server_default="UNKNOWN",
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    balance_after: Mapped[Decimal | None] = mapped_column(Money())
    installment_index: Mapped[int | None] = mapped_column(SmallInteger)
    installment_count: Mapped[int | None] = mapped_column(SmallInteger)
    # Grouping only: deliberately no plan table or pairwise installment link.
    installment_plan_id: Mapped[UUID | None] = mapped_column()
    category_source: Mapped[CategorySource] = mapped_column(
        enum_type(CategorySource, "category_source"),
        default=CategorySource.UNKNOWN,
        server_default="UNKNOWN",
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_type(ReviewStatus, "review_status"),
        default=ReviewStatus.NEEDS_REVIEW,
        server_default="NEEDS_REVIEW",
    )
    # Not unique: reuse/overlap and legitimate identical transactions need later review.
    source_transaction_id: Mapped[str | None] = mapped_column(Text)
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    # No arbitrary JSONB/raw statement dump; selected provenance is explicitly modeled.
    account: Mapped[Account] = relationship(foreign_keys=[account_id, user_id])
    category: Mapped[Category | None] = relationship()
    # Read-only navigation avoids two relationships synchronizing the same owner columns.
    import_batch: Mapped[ImportBatch | None] = relationship(
        foreign_keys=[import_batch_id, account_id, user_id], viewonly=True
    )


class TransactionLink(IdentityMixin, CreatedAtMixin, Base):
    """REFUND_OF: refund -> purchase. Symmetric pairs store the smaller UUID first."""

    __tablename__ = "transaction_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            ondelete="CASCADE",
            name="fk_transaction_links_source_owner",
        ),
        ForeignKeyConstraint(
            ["target_transaction_id", "user_id"],
            ["transactions.id", "transactions.user_id"],
            ondelete="CASCADE",
            name="fk_transaction_links_target_owner",
        ),
        UniqueConstraint(
            "source_transaction_id",
            "target_transaction_id",
            "link_type",
            name="uq_transaction_links_pair_type",
        ),
        CheckConstraint("source_transaction_id != target_transaction_id", name="not_self"),
        enum_check("link_type", LinkType),
        CheckConstraint(
            "link_type = 'REFUND_OF' OR source_transaction_id < target_transaction_id",
            name="symmetric_order",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("linked_amount > 0", name="linked_amount_positive"),
        finite_money_check("linked_amount"),
        currency_check(),
        CheckConstraint(
            "(linked_amount IS NULL) = (currency IS NULL)", name="amount_currency_pair"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_transaction_id: Mapped[UUID] = mapped_column()
    target_transaction_id: Mapped[UUID] = mapped_column(index=True)
    link_type: Mapped[LinkType] = mapped_column(enum_type(LinkType, "link_type"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_user_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Positive allocation magnitude with explicit currency, e.g. a partial refund.
    linked_amount: Mapped[Decimal | None] = mapped_column(Money())
    currency: Mapped[str | None] = mapped_column(String(3))
    source_transaction: Mapped[Transaction] = relationship(
        foreign_keys=[source_transaction_id, user_id], viewonly=True
    )
    target_transaction: Mapped[Transaction] = relationship(
        foreign_keys=[target_transaction_id, user_id], viewonly=True
    )
