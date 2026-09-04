"""Provider-neutral preview candidates and source period label.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("import_batches", sa.Column("statement_period", sa.String(100), nullable=True))
    op.create_table(
        "import_transaction_candidates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("merchant_raw", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("transaction_type", sa.String(15), nullable=False),
        sa.Column("source_transaction_id", sa.Text(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("import_batch_id", "source_row_number"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        sa.CheckConstraint(
            "amount > '-Infinity'::numeric AND amount < 'Infinity'::numeric", name="amount_finite"
        ),
        sa.CheckConstraint(
            "transaction_type IN ('EXPENSE','INCOME','TRANSFER','REFUND','FEE',"
            "'INTEREST','CARD_PAYMENT','CASH_WITHDRAWAL','UNKNOWN')",
            name="transaction_type",
        ),
        sa.CheckConstraint("source_row_number > 0", name="source_row_positive"),
        sa.CheckConstraint("source_page_number > 0", name="source_page_positive"),
    )
    op.create_index(
        "ix_import_transaction_candidates_import_batch_id",
        "import_transaction_candidates",
        ["import_batch_id"],
    )


def downgrade():
    op.drop_table("import_transaction_candidates")
    op.drop_column("import_batches", "statement_period")
