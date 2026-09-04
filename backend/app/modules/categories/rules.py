"""Small static whole-token rules; no user/database-supplied regular expressions."""

import re

from app.modules.merchants.normalization import comparison_key
from app.modules.transactions.enums import TransactionType

MERCHANT_TYPES = frozenset(
    {TransactionType.EXPENSE, TransactionType.REFUND, TransactionType.CASH_WITHDRAWAL}
)
SEMANTIC_CATEGORIES = {
    TransactionType.INCOME: "INCOME",
    TransactionType.TRANSFER: "TRANSFER",
    TransactionType.CARD_PAYMENT: "TRANSFER",
    TransactionType.FEE: "FINANCIAL_FEES",
}
KEYWORDS = {
    "FUEL": frozenset(comparison_key(word) for word in ("AKARYAKIT", "PETROL")),
    "CAFE": frozenset(comparison_key(word) for word in ("CAFE", "COFFEE", "KAHVE")),
    "GROCERIES": frozenset({comparison_key("MARKET")}),
}


def keyword_category(context: str) -> str | None:
    tokens = set(re.findall(r"[^\W_]+", context))
    matches = [code for code, words in KEYWORDS.items() if tokens & words]
    # Conflicting signals are uncertain; deterministic does not imply confident.
    return matches[0] if len(matches) == 1 else None
