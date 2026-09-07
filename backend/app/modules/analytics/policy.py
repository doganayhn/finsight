"""One spending policy for every SQL aggregation, independent of merchant/category labels."""

from decimal import Decimal

from sqlalchemy import Numeric, case, cast, func, literal

from app.modules.transactions.enums import TransactionType
from app.modules.transactions.models import Transaction

CONSUMER_TYPES = (TransactionType.EXPENSE, TransactionType.REFUND)


def metrics():
    # Cast away the per-row NUMERIC(18,2) type: aggregate totals may exceed one row's bounds.
    amount = cast(Transaction.amount, Numeric())
    zero = literal(Decimal("0.00"), type_=Numeric())

    def total(kind, value):
        return func.coalesce(
            func.sum(case((Transaction.transaction_type == kind, value), else_=zero)), zero
        )

    gross = total(TransactionType.EXPENSE, func.abs(amount))
    refunds = total(TransactionType.REFUND, func.greatest(amount, zero))
    return {
        "gross_spending": gross,
        "refunds": refunds,
        "net_spending": gross - refunds,
        "financial_fees": total(TransactionType.FEE, func.greatest(-amount, zero)),
        "cash_withdrawals": total(TransactionType.CASH_WITHDRAWAL, func.greatest(-amount, zero)),
        "expense_transaction_count": func.count().filter(
            Transaction.transaction_type == TransactionType.EXPENSE
        ),
        "refund_transaction_count": func.count().filter(
            Transaction.transaction_type == TransactionType.REFUND
        ),
    }


def breakdown_metrics():
    values = metrics()
    return {key: values[key] for key in ("gross_spending", "refunds", "net_spending")} | {
        "transaction_count": func.count(),
    }
