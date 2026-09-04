import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pdf_factory import synthetic_pdf
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.modules.accounts.models import Account
from app.modules.auth.models import User
from app.modules.imports.errors import ImportProblem
from app.modules.imports.models import ImportBatch
from app.modules.imports.parsers.registry import ParserRegistry
from app.modules.imports.parsers.yapikredi_tlcard import YapiKrediTLCardPDFParser
from app.modules.imports.schemas import ExtractedDocument, ExtractedPage
from app.modules.imports.service import ImportService
from app.modules.imports.staging import ImportTransactionCandidate
from app.modules.transactions.models import Transaction

TEXT = (Path(__file__).parent / "fixtures" / "tlcard_synthetic.txt").read_text(encoding="utf-8")


@pytest.fixture
def pdf():
    return synthetic_pdf(TEXT.split("\f"))


@pytest.fixture
def context(db_engine):
    user_id, other_id, account_id = uuid4(), uuid4(), uuid4()
    with Session(db_engine) as session, session.begin():
        session.add_all(
            [User(id=uid, email=f"synthetic-{uid}@example.invalid") for uid in [user_id, other_id]]
        )
        session.flush()
        session.add(
            Account(
                id=account_id,
                user_id=user_id,
                display_name="Synthetic test account",
                account_type="DEBIT_CARD",
                currency="TRY",
            )
        )
    settings = get_settings().model_copy(update={"app_env": "development"})
    app = create_app(settings)

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            yield client, user_id, other_id, account_id, settings
    finally:
        with db_engine.begin() as connection:
            connection.execute(delete(User).where(User.id.in_([user_id, other_id])))


def upload(context, data, *, name="synthetic.pdf", mime="application/pdf", user=None):
    client, user_id, _, account_id, _ = context
    return client.post(
        "/api/v1/imports/preview",
        headers={"X-Dev-User-ID": str(user or user_id)},
        data={"account_id": str(account_id)},
        files={"file": (name, data, mime)},
    )


def confirm(context, batch_id, *, decisions=None, user=None):
    client, user_id, *_ = context
    return client.post(
        f"/api/v1/imports/{batch_id}/confirm",
        headers={"X-Dev-User-ID": str(user or user_id)},
        json={"decisions": decisions or {}},
    )


def read(context, batch_id, *, user=None):
    client, user_id, *_ = context
    return client.get(
        f"/api/v1/imports/{batch_id}", headers={"X-Dev-User-ID": str(user or user_id)}
    )


def count(engine, model, batch_id):
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(model).where(model.import_batch_id == UUID(batch_id))
        )


def test_registry_exactly_one_match():
    doc = ExtractedDocument((ExtractedPage(1, TEXT),))
    assert isinstance(ParserRegistry().resolve(doc), YapiKrediTLCardPDFParser)
    with pytest.raises(ImportProblem, match="unsupported_statement"):
        ParserRegistry().resolve(ExtractedDocument((ExtractedPage(1, "unrelated synthetic"),)))
    with pytest.raises(ImportProblem, match="ambiguous_statement_parser"):
        ParserRegistry((YapiKrediTLCardPDFParser(), YapiKrediTLCardPDFParser())).resolve(doc)
    with pytest.raises(ImportProblem, match="unsupported_statement"):
        ParserRegistry(()).resolve(doc)


def test_synthetic_end_to_end_and_file_idempotency(context, db_engine, pdf):
    preview = upload(context, pdf, name="PRIVATE_FILENAME_SENTINEL.pdf")
    assert preview.status_code == 201
    data = preview.json()
    batch_id = data["import_batch_id"]
    assert data["status"] == "AWAITING_CONFIRMATION"
    assert data["reported_total"] == data["parsed_total"] == "1340.00"
    assert data["statement_period"] == "2024-01"
    assert data["parser"] == {"name": "yapikredi_tlcard_pdf", "version": "1.0.0"}
    assert data["counts"] == dict(
        total_rows=3,
        valid_rows=3,
        failed_rows=0,
        duplicate_rows=0,
        imported_rows=0,
        skipped_duplicate_rows=0,
    )
    assert count(db_engine, Transaction, batch_id) == 0
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 3
    with Session(db_engine) as session:
        batch = session.get(ImportBatch, UUID(batch_id))
        assert batch.file_hash == hashlib.sha256(pdf).hexdigest()
        assert batch.source_type == "MANUAL_UPLOAD" and batch.file_format == "PDF"
        assert batch.original_filename == "statement.pdf"
        assert batch.statement_period_start is None and batch.statement_period_end is None
    assert read(context, batch_id).json() == data
    pending = upload(context, pdf)
    assert pending.status_code == 409 and pending.json()["detail"]["import_batch_id"] == batch_id
    done = confirm(context, batch_id)
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"
    assert done.json()["counts"]["imported_rows"] == 3
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 0
    with Session(db_engine) as session:
        rows = session.scalars(
            select(Transaction)
            .where(Transaction.import_batch_id == UUID(batch_id))
            .order_by(Transaction.source_row_number)
        ).all()
        for row, candidate in zip(rows, data["transactions"], strict=True):
            assert str(row.amount) == candidate["amount"]
            assert row.transaction_date.isoformat() == candidate["transaction_date"]
            assert row.description_raw == candidate["description_raw"]
            assert row.merchant_raw == candidate["merchant_raw"]
            assert row.user_id == context[1] and row.account_id == context[3]
            assert row.category_id is None and row.merchant_normalized is None
            assert row.category_source == "UNKNOWN" and row.review_status == "NEEDS_REVIEW"
            assert row.amount < 0 and row.currency == "TRY"
    assert confirm(context, batch_id).json() == done.json()
    assert read(context, batch_id).json() == done.json()
    assert count(db_engine, Transaction, batch_id) == 3
    assert upload(context, pdf).status_code == 409


@pytest.mark.parametrize(
    "data,name,mime,status,code",
    [
        (b"", "synthetic.pdf", "application/pdf", 422, "empty_file"),
        (b"private-text-sentinel", "synthetic.pdf", "application/pdf", 415, "invalid_pdf_header"),
        (b"%PDF-broken", "synthetic.txt", "application/pdf", 415, "pdf_required"),
        (b"%PDF-broken", "synthetic.pdf", "text/plain", 415, "pdf_required"),
        (b"%PDF-broken", "synthetic.pdf", "application/pdf", 422, "invalid_statement"),
    ],
)
def test_upload_rejections_are_safe(context, data, name, mime, status, code, caplog):
    response = upload(context, data, name=name, mime=mime)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "private-text-sentinel" not in response.text + caplog.text


def test_file_and_streamed_request_limits(context, pdf):
    context[4].max_upload_bytes = len(pdf) - 1
    assert upload(context, pdf).status_code == 413
    # Chunked/missing Content-Length is still bounded before multipart processing.
    response = context[0].post(
        "/api/v1/imports/preview",
        content=iter([b"X" * 65536] * 200),
        headers={"Content-Type": "multipart/form-data; boundary=synthetic"},
    )
    assert response.status_code == 413


def test_page_limit_and_unsupported_pdf(context):
    context[4].max_pdf_pages = 1
    response = upload(context, synthetic_pdf(["synthetic", "second"]))
    assert response.status_code == 422
    unsupported = upload(context, synthetic_pdf(["synthetic unrelated document"]))
    assert unsupported.status_code == 415
    assert (
        read(context, unsupported.json()["detail"]["import_batch_id"]).json()["status"] == "FAILED"
    )


def test_ownership_and_explicit_preauth_context(context, pdf):
    assert upload(context, pdf, user=context[2]).status_code == 404
    batch_id = upload(context, pdf).json()["import_batch_id"]
    assert read(context, batch_id, user=context[2]).status_code == 404
    assert confirm(context, batch_id, user=context[2]).status_code == 404
    assert read(context, uuid4()).status_code == 404
    assert context[0].get(f"/api/v1/imports/{batch_id}").status_code == 422
    invalid = context[0].get(
        f"/api/v1/imports/{batch_id}", headers={"X-Dev-User-ID": "PRIVATE_HEADER_SENTINEL"}
    )
    assert invalid.status_code == 422 and "PRIVATE_HEADER_SENTINEL" not in invalid.text
    context[4].app_env = "production"
    assert read(context, batch_id).status_code == 403


def test_failed_validation_has_no_candidates_and_retry_is_allowed(context, db_engine):
    pdf = synthetic_pdf(TEXT.replace("Tutarı : 1.340,00", "Tutarı : 1.341,00").split("\f"))
    response = upload(context, pdf)
    assert response.status_code == 422
    batch_id = response.json()["detail"]["import_batch_id"]
    status = read(context, batch_id).json()
    assert status["status"] == "FAILED" and status["validation_status"] == "FAILED"
    assert status["counts"] == dict(
        total_rows=3,
        valid_rows=0,
        failed_rows=3,
        duplicate_rows=0,
        imported_rows=0,
        skipped_duplicate_rows=0,
    )
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 0
    assert count(db_engine, Transaction, batch_id) == 0
    assert confirm(context, batch_id).status_code == 409
    retry = upload(context, pdf)
    assert retry.status_code == 422
    assert retry.json()["detail"]["import_batch_id"] != batch_id


def test_currency_mismatch_cannot_be_confirmed(context, db_engine, pdf):
    with db_engine.begin() as connection:
        connection.execute(
            Account.__table__.update().where(Account.id == context[3]).values(currency="USD")
        )
    response = upload(context, pdf)
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "account_currency_mismatch"
    )
    assert confirm(context, response.json()["detail"]["import_batch_id"]).status_code == 409


def test_heuristic_recheck_and_explicit_decisions(context, db_engine, pdf):
    first = upload(context, pdf).json()["import_batch_id"]
    # Different exact bytes, same financial rows. Both previews predate confirmation.
    second = upload(context, pdf + b"\n%synthetic alternate file\n").json()
    assert second["counts"]["duplicate_rows"] == 0
    assert confirm(context, first).status_code == 200
    batch_id = second["import_batch_id"]
    blocked = confirm(context, batch_id)
    assert (
        blocked.status_code == 409
        and blocked.json()["detail"]["code"] == "duplicate_resolution_required"
    )
    assert count(db_engine, Transaction, batch_id) == 0
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 3
    fresh = read(context, batch_id).json()
    assert fresh["counts"]["duplicate_rows"] == 3
    assert all(row["duplicate_matches"][0]["kind"] == "heuristic" for row in fresh["transactions"])
    assert confirm(context, batch_id, decisions={str(uuid4()): "skip"}).status_code == 422
    decisions = {row["id"]: "skip" for row in fresh["transactions"]}
    decisions[fresh["transactions"][0]["id"]] = "import"
    done = confirm(context, batch_id, decisions=decisions)
    assert done.status_code == 200
    assert done.json()["counts"] == dict(
        total_rows=3,
        valid_rows=3,
        failed_rows=0,
        duplicate_rows=3,
        imported_rows=1,
        skipped_duplicate_rows=2,
    )
    assert count(db_engine, Transaction, batch_id) == 1
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 0
    third = upload(context, pdf + b"\n%third\n").json()
    assert third["counts"]["duplicate_rows"] == 3


def test_duplicate_comparison_does_not_rewrite_merchants(context, db_engine, pdf):
    first = upload(context, pdf).json()["import_batch_id"]
    confirm(context, first)
    with db_engine.begin() as connection:
        connection.execute(
            Transaction.__table__.update()
            .where(Transaction.import_batch_id == UUID(first))
            .values(description_raw="  finmarket   istanbul tr  ")
        )
    other = upload(context, pdf + b"\n%comparison\n").json()
    assert other["transactions"][0]["duplicate_matches"][0]["kind"] == "heuristic"
    assert other["transactions"][0]["merchant_raw"] == "FINMARKET ISTANBUL TR"


def test_source_id_matching_and_persistence(context, db_engine, pdf):
    class SourceIDParser(YapiKrediTLCardPDFParser):
        def parse(self, document):
            statement = super().parse(document)
            return replace(
                statement,
                transactions=tuple(
                    replace(row, source_transaction_id=f"synthetic-source-{i}")
                    for i, row in enumerate(statement.transactions)
                ),
            )

    def service(session):
        return ImportService(session, context[4], ParserRegistry((SourceIDParser(),)))

    with Session(db_engine) as session:
        first = service(session).preview(
            context[1], context[3], pdf, "synthetic.pdf", "application/pdf"
        )
        service(session).confirm(context[1], first.import_batch_id, {})
    with db_engine.begin() as connection:
        connection.execute(
            Transaction.__table__.update()
            .where(Transaction.import_batch_id == first.import_batch_id)
            .values(description_raw="SYNTHETIC CHANGED DESCRIPTION")
        )
    with Session(db_engine) as session:
        second = service(session).preview(
            context[1], context[3], pdf + b"\n%source-id\n", "synthetic.pdf", "application/pdf"
        )
        assert all(row.duplicate_matches[0].kind == "source_id" for row in second.transactions)
        with pytest.raises(ImportProblem, match="duplicate_resolution_required"):
            service(session).confirm(context[1], second.import_batch_id, {})


def test_identical_rows_within_one_preview_require_decisions(context, pdf):
    text = TEXT.replace(
        "7 Ocak 2024 DEMO CAFE  İSTANBUL TR 80,00", "2 Ocak 2024 FINMARKET ISTANBUL TR 1.234,56"
    )
    text = text.replace("1.340,00", "2.494,56")
    response = upload(context, synthetic_pdf(text.split("\f")))
    assert response.status_code == 201
    data = response.json()
    assert data["counts"]["duplicate_rows"] == 2
    assert confirm(context, data["import_batch_id"]).status_code == 409
    decisions = {row["id"]: "import" for row in data["transactions"] if row["duplicate_matches"]}
    assert (
        confirm(context, data["import_batch_id"], decisions=decisions).json()["counts"][
            "imported_rows"
        ]
        == 3
    )


def test_confirmation_failure_rolls_back_rows_status_and_cleanup(context, db_engine, pdf, caplog):
    batch_id = upload(context, pdf).json()["import_batch_id"]

    def fail_cleanup(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM import_transaction_candidates"):
            raise SQLAlchemyError("PRIVATE_SQL_PARAMETER_SENTINEL")

    event.listen(db_engine, "before_cursor_execute", fail_cleanup)
    try:
        response = confirm(context, batch_id)
    finally:
        event.remove(db_engine, "before_cursor_execute", fail_cleanup)
    assert (
        response.status_code == 500
        and "PRIVATE_SQL_PARAMETER_SENTINEL" not in response.text + caplog.text
    )
    assert count(db_engine, Transaction, batch_id) == 0
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 3
    assert read(context, batch_id).json()["status"] == "AWAITING_CONFIRMATION"
    assert confirm(context, batch_id).status_code == 200


@pytest.mark.parametrize("same_batch", [True, False])
def test_concurrent_confirmations_serialize_and_recheck(context, db_engine, pdf, same_batch):
    first = UUID(upload(context, pdf).json()["import_batch_id"])
    second = (
        first if same_batch else UUID(upload(context, pdf + b"\n%race\n").json()["import_batch_id"])
    )
    barrier = Barrier(2, timeout=10)
    locks = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            locks.append(statement)

    def run(batch_id):
        with Session(db_engine) as session:
            barrier.wait()
            try:
                return ImportService(session, context[4]).confirm(context[1], batch_id, {}).status
            except ImportProblem as error:
                return error.code

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [first, second]))
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
    assert results.count("COMPLETED") == (2 if same_batch else 1)
    if not same_batch:
        assert "duplicate_resolution_required" in results
    assert any("FROM accounts" in query for query in locks)
    assert any("FROM import_batches" in query for query in locks)
    with Session(db_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.user_id == context[1])
            )
            == 3
        )


def test_concurrent_previews_do_not_create_two_pending_batches(context, db_engine, pdf):
    barrier = Barrier(2, timeout=10)

    def run(_):
        with Session(db_engine) as session:
            barrier.wait()
            try:
                return (
                    ImportService(session, context[4])
                    .preview(context[1], context[3], pdf, "synthetic.pdf", "application/pdf")
                    .status
                )
            except ImportProblem as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert sorted(results) == ["AWAITING_CONFIRMATION", "file_already_imported_or_pending"]


def test_same_file_can_succeed_after_failed_processing(context, db_engine, pdf):
    with Session(db_engine) as session:
        unavailable = ImportService(session, context[4], ParserRegistry(()))
        with pytest.raises(ImportProblem, match="unsupported_statement"):
            unavailable.preview(context[1], context[3], pdf, "synthetic.pdf", "application/pdf")
    response = upload(context, pdf)
    assert response.status_code == 201
    assert confirm(context, response.json()["import_batch_id"]).status_code == 200


@pytest.mark.parametrize("valid", [True, False])
def test_upload_spool_is_closed_and_no_raw_document_is_stored(
    context, db_engine, pdf, monkeypatch, caplog, valid
):
    from starlette.datastructures import UploadFile

    closed = []
    original_close = UploadFile.close

    async def close(upload):
        await original_close(upload)
        closed.append(upload.file.closed)

    monkeypatch.setattr(UploadFile, "close", close)
    response = upload(context, pdf if valid else b"%PDF-PRIVATE_RAW_SENTINEL")
    assert response.status_code == (201 if valid else 422)
    assert closed and all(closed)
    assert "PRIVATE_RAW_SENTINEL" not in response.text + caplog.text
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in response.text + caplog.text
    with db_engine.connect() as connection:
        # Inspect every row created for this user, including all staging fields.
        for table in ["import_batches", "import_transaction_candidates"]:
            from sqlalchemy import text

            predicate = (
                "user_id = :uid"
                if table == "import_batches"
                else "import_batch_id IN (SELECT id FROM import_batches WHERE user_id = :uid)"
            )
            values = connection.scalars(
                text(f"SELECT row_to_json(t)::text FROM {table} t WHERE {predicate}"),
                {"uid": context[1]},
            ).all()
            assert all(
                "SYNTHETIC_PRIVATE_SENTINEL" not in value and "%PDF-" not in value
                for value in values
            )


def test_other_account_transactions_are_not_duplicate_matches(context, db_engine, pdf):
    first = upload(context, pdf).json()["import_batch_id"]
    confirm(context, first)
    with Session(db_engine) as session, session.begin():
        other_account = Account(
            user_id=context[1],
            display_name="Second synthetic account",
            account_type="DEBIT_CARD",
            currency="TRY",
        )
        session.add(other_account)
        session.flush()
        account_id = other_account.id
    with Session(db_engine) as session:
        preview = ImportService(session, context[4]).preview(
            context[1], account_id, pdf, "synthetic.pdf", "application/pdf"
        )
        assert preview.counts.duplicate_rows == 0
        assert all(not row.duplicate_matches for row in preview.transactions)


def test_confirm_rechecks_account_currency(context, db_engine, pdf):
    batch_id = upload(context, pdf).json()["import_batch_id"]
    with db_engine.begin() as connection:
        connection.execute(
            Account.__table__.update().where(Account.id == context[3]).values(currency="USD")
        )
    assert confirm(context, batch_id).status_code == 409
    assert count(db_engine, Transaction, batch_id) == 0


def assert_confirmation_unchanged(context, db_engine, batch_id):
    assert read(context, batch_id).json()["status"] == "AWAITING_CONFIRMATION"
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 3
    assert count(db_engine, Transaction, batch_id) == 0


@pytest.mark.parametrize("decision", ["skip", "import"])
def test_non_duplicate_decisions_rejected_without_partial_confirmation(
    context, db_engine, pdf, decision
):
    preview = upload(context, pdf).json()
    batch_id = preview["import_batch_id"]
    row = preview["transactions"][0]
    assert not row["duplicate_matches"]
    response = confirm(context, batch_id, decisions={row["id"]: decision})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "decision_for_non_duplicate_candidate"
    assert row["description_raw"] not in response.text
    assert_confirmation_unchanged(context, db_engine, batch_id)
    done = confirm(context, batch_id)
    assert done.status_code == 200
    assert done.json()["counts"]["imported_rows"] == 3
    assert done.json()["counts"]["skipped_duplicate_rows"] == 0
    assert confirm(context, batch_id).json() == done.json()


@pytest.mark.parametrize("decision", ["skip", "import"])
def test_mixed_batch_imports_normal_rows_and_resolves_only_duplicates(
    context, db_engine, pdf, decision
):
    first = upload(context, pdf).json()["import_batch_id"]
    assert confirm(context, first).status_code == 200
    # Only the first row still matches; the other synthetic dates are different.
    text = TEXT.replace("7 Ocak 2024", "17 Ocak 2024").replace("9 Ocak 2024", "19 Ocak 2024")
    preview = upload(context, synthetic_pdf(text.split("\f"))).json()
    batch_id = preview["import_batch_id"]
    duplicate, *normal = preview["transactions"]
    assert duplicate["duplicate_matches"]
    assert all(not row["duplicate_matches"] for row in normal)
    assert confirm(context, batch_id).status_code == 409
    assert_confirmation_unchanged(context, db_engine, batch_id)
    # Even a valid duplicate resolution must not allow omitting another ordinary row.
    invalid = confirm(
        context, batch_id, decisions={duplicate["id"]: decision, normal[0]["id"]: "skip"}
    )
    assert invalid.status_code == 422
    assert_confirmation_unchanged(context, db_engine, batch_id)
    done = confirm(context, batch_id, decisions={duplicate["id"]: decision})
    assert done.status_code == 200
    skipped = int(decision == "skip")
    assert done.json()["counts"] == dict(
        total_rows=3,
        valid_rows=3,
        failed_rows=0,
        duplicate_rows=1,
        imported_rows=3 - skipped,
        skipped_duplicate_rows=skipped,
    )
    assert done.json()["reported_total"] == done.json()["parsed_total"] == "1340.00"
    with Session(db_engine) as session:
        rows = session.scalars(
            select(Transaction).where(Transaction.import_batch_id == UUID(batch_id))
        ).all()
        assert {row.source_row_number for row in rows} == ({2, 3} if skipped else {1, 2, 3})
    assert count(db_engine, ImportTransactionCandidate, batch_id) == 0
    assert confirm(context, batch_id).json() == done.json()


@pytest.mark.parametrize("decision", ["skip", "import"])
def test_disappeared_duplicate_flags_invalidate_stale_decisions(context, db_engine, pdf, decision):
    first = upload(context, pdf).json()["import_batch_id"]
    assert confirm(context, first).status_code == 200
    preview = upload(context, pdf + b"\n%synthetic stale flags\n").json()
    batch_id = preview["import_batch_id"]
    assert preview["counts"]["duplicate_rows"] == 3
    decisions = {row["id"]: decision for row in preview["transactions"]}
    # Simulate a relevant state change using synthetic database records, not an editor API.
    with db_engine.begin() as connection:
        connection.execute(delete(Transaction).where(Transaction.import_batch_id == UUID(first)))
    response = confirm(context, batch_id, decisions=decisions)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "decision_for_non_duplicate_candidate"
    assert_confirmation_unchanged(context, db_engine, batch_id)
    done = confirm(context, batch_id)
    assert done.status_code == 200
    assert done.json()["counts"]["duplicate_rows"] == 0
    assert done.json()["counts"]["imported_rows"] == 3
    assert done.json()["counts"]["skipped_duplicate_rows"] == 0
