"""Bounded metadata-only history; never retrieves candidate or canonical descriptions."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.imports.enums import ImportStatus, ValidationStatus
from app.modules.imports.models import ImportBatch
from app.modules.imports.repository import ImportRepository

router = APIRouter(prefix="/imports", tags=["imports"])


class HistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)


class ImportHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    created_at: datetime
    institution_code: str | None
    statement_type: str | None
    statement_period: str | None
    currency: str | None
    import_status: ImportStatus
    validation_status: ValidationStatus
    reported_total: Decimal | None
    parsed_total: Decimal | None
    total_rows: int


class ImportHistoryPage(BaseModel):
    imports: list[ImportHistoryItem]
    limit: int
    offset: int
    has_more: bool


@router.get("", response_model=ImportHistoryPage)
def history(
    user_id: UserContext,
    query: Annotated[HistoryQuery, Query()],
    session: Annotated[Session, Depends(get_session)],
):
    conditions = [ImportBatch.user_id == user_id]
    if query.account_id is not None:
        ImportRepository(session).account(user_id, query.account_id)
        conditions.append(ImportBatch.account_id == query.account_id)
    columns = [getattr(ImportBatch, name) for name in ImportHistoryItem.model_fields]
    rows = (
        session.execute(
            select(*columns)
            .where(*conditions)
            .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
            .offset(query.offset)
            .limit(query.limit + 1)
        )
        .mappings()
        .all()
    )
    return ImportHistoryPage(
        imports=[ImportHistoryItem(**row) for row in rows[: query.limit]],
        limit=query.limit,
        offset=query.offset,
        has_more=len(rows) > query.limit,
    )
