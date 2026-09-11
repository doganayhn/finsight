"""Repeatable local V1 timing probe using ephemeral synthetic data only."""

import json
import statistics
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.modules.accounts.enums import AccountType
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.transactions.enums import CategorySource, ReviewStatus, TransactionType
from app.modules.transactions.models import Transaction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from pdf_factory import synthetic_pdf  # noqa: E402, I001


BASE_URL = "http://127.0.0.1:8000/api/v1"
ROWS = 10_000
START = date(2024, 9, 1)
END = date(2026, 9, 10)
PASSWORD = "Synthetic-evaluation-password-2026"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/tlcard_synthetic.txt"


def timed(call, samples=5):
    values = []
    response = None
    for _ in range(samples):
        started = time.perf_counter()
        response = call()
        values.append((time.perf_counter() - started) * 1000)
        response.raise_for_status()
    return {"median_ms": round(statistics.median(values), 2), "samples": samples}, response


def plan_summary(plan):
    indexes = set()

    def visit(node):
        if name := node.get("Index Name"):
            indexes.add(name)
        for child in node.get("Plans", []):
            visit(child)

    visit(plan["Plan"])
    return {
        "root_node": plan["Plan"]["Node Type"],
        "planning_ms": round(plan.get("Planning Time", 0), 3),
        "execution_ms": round(plan.get("Execution Time", 0), 3),
        "indexes": sorted(indexes),
    }


def main():
    engine = get_engine()
    email = f"phase10-evaluation-{uuid4()}@example.com"
    client = httpx.Client(base_url=BASE_URL, timeout=60)
    registered = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    registered.raise_for_status()
    user_id = registered.json()["user"]["id"]
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        accounts = []
        for display_name, currency in (
            ("Synthetic TRY evaluation", "TRY"),
            ("Synthetic USD evaluation", "USD"),
            ("Synthetic import evaluation", "TRY"),
        ):
            response = client.post(
                "/accounts",
                headers=headers,
                json={
                    "display_name": display_name,
                    "institution_code": "SYNTHETIC_EVALUATION",
                    "account_type": AccountType.DEBIT_CARD,
                    "currency": currency,
                },
            )
            response.raise_for_status()
            accounts.append(response.json()["id"])

        with Session(engine) as session, session.begin():
            categories = {
                row.code: row.id
                for row in session.scalars(
                    select(Category).where(
                        Category.code.in_(["GROCERIES", "CAFE", "FUEL", "OTHER"])
                    )
                )
            }
            codes = tuple(sorted(categories))
            merchants = tuple(f"SYNTHETIC MERCHANT {index:02d}" for index in range(20))
            rows = []
            for index in range(ROWS):
                is_usd = index % 5 == 0
                amount = -(Decimal(100 + index % 19_900) / Decimal(100))
                rows.append(
                    {
                        "id": uuid4(),
                        "user_id": user_id,
                        "account_id": accounts[1 if is_usd else 0],
                        "import_batch_id": None,
                        "transaction_date": START + timedelta(days=index % 740),
                        "posted_date": None,
                        "description_raw": f"SYNTHETIC EVALUATION ROW {index}",
                        "merchant_raw": merchants[index % len(merchants)],
                        "merchant_normalized": merchants[index % len(merchants)],
                        "amount": amount.quantize(Decimal("0.01")),
                        "currency": "USD" if is_usd else "TRY",
                        "transaction_type": TransactionType.EXPENSE,
                        "category_id": categories[codes[index % len(codes)]],
                        "balance_after": None,
                        "installment_index": None,
                        "installment_count": None,
                        "installment_plan_id": None,
                        "category_source": CategorySource.SYSTEM_RULE,
                        "review_status": ReviewStatus.AUTO_CONFIRMED,
                        "source_transaction_id": None,
                        "source_row_number": None,
                    }
                )
            session.execute(insert(Transaction), rows)

        params = {"start_date": START.isoformat(), "end_date": END.isoformat()}
        results = {}
        results["health"], _ = timed(lambda: client.get("/health"))

        def login():
            return client.post("/auth/login", json={"email": email, "password": PASSWORD})

        results["login"], login_response = timed(login, samples=3)
        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
        operations = {
            "account_list": lambda: client.get("/accounts", headers=headers),
            "transaction_list": lambda: client.get(
                "/transactions", headers=headers, params=params | {"limit": 50}
            ),
            "analytics_summary": lambda: client.get(
                "/analytics/summary", headers=headers, params=params
            ),
            "category_analytics": lambda: client.get(
                "/analytics/categories", headers=headers, params=params
            ),
            "merchant_analytics": lambda: client.get(
                "/analytics/merchants", headers=headers, params=params | {"limit": 10}
            ),
            "monthly_trend": lambda: client.get("/analytics/trend", headers=headers, params=params),
        }
        for name, operation in operations.items():
            results[name], _ = timed(operation)

        pdf = synthetic_pdf(FIXTURE.read_text(encoding="utf-8").split("\f"))
        started = time.perf_counter()
        preview = client.post(
            "/imports/preview",
            headers=headers,
            data={"account_id": accounts[2]},
            files={"file": ("synthetic.pdf", pdf, "application/pdf")},
        )
        results["import_preview"] = {
            "median_ms": round((time.perf_counter() - started) * 1000, 2),
            "samples": 1,
        }
        preview.raise_for_status()
        started = time.perf_counter()
        confirmed = client.post(
            f"/imports/{preview.json()['import_batch_id']}/confirm",
            headers=headers,
            json={"decisions": {}},
        )
        results["import_confirm"] = {
            "median_ms": round((time.perf_counter() - started) * 1000, 2),
            "samples": 1,
        }
        confirmed.raise_for_status()

        with Session(engine) as session:
            query_plans = {}
            statements = {
                "transaction_list": """
                    SELECT id FROM transactions
                    WHERE user_id = :user_id
                      AND transaction_date BETWEEN :start_date AND :end_date
                    ORDER BY transaction_date DESC, created_at DESC, id DESC
                    LIMIT 51
                """,
                "currency_totals": """
                    SELECT currency, SUM(ABS(amount))
                    FROM transactions
                    WHERE user_id = :user_id
                      AND transaction_date BETWEEN :start_date AND :end_date
                      AND transaction_type = 'EXPENSE'
                    GROUP BY currency ORDER BY currency
                """,
            }
            bindings = {"user_id": user_id, "start_date": START, "end_date": END}
            for name, statement in statements.items():
                value = session.execute(
                    text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}"), bindings
                ).scalar_one()
                query_plans[name] = plan_summary(value[0])

        print(
            json.dumps(
                {
                    "environment": "local Docker Desktop development stack",
                    "dataset": {
                        "canonical_transactions": ROWS,
                        "accounts": 3,
                        "currencies": ["TRY", "USD"],
                        "date_range": [START.isoformat(), END.isoformat()],
                    },
                    "timings": results,
                    "query_plans": query_plans,
                    "limitations": [
                        "Local single-user sequential probe; not an internet SLA or load test.",
                        "Preview and confirm are one-shot measurements because imports "
                        "are stateful.",
                    ],
                },
                indent=2,
            )
        )
    finally:
        client.close()
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.id == user_id))


if __name__ == "__main__":
    main()
