"""HTTP contracts: Decimal is serialized as a JSON string by Pydantic."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.imports.enums import ImportStatus, ValidationStatus
from app.modules.transactions.enums import TransactionType


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: dict[UUID, Literal["import", "skip"]] = Field(default_factory=dict)


class DuplicateMatch(BaseModel):
    kind: Literal["source_id", "heuristic", "candidate_source_id", "candidate_heuristic"]
    matched_id: UUID


class CandidatePreview(BaseModel):
    id: UUID
    transaction_date: date
    posted_date: date | None
    description_raw: str
    merchant_raw: str | None
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    source_transaction_id: str | None
    source_row_number: int
    source_page_number: int | None
    duplicate_matches: list[DuplicateMatch]


class ImportCounts(BaseModel):
    # valid + failed = total. duplicate is an overlapping subset of valid, not additive.
    total_rows: int
    valid_rows: int
    failed_rows: int
    duplicate_rows: int
    imported_rows: int
    # Completed valid_rows - imported_rows: only explicitly skipped current duplicates.
    skipped_duplicate_rows: int


class ParserProvenance(BaseModel):
    name: str | None
    version: str | None


class ImportPreview(BaseModel):
    import_batch_id: UUID
    status: ImportStatus
    institution_code: str | None
    statement_type: str | None
    currency: str | None
    statement_period: str | None
    parser: ParserProvenance
    reported_total: Decimal | None
    parsed_total: Decimal | None
    validation_status: ValidationStatus
    counts: ImportCounts
    transactions: list[CandidatePreview]
