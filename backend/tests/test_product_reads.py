from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.modules.accounts.models import Account
from app.modules.imports.models import ImportBatch


def read(context, path, params=None):
    return context[0].get(
        "/api/v1/" + path, params=params, headers={"X-Dev-User-ID": str(context[1])}
    )


def test_account_list_owner_scope_pagination_and_safe_contract(context, db_engine):
    with Session(db_engine) as session, session.begin():
        for owner in [context[1], context[2]]:
            session.add(
                Account(
                    user_id=owner,
                    display_name="Synthetic account",
                    account_type="CASH",
                    currency="USD",
                    account_number_masked="****1234",
                )
            )
    first = read(context, "accounts", {"limit": 1}).json()
    second = read(context, "accounts", {"limit": 1, "offset": 1}).json()
    assert first["has_more"] and not second["has_more"]
    assert first["accounts"][0]["id"] != second["accounts"][0]["id"]
    assert set(first["accounts"][0]) == {
        "id",
        "display_name",
        "institution_code",
        "account_type",
        "currency",
        "is_active",
    }
    assert len(read(context, "accounts").json()["accounts"]) == 2


def test_import_history_scope_order_pagination_safe_metadata(context, db_engine):
    with Session(db_engine) as session, session.begin():
        other_account = Account(
            user_id=context[2], display_name="Synthetic other", account_type="CASH", currency="TRY"
        )
        session.add(other_account)
        session.flush()
        for owner, account in [
            (context[1], context[3]),
            (context[1], context[3]),
            (context[2], other_account.id),
        ]:
            session.add(
                ImportBatch(
                    user_id=owner,
                    account_id=account,
                    source_type="MANUAL_UPLOAD",
                    file_format="PDF",
                    original_filename="PRIVATE_SENTINEL.pdf",
                    file_hash="a" * 64,
                    currency="TRY",
                    reported_total=Decimal("15.25"),
                    parsed_total=Decimal("15.25"),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
        foreign_id = other_account.id
    first = read(context, "imports", {"limit": 1})
    second = read(context, "imports", {"limit": 1, "offset": 1})
    assert first.status_code == second.status_code == 200
    a, b = first.json(), second.json()
    assert a["has_more"] and not b["has_more"]
    assert a["imports"][0]["id"] > b["imports"][0]["id"]
    assert a["imports"][0]["reported_total"] == "15.25"
    assert (
        not {"user_id", "original_filename", "file_hash", "parser_name", "transactions"}
        & a["imports"][0].keys()
    )
    assert "PRIVATE_SENTINEL" not in first.text
    assert len(read(context, "imports", {"account_id": str(context[3])}).json()["imports"]) == 2
    foreign = read(context, "imports", {"account_id": str(foreign_id)})
    missing = read(context, "imports", {"account_id": str(uuid4())})
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


@pytest.mark.parametrize("path", ["accounts", "imports"])
@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 100001}, {"unexpected": "x"}],
)
def test_read_bounds(context, path, params):
    assert read(context, path, params).status_code == 422


@pytest.mark.parametrize("path", ["accounts", "imports"])
def test_read_development_context_and_empty(context, path):
    assert context[0].get("/api/v1/" + path).status_code == 422
    assert read(context, path, {"offset": 1000}).json()[path] == []
    context[4].app_env = "production"
    assert read(context, path).status_code == 403
