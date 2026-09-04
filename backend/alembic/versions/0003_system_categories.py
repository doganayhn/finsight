"""Seed the shared system catalog and a small public-brand alias baseline.

Revision ID: 0003
Revises: 0002

Data-only migration. Downgrade intentionally retains shared catalog/alias data:
it may already be referenced or edited. Re-upgrade preserves existing rows.
No live application model imports.
"""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATEGORIES = (
    ("GROCERIES", "Groceries"),
    ("RESTAURANTS", "Restaurants"),
    ("CAFE", "Cafe"),
    ("FOOD_DELIVERY", "Food delivery"),
    ("TRANSPORTATION", "Transportation"),
    ("FUEL", "Fuel"),
    ("SHOPPING", "Shopping"),
    ("ENTERTAINMENT", "Entertainment"),
    ("SUBSCRIPTIONS", "Subscriptions"),
    ("BILLS", "Bills"),
    ("HOUSING", "Housing"),
    ("HEALTH", "Health"),
    ("EDUCATION", "Education"),
    ("TRAVEL", "Travel"),
    ("FINANCIAL_FEES", "Financial fees"),
    ("INCOME", "Income"),
    ("TRANSFER", "Transfer"),
    ("OTHER", "Other"),
)
# Public brands, independent of any private statement. GETIR is deliberately
# normalization-only because its services span more than one spending category.
ALIASES = (
    ("MIGROS", "Migros", "GROCERIES"),
    ("MİGROS", "Migros", "GROCERIES"),
    ("STARBUCKS", "Starbucks", "CAFE"),
    ("AMAZON", "Amazon", "SHOPPING"),
    ("TRENDYOL", "Trendyol", "SHOPPING"),
    ("TRENDYOL YEMEK", "Trendyol Yemek", "FOOD_DELIVERY"),
    ("GETIR", "Getir", None),
    ("GETİR", "Getir", None),
    ("DECATHLON", "Decathlon", "SHOPPING"),
)


def upgrade():
    connection = op.get_bind()
    for code, display_name in CATEGORIES:
        connection.execute(
            sa.text(
                "INSERT INTO categories (id, code, display_name, is_system) "
                "VALUES (:id, :code, :name, true) ON CONFLICT (code) DO NOTHING"
            ),
            {
                "id": uuid5(NAMESPACE_URL, f"urn:finsight:category:{code}"),
                "code": code,
                "name": display_name,
            },
        )
        if not connection.scalar(
            sa.text("SELECT is_system FROM categories WHERE code = :code"), {"code": code}
        ):
            raise RuntimeError("System category code conflicts with a non-system category")
    for pattern, merchant, code in ALIASES:
        connection.execute(
            sa.text(
                "INSERT INTO merchant_aliases "
                "(id, pattern, normalized_merchant, default_category_id, is_active) "
                "VALUES (:id, :pattern, :merchant, "
                "(SELECT id FROM categories WHERE code = :code), true) "
                "ON CONFLICT (pattern) DO NOTHING"
            ),
            {
                "id": uuid5(NAMESPACE_URL, f"urn:finsight:merchant-alias:{pattern}"),
                "pattern": pattern,
                "merchant": merchant,
                "code": code,
            },
        )


def downgrade():
    # Shared reference data cannot be safely identified as unused seed data once
    # deployed. Retain it, including edits and references, instead of deleting it.
    pass
