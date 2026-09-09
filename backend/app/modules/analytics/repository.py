from uuid import UUID

from sqlalchemy import Date, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, joinedload

from app.modules.accounts.models import Account
from app.modules.analytics.policy import CONSUMER_TYPES, breakdown_metrics, metrics
from app.modules.analytics.schemas import ExplorerQuery, PeriodQuery
from app.modules.categories.models import Category
from app.modules.transactions.models import Transaction


class AnalyticsRepository:
    def __init__(self, session: Session, user_id: UUID):
        self.session, self.user_id = session, user_id

    def owns_account(self, account_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(Account.id).where(Account.id == account_id, Account.user_id == self.user_id)
            )
            is not None
        )

    def conditions(self, query: PeriodQuery):
        # Canonical existence is the boundary; never read staging or parser metadata.
        conditions = [
            Transaction.user_id == self.user_id,
            Transaction.transaction_date.between(query.start_date, query.end_date),
        ]
        if query.account_id is not None:
            conditions.append(Transaction.account_id == query.account_id)
        if query.currency is not None:
            conditions.append(Transaction.currency == query.currency)
        if (category_code := getattr(query, "category_code", None)) is not None:
            category_id = (
                select(Category.id).where(Category.code == category_code).scalar_subquery()
            )
            other_id = select(Category.id).where(Category.code == "OTHER").scalar_subquery()
            conditions.append(func.coalesce(Transaction.category_id, other_id) == category_id)
        return conditions

    def totals(self, query: PeriodQuery, *, monthly: bool = False):
        keys = [Transaction.currency]
        if monthly:
            keys.append(
                cast(func.date_trunc("month", Transaction.transaction_date), Date).label("month")
            )
        statement = (
            select(*keys, *(value.label(key) for key, value in metrics().items()))
            .where(*self.conditions(query))
            .group_by(*keys)
            .order_by(*keys)
        )
        return self.session.execute(statement).mappings().all()

    def categories(self, query: PeriodQuery):
        other_id = select(Category.id).where(Category.code == "OTHER").scalar_subquery()
        category_id = func.coalesce(Transaction.category_id, other_id)
        keys = [
            Transaction.currency,
            Category.id.label("category_id"),
            Category.code.label("category_code"),
            Category.display_name.label("category_name"),
        ]
        statement = (
            select(*keys, *(value.label(key) for key, value in breakdown_metrics().items()))
            .select_from(Transaction)
            .join(Category, Category.id == category_id)
            .where(*self.conditions(query), Transaction.transaction_type.in_(CONSUMER_TYPES))
            .group_by(*keys)
            .order_by(
                Transaction.currency, breakdown_metrics()["net_spending"].desc(), Category.code
            )
        )
        return self.session.execute(statement).mappings().all()

    def compare(self, current: PeriodQuery, previous: PeriodQuery):
        # One SQL statement gives both periods the same PostgreSQL snapshot.
        statements = [
            select(
                literal(label).label("period"),
                Transaction.currency,
                metrics()["net_spending"].label("net_spending"),
            )
            .where(*self.conditions(query))
            .group_by(Transaction.currency)
            for label, query in (("current", current), ("previous", previous))
        ]
        return self.session.execute(union_all(*statements)).mappings().all()

    def merchants(self, query: PeriodQuery, limit: int):
        whitespace = " \t\r\n\v\f"
        normalized = func.nullif(func.btrim(Transaction.merchant_normalized, whitespace), "")
        raw = func.nullif(func.btrim(Transaction.merchant_raw, whitespace), "")
        usable_raw = func.length(raw).between(1, 120)
        merchant = case((normalized.is_not(None), normalized), (usable_raw, raw), else_=None)
        source = case((normalized.is_not(None), "NORMALIZED"), (usable_raw, "RAW"), else_="UNKNOWN")
        grouped = (
            select(
                Transaction.currency,
                merchant.label("merchant"),
                source.label("identity_source"),
                *(value.label(key) for key, value in breakdown_metrics().items()),
            )
            .where(*self.conditions(query), Transaction.transaction_type.in_(CONSUMER_TYPES))
            .group_by(Transaction.currency, merchant, source)
            .subquery()
        )
        ordering = (
            grouped.c.net_spending.desc(),
            grouped.c.merchant.collate("C").asc().nulls_last(),
            grouped.c.identity_source.asc(),
        )
        ranked = select(
            grouped,
            func.row_number()
            .over(partition_by=grouped.c.currency, order_by=ordering)
            .label("rank"),
        ).subquery()
        return (
            self.session.execute(
                select(ranked)
                .where(ranked.c.rank <= limit)
                .order_by(ranked.c.currency, ranked.c.rank)
            )
            .mappings()
            .all()
        )

    def transactions(self, query: ExplorerQuery):
        conditions = self.conditions(query)
        if query.category_id is not None:
            other_id = select(Category.id).where(Category.code == "OTHER").scalar_subquery()
            conditions.append(func.coalesce(Transaction.category_id, other_id) == query.category_id)
        for field in ("transaction_type", "review_status"):
            if (value := getattr(query, field)) is not None:
                conditions.append(getattr(Transaction, field) == value)
        if query.merchant_query is not None:
            # Bound parameters + escaped LIKE wildcards; no user-supplied SQL or fuzzy search.
            conditions.append(
                or_(
                    *(
                        column.icontains(query.merchant_query, autoescape=True)
                        for column in (
                            Transaction.merchant_normalized,
                            Transaction.merchant_raw,
                            Transaction.description_raw,
                        )
                    )
                )
            )
        statement = (
            select(Transaction)
            .options(joinedload(Transaction.category))
            .where(*conditions)
            .order_by(
                Transaction.transaction_date.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .offset(query.offset)
            .limit(query.limit + 1)
        )
        return self.session.scalars(statement).all()
