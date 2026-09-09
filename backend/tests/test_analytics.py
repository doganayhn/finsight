import socket
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pdf_factory import synthetic_pdf
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_imports import TEXT, confirm, upload

from app.modules.accounts.models import Account
from app.modules.analytics.schemas import (
    CompareQuery,
    ExplorerQuery,
    MerchantQuery,
    PeriodQuery,
    ProjectionQuery,
)
from app.modules.analytics.service import AnalyticsProblem, AnalyticsService
from app.modules.categories.models import Category
from app.modules.imports.models import ImportBatch
from app.modules.transactions.models import Transaction

AUGUST = {"start_date": "2026-08-01", "end_date": "2026-08-31"}


def get(context, endpoint, params=None, *, user=None):
    return context[0].get(
        "/api/v1/" + endpoint,
        params=AUGUST if params is None else params,
        headers={"X-Dev-User-ID": str(user or context[1])},
    )


def currency_row(response, currency="TRY"):
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["currencies"] if row["currency"] == currency)


@pytest.fixture
def data(context, db_engine):
    """Invented transactions; no private source files or today's date."""
    with Session(db_engine) as session, session.begin():
        categories = {row.code: row.id for row in session.scalars(select(Category))}
        second, usd, other = uuid4(), uuid4(), uuid4()
        session.add_all(
            [
                Account(
                    id=second,
                    user_id=context[1],
                    display_name="Synthetic second",
                    account_type="CASH",
                    currency="TRY",
                ),
                Account(
                    id=usd,
                    user_id=context[1],
                    display_name="Synthetic dollar",
                    account_type="CASH",
                    currency="USD",
                ),
                Account(
                    id=other,
                    user_id=context[2],
                    display_name="Synthetic other",
                    account_type="CASH",
                    currency="EUR",
                ),
            ]
        )
        session.flush()
        # Deliberately unrelated billing label: calendar transaction dates drive results.
        batch = ImportBatch(
            user_id=context[1],
            account_id=context[3],
            source_type="MANUAL_UPLOAD",
            file_format="PDF",
            import_status="COMPLETED",
            statement_period="2020-01",
        )
        session.add(batch)
        session.flush()
        rows = []

        def add(
            amount,
            kind="EXPENSE",
            category="SHOPPING",
            merchant="Demo Shop",
            day="2026-08-15",
            account=None,
            user=None,
            currency="TRY",
            **kwargs,
        ):
            row = Transaction(
                id=uuid4(),
                user_id=user or context[1],
                account_id=account or context[3],
                transaction_date=date.fromisoformat(day),
                amount=Decimal(amount),
                currency=currency,
                description_raw="SYNTHETIC " + (merchant or "Unidentified"),
                merchant_raw="RAW DEMO",
                merchant_normalized=merchant,
                transaction_type=kind,
                category_id=categories[category] if category else None,
                category_source="SYSTEM_RULE",
                review_status="AUTO_CONFIRMED",
                created_at=datetime(2026, 8, 20, tzinfo=UTC),
                **kwargs,
            )
            session.add(row)
            rows.append(row)
            return row

        groceries = add(
            "-1000",
            category="GROCERIES",
            merchant="Demo Groceries",
            day="2026-08-01",
            import_batch_id=batch.id,
        )
        cafe = add("-200", category="CAFE", merchant="Demo Cafe")
        shopping = add("-500", merchant="Demo Shop", day="2026-08-31")
        add("100", "REFUND", merchant="Demo Shop")
        for amount, kind in [
            ("-5000", "TRANSFER"),
            ("-3000", "CARD_PAYMENT"),
            ("-25", "FEE"),
            ("-1000", "CASH_WITHDRAWAL"),
            ("10000", "INCOME"),
            ("-700", "UNKNOWN"),
            ("-30", "INTEREST"),
        ]:
            add(amount, kind, merchant="Demo Groceries", category="GROCERIES")
        add("-800", day="2026-07-15")
        add("-999", day="2026-09-01")
        add("-50", category="OTHER", merchant=None, account=second)
        add("-10", category=None, merchant=None, account=second)
        add("20", "REFUND", category=None, merchant=None, account=second)
        add("-5000", account=second, installment_index=2, installment_count=6)
        add("-100", account=usd, currency="USD")
        add("-9876", account=other, user=context[2], currency="EUR")
        session.flush()
        session.get(Transaction, cafe.id).review_status = "NEEDS_REVIEW"
        for row in rows:
            if row.category_id in {None, categories["OTHER"]}:
                row.review_status = "NEEDS_REVIEW"
        return {
            "categories": categories,
            "second": second,
            "usd": usd,
            "other": other,
            "groceries": groceries.id,
            "cafe": cafe.id,
            "shopping": shopping.id,
        }


def test_authoritative_summary_core_scenario_and_decimal_strings(context, data):
    result = get(context, "analytics/summary", AUGUST | {"account_id": str(context[3])})
    row = currency_row(result)
    assert row == {
        "currency": "TRY",
        "gross_spending": "1700.00",
        "refunds": "100.00",
        "net_spending": "1600.00",
        "financial_fees": "25.00",
        "cash_withdrawals": "1000.00",
        "expense_transaction_count": 3,
        "refund_transaction_count": 1,
    }
    assert result.json()["data_scope"] == "CANONICAL_TRANSACTIONS"
    assert result.json()["period"] == AUGUST


def test_currencies_accounts_installments_and_needs_review(context, data):
    result = get(context, "analytics/summary")
    assert [row["currency"] for row in result.json()["currencies"]] == ["TRY", "USD"]
    row = currency_row(result)
    assert row["gross_spending"] == "6760.00"  # Includes only 5000 for installment 2/6.
    assert row["refunds"] == "120.00" and row["net_spending"] == "6640.00"
    assert currency_row(result, "USD")["net_spending"] == "100.00"
    filtered = get(context, "analytics/summary", AUGUST | {"currency": "USD"})
    assert len(filtered.json()["currencies"]) == 1
    assert currency_row(filtered, "USD")["net_spending"] == "100.00"


def test_category_netting_and_null_other_bucket(context, data):
    result = get(context, "analytics/categories")
    groups = currency_row(result)["categories"]
    assert [row["category_code"] for row in groups] == ["SHOPPING", "GROCERIES", "CAFE", "OTHER"]
    by_code = {row["category_code"]: row for row in groups}
    assert by_code["SHOPPING"]["net_spending"] == "5400.00"
    assert by_code["OTHER"]["gross_spending"] == "60.00"
    assert by_code["OTHER"]["refunds"] == "20.00"
    assert by_code["OTHER"]["net_spending"] == "40.00"
    assert by_code["OTHER"]["transaction_count"] == 3
    assert by_code["CAFE"]["gross_spending"] == "200.00"  # NEEDS_REVIEW still counts.


def test_merchant_preference_exact_refund_identity_and_limit(context, data):
    result = get(context, "analytics/merchants", AUGUST | {"account_id": str(context[3])})
    rows = currency_row(result)["merchants"]
    assert [(row["merchant"], row["net_spending"]) for row in rows] == [
        ("Demo Groceries", "1000.00"),
        ("Demo Shop", "400.00"),
        ("Demo Cafe", "200.00"),
    ]
    assert all(row["identity_source"] == "NORMALIZED" for row in rows)
    top = get(context, "analytics/merchants", AUGUST | {"limit": 1})
    assert len(currency_row(top)["merchants"]) == len(currency_row(top, "USD")["merchants"]) == 1


def test_merchant_fallback_is_bounded_and_does_not_guess_from_description(context, data, db_engine):
    with Session(db_engine) as session, session.begin():
        first = session.get(Transaction, data["groceries"])
        first.merchant_normalized = "  "
        first.merchant_raw = "  Demo raw  "
        second = session.get(Transaction, data["cafe"])
        second.merchant_normalized = None
        second.merchant_raw = "x" * 121
        third = session.get(Transaction, data["shopping"])
        third.merchant_normalized = None
        third.merchant_raw = " \t\n "
    result = get(context, "analytics/merchants", AUGUST | {"account_id": str(context[3])})
    rows = currency_row(result)["merchants"]
    assert [(row["merchant"], row["identity_source"]) for row in rows] == [
        ("Demo raw", "RAW"),
        (None, "UNKNOWN"),
        ("Demo Shop", "NORMALIZED"),
    ]
    assert rows[1]["gross_spending"] == "700.00"
    assert rows[2]["net_spending"] == "-100.00"  # Refund identity not inferred from its amount.
    assert "SYNTHETIC" not in result.text and "x" * 121 not in result.text


def test_trend_zero_months_inclusive_partial_months_and_currencies(context, data):
    result = get(context, "analytics/trend", {"start_date": "2026-06-01", "end_date": "2026-09-01"})
    rows = currency_row(result)["months"]
    assert [row["month"] for row in rows] == ["2026-06", "2026-07", "2026-08", "2026-09"]
    assert [row["net_spending"] for row in rows] == ["0.00", "800.00", "6640.00", "999.00"]
    usd = currency_row(result, "USD")["months"]
    assert [row["net_spending"] for row in usd] == ["0.00", "0.00", "100.00", "0.00"]
    partial = get(
        context,
        "analytics/trend",
        {"start_date": "2026-08-02", "end_date": "2026-08-30", "account_id": str(context[3])},
    )
    assert currency_row(partial)["months"][0]["net_spending"] == "100.00"


@pytest.mark.parametrize(
    "current,previous,direction,percentage,state",
    [
        ("08", "07", "INCREASE", "100.00", "DEFINED"),
        ("07", "08", "DECREASE", "-50.00", "DEFINED"),
        ("08", "08", "UNCHANGED", "0.00", "DEFINED"),
        ("08", "06", "INCREASE", None, "PREVIOUS_ZERO"),
        ("06", "08", "DECREASE", "-100.00", "DEFINED"),
        ("06", "06", "UNCHANGED", "0.00", "BOTH_ZERO"),
    ],
)
def test_comparison_percentages(context, data, current, previous, direction, percentage, state):
    params = {
        "current_start": f"2026-{current}-01",
        "current_end": f"2026-{current}-31" if current != "06" else "2026-06-30",
        "previous_start": f"2026-{previous}-01",
        "previous_end": f"2026-{previous}-31" if previous != "06" else "2026-06-30",
        "account_id": str(context[3]),
        "currency": "TRY",
    }
    row = currency_row(get(context, "analytics/compare", params))
    assert row["direction"] == direction and row["percentage_change"] == percentage
    assert row["percentage_state"] == state
    assert Decimal(row["absolute_change"]) == Decimal(row["current_net_spending"]) - Decimal(
        row["previous_net_spending"]
    )


def test_projection_uses_as_of_net_not_future_rows_income_or_fees(context, data):
    row = currency_row(
        get(
            context,
            "analytics/projection",
            {"year": 2026, "month": 8, "as_of_date": "2026-08-15", "account_id": str(context[3])},
        )
    )
    assert row == {
        "currency": "TRY",
        "observed_net_spending": "1100.00",
        "projection_basis": "1100.00",
        "average_daily_spending": "73.33",
        "projected_month_spending": "2273.33",
    }
    # Projection uses unrounded 1100 / 15, not displayed rounded 73.33.


def test_projection_leap_year_zero_and_negative_refund_basis(context, db_engine):
    with Session(db_engine) as session, session.begin():
        session.add(
            Transaction(
                user_id=context[1],
                account_id=context[3],
                transaction_date=date(2024, 2, 10),
                description_raw="SYNTHETIC",
                transaction_type="EXPENSE",
                amount=Decimal("-100.00"),
                currency="TRY",
            )
        )
        session.add(
            Transaction(
                user_id=context[1],
                account_id=context[3],
                transaction_date=date(2024, 2, 11),
                description_raw="SYNTHETIC REFUND",
                transaction_type="REFUND",
                amount=Decimal("150.00"),
                currency="TRY",
            )
        )
    result = get(
        context, "analytics/projection", {"year": 2024, "month": 2, "as_of_date": "2024-02-10"}
    )
    assert result.json()["days_in_month"] == 29 and result.json()["elapsed_days"] == 10
    assert currency_row(result)["projected_month_spending"] == "290.00"
    negative = get(
        context, "analytics/projection", {"year": 2024, "month": 2, "as_of_date": "2024-02-11"}
    )
    assert currency_row(negative)["observed_net_spending"] == "-50.00"
    assert currency_row(negative)["projected_month_spending"] == "0.00"
    zero = get(
        context,
        "analytics/projection",
        {"year": 2024, "month": 2, "as_of_date": "2024-02-01", "currency": "TRY"},
    )
    assert currency_row(zero)["projected_month_spending"] == "0.00"
    assert result.json()["method"] == "LINEAR_DAILY_RUN_RATE"
    assert not {"current_balance", "salary", "remaining_money", "net_worth"} & result.json().keys()


def test_explorer_filters_order_pagination_and_safe_fields(context, data, db_engine):
    params = AUGUST | {"account_id": str(context[3]), "transaction_type": "EXPENSE", "limit": 1}
    first = get(context, "transactions", params).json()
    second = get(context, "transactions", params | {"offset": 1}).json()
    third = get(context, "transactions", params | {"offset": 2}).json()
    assert first["has_more"] and second["has_more"] and not third["has_more"]
    assert [page["transactions"][0]["id"] for page in [first, second, third]] == [
        str(data[key]) for key in ("shopping", "cafe", "groceries")
    ]
    for row in first["transactions"]:
        assert isinstance(row["amount"], str)
        assert (
            not {
                "user_id",
                "source_transaction_id",
                "source_row_number",
                "import_batch_id",
                "balance_after",
                "merchant_raw",
            }
            & row.keys()
        )
        assert row["category"]["code"] == "SHOPPING"
    filtered = get(
        context,
        "transactions",
        AUGUST
        | {
            "category_id": str(data["categories"]["CAFE"]),
            "review_status": "NEEDS_REVIEW",
            "merchant_query": "demo cafe",
            "currency": "TRY",
        },
    )
    assert [row["id"] for row in filtered.json()["transactions"]] == [str(data["cafe"])]
    other = get(context, "transactions", AUGUST | {"category_id": str(data["categories"]["OTHER"])})
    assert len(other.json()["transactions"]) == 3
    tied = get(
        context,
        "transactions",
        AUGUST | {"start_date": "2026-08-15", "end_date": "2026-08-15", "limit": 100},
    ).json()["transactions"]
    assert [row["id"] for row in tied] == sorted((row["id"] for row in tied), reverse=True)
    assert (
        get(context, "transactions", AUGUST | {"merchant_query": "%"}).json()["transactions"] == []
    )
    assert (
        get(context, "transactions", AUGUST | {"merchant_query": "' OR 1=1 --"}).json()[
            "transactions"
        ]
        == []
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "analytics/summary",
        "analytics/categories",
        "analytics/merchants",
        "analytics/trend",
        "analytics/compare",
        "analytics/projection",
        "transactions",
    ],
)
def test_every_endpoint_enforces_ownership(context, data, endpoint):
    params = dict(AUGUST)
    if endpoint.endswith("compare"):
        params = {
            "current_start": "2026-08-01",
            "current_end": "2026-08-31",
            "previous_start": "2026-07-01",
            "previous_end": "2026-07-31",
        }
    elif endpoint.endswith("projection"):
        params = {"year": 2026, "month": 8, "as_of_date": "2026-08-15"}
    other = get(context, endpoint, params | {"account_id": str(data["other"])})
    absent = get(context, endpoint, params | {"account_id": str(uuid4())})
    assert other.status_code == absent.status_code == 404
    assert other.json() == absent.json() == {"detail": {"code": "account_not_found"}}
    own = get(context, endpoint, params)
    assert own.status_code == 200
    assert (
        "9876" not in own.text
        and str(context[2]) not in own.text
        and str(data["other"]) not in own.text
    )


@pytest.mark.parametrize(
    "endpoint,params",
    [
        ("analytics/summary", {"start_date": "2026-08-31", "end_date": "2026-08-01"}),
        ("analytics/trend", {"start_date": "1900-01-01", "end_date": "2100-01-01"}),
        ("analytics/summary", AUGUST | {"currency": "try"}),
        ("analytics/summary", AUGUST | {"currency": "TRY,USD"}),
        ("analytics/merchants", AUGUST | {"limit": 0}),
        ("analytics/merchants", AUGUST | {"limit": 101}),
        ("transactions", AUGUST | {"limit": 101}),
        ("transactions", AUGUST | {"offset": -1}),
        ("transactions", AUGUST | {"offset": 100001}),
        ("transactions", AUGUST | {"transaction_type": "NOT_A_TYPE"}),
        ("transactions", AUGUST | {"merchant_query": " "}),
        ("analytics/projection", {"year": 2024, "month": 2, "as_of_date": "2024-03-01"}),
        ("analytics/projection", {"year": 2024, "month": 13, "as_of_date": "2024-02-01"}),
        ("analytics/projection", {"year": 2023, "month": 2, "as_of_date": "2023-02-29"}),
        ("analytics/summary", {}),
        ("analytics/summary", AUGUST | {"unexpected": "PRIVATE_SENTINEL"}),
    ],
)
def test_invalid_queries_are_safe(context, endpoint, params):
    response = get(context, endpoint, params)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}


def test_empty_period_and_development_only_context(context):
    result = get(context, "analytics/summary")
    assert result.json()["currencies"] == []
    filtered = get(context, "analytics/trend", AUGUST | {"currency": "TRY"})
    assert currency_row(filtered)["months"][0]["net_spending"] == "0.00"
    assert context[0].get("/api/v1/analytics/summary", params=AUGUST).status_code == 422
    context[4].app_env = "production"
    assert get(context, "analytics/summary").status_code == 403


def test_services_use_sql_aggregation_with_bounded_queries(context, data, db_engine):
    statements = []

    def capture(connection, cursor, statement, parameters, ctx, executemany):
        statements.append(statement)

    with Session(db_engine) as session:
        event.listen(db_engine, "before_cursor_execute", capture)
        try:
            service = AnalyticsService(session, context[1])
            query = PeriodQuery(**AUGUST)
            summary = service.get_spending_summary(query)
            assert summary.currencies[0].net_spending == Decimal("6640.00")
            assert len(statements) == 1 and "sum(" in statements[0].lower()
            statements.clear()
            service.get_category_breakdown(query)
            assert len(statements) == 1 and "group by" in statements[0].lower()
            statements.clear()
            service.get_merchant_breakdown(MerchantQuery(**AUGUST))
            assert len(statements) == 1 and "row_number()" in statements[0].lower()
            statements.clear()
            service.compare_periods(
                CompareQuery(
                    current_start="2026-08-01",
                    current_end="2026-08-31",
                    previous_start="2026-07-01",
                    previous_end="2026-07-31",
                )
            )
            assert len(statements) == 1 and "union all" in statements[0].lower()
            statements.clear()
            service.list_transactions(ExplorerQuery(**AUGUST))
            assert len(statements) == 1 and "join categories" in statements[0].lower()
        finally:
            event.remove(db_engine, "before_cursor_execute", capture)
    with pytest.raises(ValidationError):
        ProjectionQuery(year=2024, month=2, as_of_date="2024-03-01")
    with Session(db_engine) as session, pytest.raises(AnalyticsProblem, match="account_not_found"):
        AnalyticsService(session, context[1]).get_spending_summary(
            PeriodQuery(**AUGUST, account_id=data["other"])
        )


def test_decimal_aggregation_exceeds_individual_row_limit_without_float(context, db_engine):
    with Session(db_engine) as session, session.begin():
        for _ in range(2):
            session.add(
                Transaction(
                    user_id=context[1],
                    account_id=context[3],
                    transaction_date=date(2026, 8, 1),
                    description_raw="Synthetic large amount",
                    transaction_type="EXPENSE",
                    amount=Decimal("-9999999999999999.99"),
                    currency="TRY",
                )
            )
    row = currency_row(get(context, "analytics/summary"))
    assert row["gross_spending"] == row["net_spending"] == "19999999999999999.98"


def test_negative_previous_comparison_and_no_external_service_calls(
    context, db_engine, monkeypatch
):
    with Session(db_engine) as session, session.begin():
        session.add(
            Transaction(
                user_id=context[1],
                account_id=context[3],
                transaction_date=date(2026, 7, 1),
                description_raw="Synthetic refund",
                transaction_type="REFUND",
                amount=Decimal("50.00"),
                currency="TRY",
            )
        )
    with Session(db_engine) as session:
        session.connection()  # The only network dependency is the existing PostgreSQL session.

        def forbidden(*args, **kwargs):
            pytest.fail("Analytics attempted an external connection")

        monkeypatch.setattr(socket.socket, "connect", forbidden)
        service = AnalyticsService(session, context[1])
        query = PeriodQuery(**AUGUST, currency="TRY")
        service.get_spending_summary(query)
        service.get_category_breakdown(query)
        service.get_merchant_breakdown(MerchantQuery(**AUGUST, currency="TRY"))
        service.get_monthly_trend(query)
        service.project_month_spending(
            ProjectionQuery(year=2026, month=8, as_of_date="2026-08-15", currency="TRY")
        )
        service.list_transactions(ExplorerQuery(**AUGUST, currency="TRY"))
        result = service.compare_periods(
            CompareQuery(
                current_start="2026-08-01",
                current_end="2026-08-31",
                previous_start="2026-07-01",
                previous_end="2026-07-31",
            )
        )
        row = result.currencies[0]
        assert row.previous_net_spending == Decimal("-50.00")
        assert row.current_net_spending == Decimal("0.00")
        assert row.percentage_change is None and row.percentage_state == "PREVIOUS_NEGATIVE"
        assert row.direction == "INCREASE"


def test_preview_skips_and_user_correction_are_reflected_in_canonical_analytics(context, db_engine):
    preview = upload(context, synthetic_pdf(TEXT.split("\f"))).json()
    params = {"start_date": "2024-01-01", "end_date": "2024-01-31", "currency": "TRY"}
    assert currency_row(get(context, "analytics/summary", params))["net_spending"] == "0.00"
    assert confirm(context, preview["import_batch_id"]).status_code == 200
    assert currency_row(get(context, "analytics/summary", params))["net_spending"] == "1340.00"
    duplicate = upload(
        context, synthetic_pdf((TEXT + "\nSynthetic duplicate variant").split("\f"))
    ).json()
    decisions = {row["id"]: "skip" for row in duplicate["transactions"]}
    assert confirm(context, duplicate["import_batch_id"], decisions=decisions).status_code == 200
    assert currency_row(get(context, "analytics/summary", params))["gross_spending"] == "1340.00"
    with Session(db_engine) as session:
        transaction_id = session.scalar(
            select(Transaction.id)
            .where(Transaction.import_batch_id == UUID(preview["import_batch_id"]))
            .order_by(Transaction.source_row_number)
        )
        cafe_id = session.scalar(select(Category.id).where(Category.code == "CAFE"))
    response = context[0].patch(
        f"/api/v1/transactions/{transaction_id}/classification",
        headers={"X-Dev-User-ID": str(context[1])},
        json={"category_id": str(cafe_id), "persist_as_rule": True},
    )
    assert response.status_code == 200
    categories = currency_row(get(context, "analytics/categories", params))["categories"]
    assert (
        next(row for row in categories if row["category_code"] == "CAFE")["gross_spending"]
        == "1314.56"
    )


def test_category_filtered_comparison_is_provider_neutral_and_decimal_safe(
    context, data, db_engine
):
    with Session(db_engine) as session:
        result = AnalyticsService(session, context[1]).compare_periods(
            CompareQuery(
                current_start="2026-08-01",
                current_end="2026-08-31",
                previous_start="2026-07-01",
                previous_end="2026-07-31",
                category_code="CAFE",
            )
        )
    assert result.category_code == "CAFE"
    assert result.currencies[0].currency == "TRY"
    assert result.currencies[0].current_net_spending == Decimal("200.00")
    assert result.currencies[0].previous_net_spending == Decimal("0.00")
    assert result.currencies[0].percentage_state == "PREVIOUS_ZERO"
