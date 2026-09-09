from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.analytics.schemas import (
    CategoryBucket,
    CategoryCurrency,
    CategoryResult,
    CompareQuery,
    CompareResult,
    ComparisonCurrency,
    CurrencySummary,
    ExplorerQuery,
    MerchantBucket,
    MerchantCurrency,
    MerchantQuery,
    MerchantResult,
    MonthBucket,
    Period,
    PeriodQuery,
    ProjectionCurrency,
    ProjectionQuery,
    ProjectionResult,
    SummaryResult,
    TransactionItem,
    TransactionPage,
    TrendCurrency,
    TrendResult,
)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class AnalyticsProblem(Exception):
    def __init__(self, code: str, status: int = 404):
        self.code, self.status = code, status
        super().__init__(code)


class AnalyticsService:
    """HTTP-independent validated query DTOs in, typed results out; no raw-row summation."""

    def __init__(self, session: Session, user_id: UUID):
        self.repo = AnalyticsRepository(session, user_id)

    def validate_account_scope(self, account_id: UUID | None) -> None:
        if account_id is not None and not self.repo.owns_account(account_id):
            raise AnalyticsProblem("account_not_found")

    def _scope(self, query):
        if query.account_id is not None and not self.repo.owns_account(query.account_id):
            raise AnalyticsProblem("account_not_found")
        return {"account_id": query.account_id, "currency_filter": query.currency}

    def _period_metadata(self, query):
        return self._scope(query) | {
            "period": Period(start_date=query.start_date, end_date=query.end_date)
        }

    @staticmethod
    def _currencies(rows, currency):
        return sorted({row["currency"] for row in rows} | ({currency} if currency else set()))

    def get_spending_summary(self, query: PeriodQuery) -> SummaryResult:
        metadata = self._period_metadata(query)
        rows = self.repo.totals(query)
        by_currency = {row["currency"]: row for row in rows}
        return SummaryResult(
            **metadata,
            currencies=[
                CurrencySummary(**by_currency.get(code, {"currency": code}))
                for code in self._currencies(rows, query.currency)
            ],
        )

    def get_category_breakdown(self, query: PeriodQuery) -> CategoryResult:
        metadata = self._period_metadata(query)
        rows = self.repo.categories(query)
        groups = defaultdict(list)
        for row in rows:
            groups[row["currency"]].append(CategoryBucket(**row))
        return CategoryResult(
            **metadata,
            currencies=[
                CategoryCurrency(currency=code, categories=groups[code])
                for code in self._currencies(rows, query.currency)
            ],
        )

    def get_merchant_breakdown(self, query: MerchantQuery) -> MerchantResult:
        metadata = self._period_metadata(query)
        rows = self.repo.merchants(query, query.limit)
        groups = defaultdict(list)
        for row in rows:
            groups[row["currency"]].append(MerchantBucket(**row))
        return MerchantResult(
            **metadata,
            limit_per_currency=query.limit,
            currencies=[
                MerchantCurrency(currency=code, merchants=groups[code])
                for code in self._currencies(rows, query.currency)
            ],
        )

    def get_monthly_trend(self, query: PeriodQuery) -> TrendResult:
        metadata = self._period_metadata(query)
        rows = self.repo.totals(query, monthly=True)
        by_month = {(row["currency"], row["month"].strftime("%Y-%m")): row for row in rows}
        months, cursor = [], query.start_date.replace(day=1)
        while cursor <= query.end_date:
            months.append(cursor.strftime("%Y-%m"))
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        return TrendResult(
            **metadata,
            currencies=[
                TrendCurrency(
                    currency=code,
                    months=[
                        MonthBucket(**(dict(by_month.get((code, month), {})) | {"month": month}))
                        for month in months
                    ],
                )
                for code in self._currencies(rows, query.currency)
            ],
        )

    def compare_periods(self, query: CompareQuery) -> CompareResult:
        metadata = self._scope(query)
        scope = {"account_id": query.account_id, "currency": query.currency}
        filtered_scope = scope | {"category_code": query.category_code}
        current = ExplorerQuery(
            start_date=query.current_start,
            end_date=query.current_end,
            limit=1,
            **filtered_scope,
        )
        previous = PeriodQuery(
            start_date=query.previous_start,
            end_date=query.previous_end,
            **scope,
        )
        if query.category_code is not None:
            previous = ExplorerQuery(
                start_date=query.previous_start,
                end_date=query.previous_end,
                limit=1,
                **filtered_scope,
            )
        rows = self.repo.compare(current, previous)
        amounts = {(row["period"], row["currency"]): row["net_spending"] for row in rows}
        results = []
        with localcontext() as context:
            context.prec = 50
            for code in self._currencies(rows, query.currency):
                now, before = (
                    amounts.get(("current", code), ZERO),
                    amounts.get(("previous", code), ZERO),
                )
                delta = now - before
                if before > ZERO:
                    percentage = (delta / before * 100).quantize(CENT, rounding=ROUND_HALF_UP)
                    state = "DEFINED"
                elif before == now == ZERO:
                    percentage, state = ZERO, "BOTH_ZERO"
                else:
                    percentage = None
                    state = "PREVIOUS_ZERO" if before == ZERO else "PREVIOUS_NEGATIVE"
                results.append(
                    ComparisonCurrency(
                        currency=code,
                        current_net_spending=now,
                        previous_net_spending=before,
                        absolute_change=delta,
                        percentage_change=percentage,
                        percentage_state=state,
                        direction="INCREASE"
                        if delta > ZERO
                        else "DECREASE"
                        if delta < ZERO
                        else "UNCHANGED",
                    )
                )
        return CompareResult(
            **metadata,
            current_period=Period(start_date=current.start_date, end_date=current.end_date),
            previous_period=Period(start_date=previous.start_date, end_date=previous.end_date),
            category_code=query.category_code,
            currencies=results,
        )

    def project_month_spending(self, query: ProjectionQuery) -> ProjectionResult:
        period = PeriodQuery(
            start_date=date(query.year, query.month, 1),
            end_date=query.as_of_date,
            account_id=query.account_id,
            currency=query.currency,
        )
        summary = self.get_spending_summary(period)
        results = []
        with localcontext() as context:
            context.prec = 50
            for row in summary.currencies:
                basis = max(row.net_spending, ZERO)
                daily = basis / Decimal(query.as_of_date.day)
                results.append(
                    ProjectionCurrency(
                        currency=row.currency,
                        observed_net_spending=row.net_spending,
                        projection_basis=basis,
                        average_daily_spending=daily.quantize(CENT, rounding=ROUND_HALF_UP),
                        projected_month_spending=(daily * query.days_in_month).quantize(
                            CENT, rounding=ROUND_HALF_UP
                        ),
                    )
                )
        return ProjectionResult(
            account_id=query.account_id,
            currency_filter=query.currency,
            month=f"{query.year:04d}-{query.month:02d}",
            as_of_date=query.as_of_date,
            elapsed_days=query.as_of_date.day,
            days_in_month=query.days_in_month,
            currencies=results,
        )

    def list_transactions(self, query: ExplorerQuery) -> TransactionPage:
        metadata = self._period_metadata(query)
        rows = self.repo.transactions(query)
        return TransactionPage(
            **metadata,
            limit=query.limit,
            offset=query.offset,
            has_more=len(rows) > query.limit,
            transactions=[TransactionItem.model_validate(row) for row in rows[: query.limit]],
        )
