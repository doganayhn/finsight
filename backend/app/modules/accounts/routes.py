from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.accounts.enums import AccountType
from app.modules.accounts.models import Account

router = APIRouter(prefix="/accounts", tags=["accounts"])


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    display_name: str
    institution_code: str | None
    account_type: AccountType
    currency: str
    is_active: bool


class AccountPage(BaseModel):
    accounts: list[AccountResponse]
    limit: int
    offset: int
    has_more: bool


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    institution_code: str | None = Field(default=None, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    account_type: AccountType
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name must not be blank")
        return cleaned


@router.get("", response_model=AccountPage)
def list_accounts(
    user_id: UserContext,
    query: Annotated[PageQuery, Query()],
    session: Annotated[Session, Depends(get_session)],
):
    rows = session.scalars(
        select(Account)
        .where(Account.user_id == user_id)
        .order_by(Account.created_at, Account.id)
        .offset(query.offset)
        .limit(query.limit + 1)
    ).all()
    return AccountPage(
        accounts=[AccountResponse.model_validate(row) for row in rows[: query.limit]],
        limit=query.limit,
        offset=query.offset,
        has_more=len(rows) > query.limit,
    )


@router.post("", response_model=AccountResponse, status_code=201)
def create_account(
    body: AccountCreate,
    user_id: UserContext,
    session: Annotated[Session, Depends(get_session)],
):
    account = Account(
        user_id=user_id,
        display_name=body.display_name,
        institution_code=body.institution_code,
        account_type=body.account_type,
        currency=body.currency,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return AccountResponse.model_validate(account)
