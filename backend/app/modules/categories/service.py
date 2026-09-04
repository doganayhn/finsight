"""Provider-neutral classification with no network clients or financial calculations."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.categories.repository import CategoryRepository
from app.modules.categories.rules import MERCHANT_TYPES, SEMANTIC_CATEGORIES, keyword_category
from app.modules.merchants.normalization import (
    comparison_key,
    merchant_context,
    merchant_rule_key,
)
from app.modules.merchants.repository import MerchantRepository
from app.modules.transactions.enums import CategorySource, ReviewStatus, TransactionType


@dataclass(frozen=True)
class ClassificationResult:
    merchant_normalized: str | None
    category_id: UUID
    category_source: CategorySource
    review_status: ReviewStatus
    matched_rule: str

    def apply(self, transaction):
        for field in ("merchant_normalized", "category_id", "category_source", "review_status"):
            setattr(transaction, field, getattr(self, field))


class ClassificationService:
    def __init__(self, session: Session, user_id: UUID):
        # One catalog/rule snapshot per confirmation, within its existing transaction.
        self.categories = {row.code: row.id for row in CategoryRepository(session).catalog()}
        repository = MerchantRepository(session)
        self.rules = {row.merchant_key: row for row in repository.user_rules(user_id)}
        self.aliases = sorted(
            ((comparison_key(row.pattern), row) for row in repository.aliases()),
            key=lambda pair: (-len(pair[0]), pair[0], pair[1].pattern, str(pair[1].id)),
        )

    def classify(
        self, description_raw: str, merchant_raw: str | None, transaction_type: TransactionType
    ) -> ClassificationResult:
        merchant, category, source, matched = None, None, CategorySource.UNKNOWN, "unresolved"
        if transaction_type in MERCHANT_TYPES:
            context = merchant_context(description_raw, merchant_raw)
            rule = self.rules.get(merchant_rule_key(description_raw, merchant_raw))
            if rule:
                merchant, category = rule.preferred_merchant_name, rule.category_id
                if category is not None:
                    source, matched = CategorySource.USER, "user_rule"
            alias = next(
                (row for pattern, row in self.aliases if pattern and pattern in context), None
            )
            if alias:
                if merchant is None:
                    merchant = alias.normalized_merchant
                if category is None and alias.default_category_id is not None:
                    category = alias.default_category_id
                    source, matched = CategorySource.MERCHANT_RULE, f"alias:{alias.id}"
            if category is None and (code := keyword_category(context)):
                category = self.categories[code]
                source, matched = CategorySource.SYSTEM_RULE, f"keyword:{code}"
        elif code := SEMANTIC_CATEGORIES.get(transaction_type):
            category = self.categories[code]
            source, matched = CategorySource.SYSTEM_RULE, f"type:{transaction_type}"
        return ClassificationResult(
            merchant_normalized=merchant,
            category_id=category if category is not None else self.categories["OTHER"],
            category_source=source,
            review_status=ReviewStatus.NEEDS_REVIEW
            if source == CategorySource.UNKNOWN
            else ReviewStatus.AUTO_CONFIRMED,
            matched_rule=matched,
        )
