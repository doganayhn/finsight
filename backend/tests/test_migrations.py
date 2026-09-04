from decimal import Decimal
from uuid import UUID

from db_support import isolated_database, run_migration
from sqlalchemy import inspect, text

EXPECTED_TABLES = {
    "users",
    "accounts",
    "categories",
    "import_batches",
    "transactions",
    "transaction_links",
    "merchant_aliases",
    "user_merchant_rules",
    "alembic_version",
}


def test_clean_migration_downgrade_reupgrade_and_drift():
    with isolated_database() as engine:
        assert inspect(engine).get_table_names() == []
        for _ in range(2):
            run_migration(engine, "upgrade", "head")
            assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
            run_migration(engine, "check")
            with engine.begin() as connection:
                # Raw SQL exercises server-generated UUIDs/defaults, not Python defaults/create_all.
                user = connection.execute(
                    text(
                        "INSERT INTO users (email) VALUES ('db@example.invalid') "
                        "RETURNING id, created_at"
                    )
                ).one()
                assert isinstance(user.id, UUID) and user.created_at.tzinfo is not None
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            run_migration(engine, "downgrade", "base")
            assert inspect(engine).get_table_names() == ["alembic_version"]
        run_migration(engine, "upgrade", "head")
        run_migration(engine, "check")


def test_database_schema_contract(db_engine):
    inspector = inspect(db_engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES
    columns = {column["name"]: column for column in inspector.get_columns("transactions")}
    expected = {
        "id",
        "user_id",
        "account_id",
        "import_batch_id",
        "transaction_date",
        "posted_date",
        "description_raw",
        "merchant_raw",
        "merchant_normalized",
        "amount",
        "currency",
        "transaction_type",
        "category_id",
        "balance_after",
        "installment_index",
        "installment_count",
        "installment_plan_id",
        "category_source",
        "review_status",
        "source_transaction_id",
        "source_row_number",
        "created_at",
        "updated_at",
    }
    assert set(columns) == expected  # no bank-specific columns or unbounded source_data dump
    assert columns["amount"]["type"].python_type is Decimal
    assert columns["transaction_date"]["type"].__class__.__name__ == "DATE"
    assert columns["created_at"]["type"].timezone
    fks = {fk["name"]: fk for fk in inspector.get_foreign_keys("transactions")}
    assert fks["fk_transactions_account_owner"]["constrained_columns"] == ["account_id", "user_id"]
    assert fks["fk_transactions_import_account_owner"]["constrained_columns"] == [
        "import_batch_id",
        "account_id",
        "user_id",
    ]
    indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("transactions")
    }
    assert indexes["ix_transactions_user_date"] == ["user_id", "transaction_date"]
    assert indexes["ix_transactions_account_source"] == ["account_id", "source_transaction_id"]
    checks = {check["name"] for check in inspector.get_check_constraints("transactions")}
    assert "ck_transactions_installment_order" in checks
    assert "ck_transactions_transaction_type" in checks
