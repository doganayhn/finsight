from uuid import UUID, uuid4

import pytest
from conftest import auth_headers
from pdf_factory import synthetic_pdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_imports import TEXT, confirm, count, upload

from app.modules.accounts.models import Account
from app.modules.categories.service import ClassificationService
from app.modules.imports.models import ImportBatch
from app.modules.imports.service import ImportService
from app.modules.imports.staging import ImportTransactionCandidate
from app.modules.merchants.models import UserMerchantRule
from app.modules.merchants.normalization import merchant_rule_key
from app.modules.transactions.models import Transaction


def imported_rows(engine, batch_id):
    with Session(engine) as session:
        return session.scalars(
            select(Transaction)
            .where(Transaction.import_batch_id == UUID(batch_id))
            .order_by(Transaction.source_row_number)
        ).all()


def import_synthetic(context, text=TEXT):
    preview = upload(context, synthetic_pdf(text.split("\f")))
    assert preview.status_code == 201
    data = preview.json()
    # Explicitly resolve only current synthetic duplicates in later statements.
    decisions = {row["id"]: "skip" for row in data["transactions"] if row["duplicate_matches"]}
    response = confirm(context, data["import_batch_id"], decisions=decisions)
    assert response.status_code == 200
    return data["import_batch_id"]


def correct(context, tx_id, body, user=None):
    return context[0].patch(
        f"/api/v1/transactions/{tx_id}/classification",
        headers=auth_headers(context, user),
        json=body,
    )


def catalog(context):
    response = context[0].get("/api/v1/categories", headers=auth_headers(context))
    assert response.status_code == 200
    return {row["code"]: row for row in response.json()}


def test_read_catalog_contract_and_authenticated_context(context):
    rows = catalog(context)
    assert len(rows) == 18 and list(rows) == sorted(rows)
    assert all(set(row) == {"id", "code", "display_name", "parent_id"} for row in rows.values())
    assert all(row["parent_id"] is None for row in rows.values())
    assert len({row["id"] for row in rows.values()}) == 18
    assert context[0].get("/api/v1/categories").status_code == 401
    assert correct(context, uuid4(), {"preferred_merchant_name": "Demo"}).status_code == 404


def test_correction_rule_future_import_and_other_user_isolation(context, db_engine):
    text = TEXT.replace("FINMARKET ISTANBUL TR", "DEMO STORE ONLINE TR")
    batch = import_synthetic(context, text)
    rows = imported_rows(db_engine, batch)
    original = rows[0]
    categories = catalog(context)
    assert str(original.category_id) == categories["OTHER"]["id"]
    assert original.category_source == "UNKNOWN" and original.review_status == "NEEDS_REVIEW"
    response = correct(
        context,
        original.id,
        {
            "preferred_merchant_name": "Demo Coffee",
            "category_id": categories["CAFE"]["id"],
            "persist_as_rule": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": str(original.id),
        "merchant_normalized": "Demo Coffee",
        "category_id": categories["CAFE"]["id"],
        "category_source": "USER",
        "review_status": "USER_CONFIRMED",
    }
    corrected = imported_rows(db_engine, batch)
    assert corrected[0].description_raw == original.description_raw
    assert corrected[0].merchant_raw == original.merchant_raw
    assert corrected[0].amount == original.amount
    assert corrected[0].transaction_type == original.transaction_type
    assert corrected[1].updated_at == rows[1].updated_at
    with Session(db_engine) as session:
        rule = session.scalar(
            select(UserMerchantRule).where(UserMerchantRule.user_id == context[1])
        )
        assert rule.merchant_key == merchant_rule_key(
            original.description_raw, original.merchant_raw
        )
        assert rule.preferred_merchant_name == "Demo Coffee"
        assert str(rule.category_id) == categories["CAFE"]["id"]
    # A later statement date changes transaction identity, not merchant identity.
    later = import_synthetic(context, text.replace("2 Ocak 2024", "3 Ocak 2024"))
    future = imported_rows(db_engine, later)
    assert len(future) == 1
    assert future[0].merchant_normalized == "Demo Coffee"
    assert str(future[0].category_id) == categories["CAFE"]["id"]
    assert future[0].category_source == "USER" and future[0].review_status == "AUTO_CONFIRMED"
    other_account = uuid4()
    with Session(db_engine) as session, session.begin():
        session.add(
            Account(
                id=other_account,
                user_id=context[2],
                display_name="Synthetic other",
                account_type="DEBIT_CARD",
                currency="TRY",
            )
        )
    other_context = (context[0], context[2], context[1], other_account, context[4])
    other_batch = import_synthetic(other_context, text)
    other = imported_rows(db_engine, other_batch)[0]
    assert other.merchant_normalized is None and other.category_source == "UNKNOWN"
    assert str(other.category_id) == categories["OTHER"]["id"]
    # Partial upsert preserves the earlier preferred merchant. No historical bulk rewrite.
    update = correct(
        context, original.id, {"category_id": categories["SHOPPING"]["id"], "persist_as_rule": True}
    )
    assert update.status_code == 200
    with Session(db_engine) as session:
        rules = session.scalars(
            select(UserMerchantRule).where(UserMerchantRule.user_id == context[1])
        ).all()
        assert len(rules) == 1 and rules[0].preferred_merchant_name == "Demo Coffee"
        assert str(rules[0].category_id) == categories["SHOPPING"]["id"]
    assert imported_rows(db_engine, later)[0].category_id == future[0].category_id


def test_direct_correction_is_selected_only_without_implicit_rule(context, db_engine):
    batch = import_synthetic(context)
    original = imported_rows(db_engine, batch)[0]
    response = correct(context, original.id, {"preferred_merchant_name": "Demo Preferred"})
    assert response.status_code == 200
    assert response.json()["category_source"] == original.category_source
    assert response.json()["review_status"] == "USER_CONFIRMED"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(UserMerchantRule)) == 0
    assert imported_rows(db_engine, batch)[0].description_raw == original.description_raw


def test_correction_ownership_and_invalid_requests_leave_data_unchanged(context, db_engine):
    batch = import_synthetic(context)
    original = imported_rows(db_engine, batch)[0]
    valid = {"preferred_merchant_name": "Demo"}
    response = correct(context, original.id, valid, user=context[2])
    missing = correct(context, uuid4(), valid)
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json() == {"detail": {"code": "transaction_not_found"}}
    for invalid in (
        {},
        {"persist_as_rule": True},
        {"preferred_merchant_name": "  "},
        {"preferred_merchant_name": None},
        {"category_id": None},
        {"category_id": str(uuid4())},
        {"description_raw": "overwrite"},
        {"preferred_merchant_name": "x" * 256},
    ):
        assert correct(context, original.id, invalid).status_code == 422
    after = imported_rows(db_engine, batch)[0]
    assert (
        after.updated_at == original.updated_at
        and after.description_raw == original.description_raw
    )


@pytest.mark.parametrize("kind", ["TRANSFER", "CARD_PAYMENT", "INCOME", "FEE"])
def test_corrections_cannot_install_spending_rules_for_semantic_types(context, db_engine, kind):
    batch = import_synthetic(context)
    tx = imported_rows(db_engine, batch)[0]
    with Session(db_engine) as session, session.begin():
        session.get(Transaction, tx.id).transaction_type = kind
    response = correct(context, tx.id, {"category_id": catalog(context)["CAFE"]["id"]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "classification_incompatible_with_type"


def test_import_confirmation_normalizes_and_categorizes_before_commit(context, db_engine):
    text = TEXT.replace("FINMARKET ISTANBUL TR", "TRENDYOL YEMEK ISTANBUL TR")
    batch = import_synthetic(context, text)
    row = imported_rows(db_engine, batch)[0]
    assert row.merchant_normalized == "Trendyol Yemek"
    assert row.description_raw == "TRENDYOL YEMEK ISTANBUL TR"
    assert row.category_source == "MERCHANT_RULE" and row.review_status == "AUTO_CONFIRMED"
    assert str(row.category_id) == catalog(context)["FOOD_DELIVERY"]["id"]


def test_enrichment_failure_rolls_back_rows_status_and_staging(context, db_engine, monkeypatch):
    preview = upload(context, synthetic_pdf(TEXT.split("\f"))).json()
    batch_id = preview["import_batch_id"]
    original = ClassificationService.classify
    calls = 0
    with Session(db_engine) as session:

        def fail_second(self, *args):
            nonlocal calls
            calls += 1
            if calls == 2:
                # Prove rollback even after the first enriched row reached PostgreSQL.
                session.flush()
                raise RuntimeError("synthetic enrichment failure")
            return original(self, *args)

        monkeypatch.setattr(ClassificationService, "classify", fail_second)
        with pytest.raises(RuntimeError, match="synthetic enrichment failure"):
            ImportService(session, context[4]).confirm(context[1], UUID(batch_id), {})
    assert calls == 2
    assert count(db_engine, Transaction, batch_id) == 0
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 3
    with Session(db_engine) as session:
        assert session.get(ImportBatch, UUID(batch_id)).import_status == "AWAITING_CONFIRMATION"
    monkeypatch.setattr(ClassificationService, "classify", original)
    assert confirm(context, batch_id).status_code == 200
    assert count(db_engine, Transaction, batch_id) == 3
