from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from app.modules.transactions.enums import CategorySource, ReviewStatus, TransactionType

MoneyValue = Annotated[
    Decimal, PlainSerializer(lambda value: format(value, ".2f"), when_used="json")
]
CalendarDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(2100, 12, 31))]


class ScopeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    account_id: UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class Period(BaseModel):
    start_date: CalendarDate
    end_date: CalendarDate

    @model_validator(mode="after")
    def bounded_period(self) -> Self:
        if not 0 <= (self.end_date - self.start_date).days <= 3660:
            raise ValueError("Date range must be ordered and at most 3661 inclusive days")
        return self


class PeriodQuery(ScopeQuery, Period):
    pass


class MerchantQuery(PeriodQuery):
    limit: int = Field(default=10, ge=1, le=100)


class ExplorerQuery(PeriodQuery):
    category_id: UUID | None = None
    transaction_type: TransactionType | None = None
    review_status: ReviewStatus | None = None
    merchant_query: str | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)


class CompareQuery(ScopeQuery):
    current_start: CalendarDate
    current_end: CalendarDate
    previous_start: CalendarDate
    previous_end: CalendarDate

    @model_validator(mode="after")
    def valid_periods(self) -> Self:
        Period(start_date=self.current_start, end_date=self.current_end)
        Period(start_date=self.previous_start, end_date=self.previous_end)
        return self


class ProjectionQuery(ScopeQuery):
    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    as_of_date: CalendarDate

    @model_validator(mode="after")
    def date_in_month(self) -> Self:
        if (self.as_of_date.year, self.as_of_date.month) != (self.year, self.month):
            raise ValueError("as_of_date must belong to the requested calendar month")
        return self

    @property
    def days_in_month(self) -> int:
        return monthrange(self.year, self.month)[1]


class ScopedResult(BaseModel):
    data_scope: Literal["CANONICAL_TRANSACTIONS"] = "CANONICAL_TRANSACTIONS"
    account_id: UUID | None
    currency_filter: str | None


class PeriodResult(ScopedResult):
    period: Period


class SpendingMetrics(BaseModel):
    gross_spending: MoneyValue = Decimal("0.00")
    refunds: MoneyValue = Decimal("0.00")
    net_spending: MoneyValue = Decimal("0.00")
    financial_fees: MoneyValue = Decimal("0.00")
    cash_withdrawals: MoneyValue = Decimal("0.00")
    expense_transaction_count: int = 0
    refund_transaction_count: int = 0


class CurrencySummary(SpendingMetrics):
    currency: str


class SummaryResult(PeriodResult):
    currencies: list[CurrencySummary]


class BreakdownMetrics(BaseModel):
    gross_spending: MoneyValue
    refunds: MoneyValue
    net_spending: MoneyValue
    transaction_count: int


class CategoryBucket(BreakdownMetrics):
    category_id: UUID
    category_code: str
    category_name: str


class CategoryCurrency(BaseModel):
    currency: str
    categories: list[CategoryBucket]


class CategoryResult(PeriodResult):
    currencies: list[CategoryCurrency]


class MerchantBucket(BreakdownMetrics):
    merchant: str | None
    identity_source: Literal["NORMALIZED", "RAW", "UNKNOWN"]


class MerchantCurrency(BaseModel):
    currency: str
    merchants: list[MerchantBucket]


class MerchantResult(PeriodResult):
    limit_per_currency: int
    currencies: list[MerchantCurrency]


class MonthBucket(SpendingMetrics):
    month: str


class TrendCurrency(BaseModel):
    currency: str
    months: list[MonthBucket]


class TrendResult(PeriodResult):
    currencies: list[TrendCurrency]


class ComparisonCurrency(BaseModel):
    currency: str
    current_net_spending: MoneyValue
    previous_net_spending: MoneyValue
    absolute_change: MoneyValue
    percentage_change: MoneyValue | None
    percentage_state: Literal["DEFINED", "BOTH_ZERO", "PREVIOUS_ZERO", "PREVIOUS_NEGATIVE"]
    direction: Literal["INCREASE", "DECREASE", "UNCHANGED"]


class CompareResult(ScopedResult):
    current_period: Period
    previous_period: Period
    currencies: list[ComparisonCurrency]


class ProjectionCurrency(BaseModel):
    currency: str
    observed_net_spending: MoneyValue
    projection_basis: MoneyValue
    average_daily_spending: MoneyValue
    projected_month_spending: MoneyValue


class ProjectionResult(ScopedResult):
    month: str
    as_of_date: date
    elapsed_days: int
    days_in_month: int
    method: Literal["LINEAR_DAILY_RUN_RATE"] = "LINEAR_DAILY_RUN_RATE"
    assumptions: tuple[str, ...] = (
        "Observed canonical transactions only; source coverage may be incomplete.",
        "Inclusive elapsed calendar days; no transactions after as_of_date.",
        "Remaining days follow the observed daily pace; no seasonality assumption.",
        "Projection basis is max(observed net spending, 0); no balance or income forecast.",
    )
    currencies: list[ProjectionCurrency]


class TransactionCategory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    display_name: str


class TransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    transaction_date: date
    posted_date: date | None
    description_raw: str
    merchant_normalized: str | None
    amount: MoneyValue
    currency: str
    transaction_type: TransactionType
    category: TransactionCategory | None
    category_source: CategorySource
    review_status: ReviewStatus
    installment_index: int | None
    installment_count: int | None
    installment_plan_id: UUID | None


class TransactionPage(PeriodResult):
    limit: int
    offset: int
    has_more: bool
    transactions: list[TransactionItem]
