"""Exact money and UTC system timestamps at the persistence boundary."""

from datetime import UTC
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, Numeric, column
from sqlalchemy.types import TypeDecorator


class Money(TypeDecorator):
    """NUMERIC(18,2); reject floats and implicit rounding before database binding."""

    impl = Numeric(18, 2)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError("Money must be a Decimal")
        if not value.is_finite() or abs(value) >= Decimal("10000000000000000"):
            raise ValueError("Money must be finite and fit NUMERIC(18,2)")
        if value != value.quantize(Decimal("0.01")):
            raise ValueError("Money must not require rounding to two decimal places")
        return value


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("System timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        return value.astimezone(UTC) if value is not None else None


def enum_type(enum_class, name):
    # Named VARCHAR CHECKs avoid PostgreSQL enum lifecycle complexity in migrations.
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda cls: [item.value for item in cls],
    )


def enum_check(column_name, enum_class):
    # Explicit table CHECKs remain visible to Alembic's constraint drift comparison.
    return CheckConstraint(
        column(column_name).in_([item.value for item in enum_class]), name=column_name
    )


def currency_check(column="currency"):
    return CheckConstraint(f"{column} ~ '^[A-Z]{{3}}$'", name=f"{column}_format")


def finite_money_check(column):
    # PostgreSQL NUMERIC permits NaN; CHECKs protect direct SQL as well as ORM writes.
    return CheckConstraint(
        f"{column} > '-Infinity'::numeric AND {column} < 'Infinity'::numeric",
        name=f"{column}_finite",
    )
