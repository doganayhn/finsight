from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import IdentityMixin, TimestampMixin
from app.db.types import Money, currency_check, enum_check, enum_type, finite_money_check
from app.modules.accounts.models import Account
from app.modules.imports.enums import FileFormat, ImportStatus, SourceType, ValidationStatus


class ImportBatch(IdentityMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "user_id"],
            ["accounts.id", "accounts.user_id"],
            ondelete="CASCADE",
            name="fk_import_batches_account_owner",
        ),
        UniqueConstraint("id", "account_id", "user_id", name="uq_import_batches_id_account_user"),
        CheckConstraint("file_hash ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        CheckConstraint("statement_period_start <= statement_period_end", name="period_order"),
        CheckConstraint(
            "total_rows >= 0 AND valid_rows >= 0 AND duplicate_rows >= 0 AND failed_rows >= 0",
            name="nonnegative_counters",
        ),
        CheckConstraint(
            "(reported_total IS NULL AND parsed_total IS NULL) OR currency IS NOT NULL",
            name="totals_require_currency",
        ),
        currency_check(),
        enum_check("source_type", SourceType),
        enum_check("file_format", FileFormat),
        enum_check("validation_status", ValidationStatus),
        enum_check("import_status", ImportStatus),
        finite_money_check("reported_total"),
        finite_money_check("parsed_total"),
        Index("ix_import_batches_user_account_hash", "user_id", "account_id", "file_hash"),
        Index("ix_import_batches_account_id", "account_id"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[UUID] = mapped_column()
    source_type: Mapped[SourceType] = mapped_column(enum_type(SourceType, "source_type"))
    file_format: Mapped[FileFormat] = mapped_column(enum_type(FileFormat, "file_format"))
    institution_code: Mapped[str | None] = mapped_column(String(100))
    statement_type: Mapped[str | None] = mapped_column(String(100))
    # Basename only in the future upload layer; never a raw file body/path.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    parser_name: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    statement_period_start: Mapped[date | None] = mapped_column(Date)
    statement_period_end: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    reported_total: Mapped[Decimal | None] = mapped_column(Money())
    parsed_total: Mapped[Decimal | None] = mapped_column(Money())
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    validation_status: Mapped[ValidationStatus] = mapped_column(
        enum_type(ValidationStatus, "validation_status"),
        default=ValidationStatus.NOT_AVAILABLE,
        server_default="NOT_AVAILABLE",
    )
    import_status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, "import_status"),
        default=ImportStatus.PENDING,
        server_default="PENDING",
    )
    account: Mapped[Account] = relationship(foreign_keys=[account_id, user_id])
