"""Explicit model registry for Alembic and persistence consumers."""

from app.modules.accounts.models import Account
from app.modules.auth.models import AuthSession, User
from app.modules.categories.models import Category
from app.modules.imports.models import ImportBatch
from app.modules.imports.staging import ImportTransactionCandidate
from app.modules.merchants.models import MerchantAlias, UserMerchantRule
from app.modules.transactions.models import Transaction, TransactionLink

__all__ = [
    "Account",
    "AuthSession",
    "User",
    "Category",
    "ImportBatch",
    "ImportTransactionCandidate",
    "MerchantAlias",
    "UserMerchantRule",
    "Transaction",
    "TransactionLink",
]
