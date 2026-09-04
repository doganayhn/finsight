"""Provider-neutral, in-memory import DTOs; no ORM or persistence dependency."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.modules.imports.enums import ValidationStatus
from app.modules.transactions.enums import TransactionType


def _money(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Money must be a finite Decimal")
    if abs(value) >= Decimal("10000000000000000") or value != value.quantize(Decimal("0.01")):
        raise ValueError("Money must fit NUMERIC(18,2) without rounding")


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    number: int
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]


@dataclass(frozen=True, slots=True)
class CanonicalTransactionCandidate:
    transaction_date: date
    description_raw: str = field(repr=False)
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    source_row_number: int
    source_page_number: int
    merchant_raw: str | None = field(default=None, repr=False)
    posted_date: date | None = None

    def __post_init__(self):
        _money(self.amount)
        if type(self.transaction_date) is not date:
            raise ValueError("Transaction date must be a date")
        if self.posted_date is not None and type(self.posted_date) is not date:
            raise ValueError("Posting date must be a date")
        if len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isupper():
            raise ValueError("Currency must be three uppercase ASCII letters")
        if not self.currency.isalpha():
            raise ValueError("Currency must be three uppercase ASCII letters")
        if self.source_row_number < 1 or self.source_page_number < 1:
            raise ValueError("Source positions must be positive")


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    institution_code: str
    statement_type: str
    currency: str
    # YYYY-MM label; a monthly label does not assert exact billing start/end dates.
    statement_period: str
    reported_total: Decimal
    transactions: tuple[CanonicalTransactionCandidate, ...] = field(repr=False)
    parser_name: str
    parser_version: str
    statement_period_start: date | None = None
    statement_period_end: date | None = None

    def __post_init__(self):
        _money(self.reported_total)


@dataclass(frozen=True, slots=True)
class StatementValidation:
    status: ValidationStatus
    reported_total: Decimal
    parsed_purchase_magnitude: Decimal
    qualifying_purchase_count: int
    issues: tuple[str, ...] = ()

    def require_passed(self) -> None:
        from app.modules.imports.exceptions import StatementValidationError

        if self.status != ValidationStatus.PASSED:
            raise StatementValidationError("Statement validation did not pass")
