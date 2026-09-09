from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.transactions.enums import ReviewStatus, TransactionType


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


CalendarDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(2100, 12, 31))]


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    account_id: UUID | None = None
    client_timezone: str = Field(default="Europe/Istanbul", min_length=1, max_length=64)


class UsedTool(BaseModel):
    name: str
    label: str


class AssistantScope(BaseModel):
    account_id: UUID | None
    data_scope: Literal["CANONICAL_TRANSACTIONS"] = "CANONICAL_TRANSACTIONS"


class AssistantChatResponse(BaseModel):
    answer: str
    used_tools: list[UsedTool]
    scope: AssistantScope


class AssistantStatus(BaseModel):
    enabled: bool
    provider: Literal["Groq"] = "Groq"
    model: str


class PeriodToolArgs(StrictModel):
    start_date: CalendarDate
    end_date: CalendarDate
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 3660:
            raise ValueError("Invalid date range")
        return self


class MerchantToolArgs(PeriodToolArgs):
    limit: int = Field(default=10, ge=1, le=10)


class CompareToolArgs(StrictModel):
    current_start: CalendarDate
    current_end: CalendarDate
    previous_start: CalendarDate
    previous_end: CalendarDate
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    category_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")

    @model_validator(mode="after")
    def valid_periods(self) -> Self:
        PeriodToolArgs(start_date=self.current_start, end_date=self.current_end)
        PeriodToolArgs(start_date=self.previous_start, end_date=self.previous_end)
        return self


class ProjectionToolArgs(StrictModel):
    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    as_of_date: CalendarDate
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def date_in_month(self) -> Self:
        if (self.as_of_date.year, self.as_of_date.month) != (self.year, self.month):
            raise ValueError("as_of_date must be in year/month")
        return self


class SearchTransactionsToolArgs(PeriodToolArgs):
    category_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    transaction_type: TransactionType | None = None
    review_status: ReviewStatus | None = None
    merchant_query: str | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=20)
