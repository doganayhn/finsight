from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.categories.rules import MERCHANT_TYPES, SEMANTIC_CATEGORIES
from app.modules.merchants.normalization import merchant_rule_key
from app.modules.merchants.repository import MerchantRepository
from app.modules.transactions.enums import CategorySource, ReviewStatus
from app.modules.transactions.models import Transaction


class ClassificationProblem(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preferred_merchant_name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: UUID | None = None
    persist_as_rule: bool = False

    @model_validator(mode="after")
    def explicit_changes(self) -> Self:
        fields = self.model_fields_set & {"preferred_merchant_name", "category_id"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Provide a non-null merchant name or category")
        return self


class ClassificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_normalized: str | None
    category_id: UUID | None
    category_source: CategorySource
    review_status: ReviewStatus


class CorrectionService:
    def __init__(self, session: Session):
        self.session = session

    def correct(self, user_id: UUID, transaction_id: UUID, body: CorrectionRequest):
        with self.session.begin():
            transaction = self.session.scalar(
                select(Transaction)
                .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
                .with_for_update()
            )
            if transaction is None:
                raise ClassificationProblem("transaction_not_found", 404)
            category = None
            if body.category_id is not None:
                category = self.session.scalar(
                    select(Category).where(Category.id == body.category_id, Category.is_system)
                )
                if category is None:
                    raise ClassificationProblem("category_not_found", 422)
            if transaction.transaction_type not in MERCHANT_TYPES:
                # Non-merchant financial types never inherit spending rules or merchant names.
                allowed = {"OTHER", SEMANTIC_CATEGORIES.get(transaction.transaction_type)}
                if (
                    body.preferred_merchant_name is not None
                    or body.persist_as_rule
                    or (category is not None and category.code not in allowed)
                ):
                    raise ClassificationProblem("classification_incompatible_with_type", 422)
            changes = {}
            if body.preferred_merchant_name is not None:
                transaction.merchant_normalized = body.preferred_merchant_name
                changes["preferred_merchant_name"] = body.preferred_merchant_name
            if category is not None:
                transaction.category_id = category.id
                transaction.category_source = CategorySource.USER
                changes["category_id"] = category.id
            transaction.review_status = ReviewStatus.USER_CONFIRMED
            if body.persist_as_rule:
                MerchantRepository(self.session).upsert_rule(
                    user_id,
                    merchant_rule_key(transaction.description_raw, transaction.merchant_raw),
                    changes,
                )
            self.session.flush()
            return ClassificationResponse.model_validate(transaction)
