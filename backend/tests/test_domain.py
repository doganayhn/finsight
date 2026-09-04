from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import (
    Account,
    Category,
    ImportBatch,
    MerchantAlias,
    Transaction,
    TransactionLink,
    User,
    UserMerchantRule,
)
from app.modules.accounts.enums import AccountType
from app.modules.imports.enums import FileFormat, ImportStatus, SourceType, ValidationStatus
from app.modules.transactions.enums import CategorySource, LinkType, ReviewStatus, TransactionType


@pytest.fixture
def account(db):
    user = User(email=f"synthetic-{uuid4().hex}@example.invalid")
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id,
        institution_code="SYNTHETIC_PROVIDER",
        display_name="Test card",
        account_type=AccountType.DEBIT_CARD,
        currency="TRY",
        account_number_masked="****1234",
    )
    db.add(account)
    db.flush()
    return account


def transaction(account, **overrides):
    values = dict(
        user_id=account.user_id,
        account_id=account.id,
        transaction_date=date(2026, 9, 3),
        description_raw="Synthetic row",
        amount=Decimal("-1250.00"),
        currency="TRY",
    )
    values.update(overrides)
    return Transaction(**values)


def batch(account, **overrides):
    values = dict(
        user_id=account.user_id,
        account_id=account.id,
        source_type=SourceType.MANUAL_UPLOAD,
        file_format=FileFormat.PDF,
    )
    values.update(overrides)
    return ImportBatch(**values)


def assert_rejected(db, obj, constraint):
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.add(obj)
        db.flush()
    assert error.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize(
    ("amount", "currency", "kind"),
    [
        (Decimal("-1250.00"), "TRY", TransactionType.EXPENSE),
        (Decimal("50000.00"), "USD", TransactionType.INCOME),
        (Decimal("1250.00"), "EUR", TransactionType.REFUND),
        (Decimal("-5000.00"), "TRY", TransactionType.TRANSFER),
        (Decimal("5000.00"), "TRY", TransactionType.TRANSFER),
    ],
)
def test_exact_signed_money_currency_nullable_category(db, account, amount, currency, kind):
    row = transaction(account, amount=amount, currency=currency, transaction_type=kind)
    db.add(row)
    db.flush()
    db.refresh(row)
    assert isinstance(row.amount, Decimal) and row.amount == amount
    assert row.currency == currency and row.transaction_type == kind
    assert row.category_id is None and row.category is None
    assert row.merchant_normalized is None and row.import_batch is None
    assert row.category_source == CategorySource.UNKNOWN
    assert row.review_status == ReviewStatus.NEEDS_REVIEW
    assert type(row.transaction_date) is date
    assert isinstance(row.id, UUID) and isinstance(account.id, UUID)
    assert row.account.user.id == row.user_id == account.user_id
    assert row.created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "bad_amount",
    [
        12.50,
        "12.50",
        Decimal("1.001"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("10000000000000000"),
    ],
)
def test_money_rejects_inexact_nonfinite_and_overflow_inputs(db, account, bad_amount):
    with pytest.raises(StatementError), db.begin_nested():
        db.add(transaction(account, amount=bad_amount))
        db.flush()


def test_numeric_shape_and_nan_check_in_postgres(db, account):
    columns = {c["name"]: c for c in inspect(db.bind).get_columns("transactions")}
    assert (columns["amount"]["type"].precision, columns["amount"]["type"].scale) == (18, 2)
    row = transaction(account)
    db.add(row)
    db.flush()
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.execute(
            text("UPDATE transactions SET amount = 'NaN'::numeric WHERE id = :id"), {"id": row.id}
        )
    assert error.value.orig.diag.constraint_name == "ck_transactions_amount_finite"


def test_installment_preserves_monthly_amount_and_group(db, account):
    plan = uuid4()
    row = transaction(
        account,
        amount=Decimal("-5000.00"),
        installment_index=1,
        installment_count=6,
        installment_plan_id=plan,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    assert (row.installment_index, row.installment_count, row.installment_plan_id) == (1, 6, plan)
    assert row.amount == Decimal("-5000.00")


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"installment_index": 7, "installment_count": 6}, "ck_transactions_installment_order"),
        ({"installment_index": 0}, "ck_transactions_installment_index_positive"),
        ({"installment_count": 0}, "ck_transactions_installment_count_positive"),
        ({"source_row_number": 0}, "ck_transactions_source_row_positive"),
        ({"currency": "try"}, "ck_transactions_currency_format"),
    ],
)
def test_transaction_checks(db, account, fields, constraint):
    assert_rejected(db, transaction(account, **fields), constraint)


def test_import_provenance_defaults_counters_and_duplicate_candidates(db, account):
    pending = batch(account)
    db.add(pending)
    db.flush()
    assert pending.import_status == ImportStatus.PENDING
    assert pending.validation_status == ValidationStatus.NOT_AVAILABLE
    assert (
        pending.total_rows
        == pending.valid_rows
        == pending.duplicate_rows
        == pending.failed_rows
        == 0
    )
    assert pending.parser_name is None
    parsed = batch(
        account,
        file_hash="a" * 64,
        parser_name="synthetic_parser",
        parser_version="1.0",
        statement_period_start=date(2026, 8, 12),
        statement_period_end=date(2026, 9, 11),
        currency="TRY",
        reported_total=Decimal("2500.00"),
        parsed_total=Decimal("2500.00"),
        total_rows=2,
        valid_rows=2,
        import_status=ImportStatus.PARSED,
        validation_status=ValidationStatus.PASSED,
    )
    repeated_attempt = batch(account, file_hash="a" * 64)
    db.add_all([parsed, repeated_attempt])
    db.flush()
    rows = [
        transaction(
            account,
            import_batch_id=parsed.id,
            source_row_number=1,
            source_transaction_id="synthetic-ref",
        )
        for _ in range(2)
    ]
    db.add_all(rows)
    db.flush()
    db.refresh(parsed)
    assert isinstance(parsed.reported_total, Decimal)
    assert rows[0].id != rows[1].id  # identical rows are candidates, not forcibly deduplicated
    assert rows[0].import_batch.id == parsed.id


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"failed_rows": -1}, "ck_import_batches_nonnegative_counters"),
        ({"file_hash": "bad-hash"}, "ck_import_batches_sha256_format"),
        ({"reported_total": Decimal("1.00")}, "ck_import_batches_totals_require_currency"),
        (
            {"statement_period_start": date(2026, 9, 2), "statement_period_end": date(2026, 9, 1)},
            "ck_import_batches_period_order",
        ),
    ],
)
def test_import_checks(db, account, fields, constraint):
    assert_rejected(db, batch(account, **fields), constraint)


def test_database_enum_rejects_unknown_status(db, account):
    row = batch(account)
    db.add(row)
    db.flush()
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.execute(
            text("UPDATE import_batches SET import_status = 'BOGUS' WHERE id = :id"), {"id": row.id}
        )
    assert error.value.orig.diag.constraint_name == "ck_import_batches_import_status"


def test_cross_user_and_cross_account_references_rejected(db, account):
    other_user = User(email="other@example.invalid")
    db.add(other_user)
    db.flush()
    other_account = Account(
        user_id=other_user.id, display_name="Other", account_type=AccountType.CASH, currency="TRY"
    )
    same_owner_account = Account(
        user_id=account.user_id,
        display_name="Second",
        account_type=AccountType.CASH,
        currency="TRY",
    )
    db.add_all([other_account, same_owner_account])
    db.flush()
    assert_rejected(
        db, transaction(account, user_id=other_user.id), "fk_transactions_account_owner"
    )
    assert_rejected(db, batch(account, user_id=other_user.id), "fk_import_batches_account_owner")
    other_batch = batch(same_owner_account)
    db.add(other_batch)
    db.flush()
    assert_rejected(
        db,
        transaction(account, import_batch_id=other_batch.id),
        "fk_transactions_import_account_owner",
    )
    left, right = transaction(account), transaction(other_account)
    db.add_all([left, right])
    db.flush()
    assert_rejected(
        db,
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=left.id,
            target_transaction_id=right.id,
            link_type=LinkType.REFUND_OF,
        ),
        "fk_transaction_links_target_owner",
    )


@pytest.fixture
def pair(db, account):
    rows = [
        transaction(account, amount=Decimal("500.00"), transaction_type=TransactionType.REFUND),
        transaction(account),
    ]
    db.add_all(rows)
    db.flush()
    return rows


def test_refund_direction_partial_amount_and_duplicate_link(db, account, pair):
    refund, purchase = pair
    link = TransactionLink(
        user_id=account.user_id,
        source_transaction_id=refund.id,
        target_transaction_id=purchase.id,
        link_type=LinkType.REFUND_OF,
        linked_amount=Decimal("500.00"),
        currency="TRY",
        confidence=Decimal("0.9500"),
    )
    db.add(link)
    db.flush()
    db.refresh(link)
    assert link.source_transaction.transaction_type == TransactionType.REFUND
    assert link.target_transaction.id == purchase.id
    assert link.linked_amount == Decimal("500.00") and isinstance(link.linked_amount, Decimal)
    assert link.confidence == Decimal("0.9500") and not link.is_user_confirmed
    assert_rejected(
        db,
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=refund.id,
            target_transaction_id=purchase.id,
            link_type=LinkType.REFUND_OF,
        ),
        "uq_transaction_links_pair_type",
    )


@pytest.mark.parametrize("link_type", [LinkType.TRANSFER_PAIR, LinkType.CARD_PAYMENT_PAIR])
def test_symmetric_links_require_canonical_uuid_order(db, account, pair, link_type):
    left, right = sorted(row.id for row in pair)
    db.add(
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=left,
            target_transaction_id=right,
            link_type=link_type,
        )
    )
    db.flush()
    assert_rejected(
        db,
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=right,
            target_transaction_id=left,
            link_type=link_type,
        ),
        "ck_transaction_links_symmetric_order",
    )


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"confidence": Decimal("1.1")}, "ck_transaction_links_confidence_range"),
        ({"linked_amount": Decimal("1.00")}, "ck_transaction_links_amount_currency_pair"),
        (
            {"linked_amount": Decimal("-1.00"), "currency": "TRY"},
            "ck_transaction_links_linked_amount_positive",
        ),
    ],
)
def test_link_checks(db, account, pair, fields, constraint):
    assert_rejected(
        db,
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=pair[0].id,
            target_transaction_id=pair[1].id,
            link_type=LinkType.REFUND_OF,
            **fields,
        ),
        constraint,
    )


def test_self_link_rejected(db, account, pair):
    assert_rejected(
        db,
        TransactionLink(
            user_id=account.user_id,
            source_transaction_id=pair[0].id,
            target_transaction_id=pair[0].id,
            link_type=LinkType.REFUND_OF,
        ),
        "ck_transaction_links_not_self",
    )


def test_user_email_normalization_and_database_uniqueness(db):
    user = User(email="  SYNTHETIC@EXAMPLE.INVALID  ")
    db.add(user)
    db.flush()
    assert user.email == "synthetic@example.invalid"
    assert_rejected(db, User(email="Synthetic@example.invalid"), "uq_users_email")


def test_system_timestamp_utc_and_naive_rejection(db):
    created = datetime(2026, 9, 3, 12, tzinfo=timezone(timedelta(hours=3)))
    user = User(email="utc@example.invalid", created_at=created)
    db.add(user)
    db.flush()
    db.refresh(user)
    assert user.created_at == datetime(2026, 9, 3, 9, tzinfo=UTC)
    before = user.updated_at
    user.email = "utc-updated@example.invalid"
    db.flush()
    db.refresh(user)
    assert user.updated_at >= before and user.updated_at.utcoffset() == timedelta(0)
    with pytest.raises(StatementError), db.begin_nested():
        db.add(User(email="naive@example.invalid", created_at=datetime(2026, 9, 3)))
        db.flush()


def test_masked_account_rejects_unmasked_identifier(db, account):
    assert_rejected(
        db,
        Account(
            user_id=account.user_id,
            display_name="Invalid",
            account_type=AccountType.DEBIT_CARD,
            currency="TRY",
            account_number_masked="12345678",
        ),
        "ck_accounts_masked_suffix_only",
    )


def test_catalog_and_user_corrections_persist_independently(db, account):
    parent = Category(code="SYNTHETIC_PARENT", display_name="Parent")
    db.add(parent)
    db.flush()
    category = Category(code="SYNTHETIC_CHILD", display_name="Child", parent_id=parent.id)
    db.add(category)
    db.flush()
    alias = MerchantAlias(
        pattern="SYNTHETIC",
        normalized_merchant="Synthetic merchant",
        default_category_id=category.id,
    )
    rule = UserMerchantRule(
        user_id=account.user_id,
        merchant_key="Synthetic merchant",
        preferred_merchant_name="My label",
        category_id=category.id,
    )
    db.add_all([alias, rule])
    db.flush()
    alias.normalized_merchant = "Global label changed"
    db.flush()
    db.expire_all()
    assert rule.preferred_merchant_name == "My label" and rule.category.code == "SYNTHETIC_CHILD"
    assert category.parent.id == parent.id
    assert_rejected(
        db,
        UserMerchantRule(user_id=account.user_id, merchant_key="Synthetic merchant"),
        "uq_user_merchant_rules_user_key",
    )
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(delete(Category).where(Category.id == category.id))


def test_import_audit_cannot_be_deleted_while_referenced(db, account):
    imported = batch(account)
    db.add(imported)
    db.flush()
    db.add(transaction(account, import_batch_id=imported.id))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(delete(ImportBatch).where(ImportBatch.id == imported.id))


@pytest.mark.parametrize("delete_owner", [True, False])
def test_privacy_deletion_cascades_only_owned_financial_data(db, account, delete_owner):
    owner_id, account_id = account.user_id, account.id
    imported = batch(account)
    db.add(imported)
    db.flush()
    rows = [transaction(account, import_batch_id=imported.id), transaction(account)]
    db.add_all(rows)
    db.flush()
    db.add(
        TransactionLink(
            user_id=owner_id,
            source_transaction_id=rows[0].id,
            target_transaction_id=rows[1].id,
            link_type=LinkType.REFUND_OF,
        )
    )
    db.add(UserMerchantRule(user_id=owner_id, merchant_key="Synthetic"))
    category = Category(code="PERSISTENT_CATALOG", display_name="Shared")
    db.add(category)
    survivor = User(email="survivor@example.invalid")
    db.add(survivor)
    db.flush()
    if delete_owner:
        db.execute(delete(User).where(User.id == owner_id))
    else:
        db.execute(delete(Account).where(Account.id == account_id))
    db.expire_all()
    for model in [Account, ImportBatch, Transaction, TransactionLink]:
        assert db.scalar(select(model.id).where(model.user_id == owner_id)) is None
    assert db.scalar(select(Category.id).where(Category.id == category.id)) is not None
    assert db.scalar(select(User.id).where(User.id == survivor.id)) is not None
    rules = db.scalar(select(UserMerchantRule.id).where(UserMerchantRule.user_id == owner_id))
    assert (rules is None) == delete_owner
