import socket
from uuid import uuid4

import pytest

from app.modules.categories.repository import CategoryRepository
from app.modules.categories.service import ClassificationService
from app.modules.merchants.models import MerchantAlias, UserMerchantRule
from app.modules.merchants.normalization import comparison_key, merchant_rule_key
from app.modules.transactions.enums import TransactionType


@pytest.mark.parametrize(
    "value,expected",
    [
        ("  DEMO\tCAFE\nİSTANBUL  ", "demo cafe istanbul"),
        ("İ I ı i Ş Ğ Ü Ö Ç", "i ı ı i ş ğ ü ö ç"),
        ("I\u0307 S\u0327 G\u0306 U\u0308 O\u0308 C\u0327", "i ş ğ ü ö ç"),
        ("  demo cafe istanbul ", "demo cafe istanbul"),
    ],
)
def test_comparison_keys_preserve_turkish_unicode(value, expected):
    assert comparison_key(value) == expected
    assert comparison_key(expected) == expected
    assert comparison_key("I") != comparison_key("i")


def test_exact_bounded_user_key_uses_merchant_then_description():
    assert merchant_rule_key("unrelated", " DEMO CAFE ") == merchant_rule_key("demo cafe", None)
    assert merchant_rule_key("demo cafe", " \t") == merchant_rule_key("demo cafe", None)
    first, second = "x" * 1000 + "a", "x" * 1000 + "b"
    assert len(merchant_rule_key(first, None)) == 67
    assert merchant_rule_key(first, None) != merchant_rule_key(second, None)


@pytest.mark.parametrize(
    "raw,merchant,code,source",
    [
        ("TRENDYOL YEMEK ISTANBUL TR", "Trendyol Yemek", "FOOD_DELIVERY", "MERCHANT_RULE"),
        ("TRENDYOL MARKET", "Trendyol", "SHOPPING", "MERCHANT_RULE"),
        ("  migros  ", "Migros", "GROCERIES", "MERCHANT_RULE"),
        ("MIGROS", "Migros", "GROCERIES", "MERCHANT_RULE"),
        ("MİGROS", "Migros", "GROCERIES", "MERCHANT_RULE"),
        ("GETIR MARKET", "Getir", "GROCERIES", "SYSTEM_RULE"),
        ("getir", "Getir", "OTHER", "UNKNOWN"),
        ("DEMO CAFE ISTANBUL TR", None, "CAFE", "SYSTEM_RULE"),
        ("EXAMPLE AKARYAKIT", None, "FUEL", "SYSTEM_RULE"),
        ("EXAMPLE PETROL", None, "FUEL", "SYSTEM_RULE"),
        ("DEMO COFFEE", None, "CAFE", "SYSTEM_RULE"),
        ("DEMO KAHVE", None, "CAFE", "SYSTEM_RULE"),
        ("SAMPLE MARKET ISTANBUL TR", None, "GROCERIES", "SYSTEM_RULE"),
        ("DEMO STORE ONLINE TR", None, "OTHER", "UNKNOWN"),
        ("MARKETING PETROLEUM CAFETERIA", None, "OTHER", "UNKNOWN"),
        ("SAMPLE MARKET CAFE", None, "OTHER", "UNKNOWN"),
    ],
)
def test_aliases_keywords_and_uncertainty(db, raw, merchant, code, source):
    result = ClassificationService(db, uuid4()).classify(raw, None, TransactionType.EXPENSE)
    assert result.merchant_normalized == merchant
    assert result.category_id == CategoryRepository(db).by_code(code).id
    assert result.category_source == source
    assert result.review_status == ("NEEDS_REVIEW" if source == "UNKNOWN" else "AUTO_CONFIRMED")


def test_alias_ties_are_stable_and_inactive_patterns_are_ignored(db):
    db.add_all(
        [
            MerchantAlias(pattern="demo", normalized_merchant="Lowercase"),
            MerchantAlias(pattern="DEMO", normalized_merchant="Uppercase"),
            MerchantAlias(pattern="DEMO SPECIFIC", normalized_merchant="Inactive", is_active=False),
            MerchantAlias(pattern=".*", normalized_merchant="Literal punctuation"),
        ]
    )
    db.flush()
    service = ClassificationService(db, uuid4())
    for order in (service.aliases, list(reversed(service.aliases))):
        # Rebuild from different repository ordering to exercise the sort, not incidental UUIDs.
        from unittest.mock import patch

        with patch(
            "app.modules.merchants.repository.MerchantRepository.aliases",
            return_value=[row for _, row in order],
        ):
            result = ClassificationService(db, uuid4()).classify("DEMO SPECIFIC", None, "EXPENSE")
            assert result.merchant_normalized == "Uppercase"
    assert service.classify("unmatched", None, "EXPENSE").merchant_normalized is None
    assert service.classify("DEMO .*", None, "EXPENSE").merchant_normalized == "Uppercase"


@pytest.mark.parametrize("raw", ["TRENDYOL MARKET", "DEMO MARKET"])
def test_user_rule_overrides_global_and_system_and_is_isolated(db, account, raw):
    cafe = CategoryRepository(db).by_code("CAFE")
    db.add(
        UserMerchantRule(
            user_id=account.user_id,
            merchant_key=merchant_rule_key(raw, None),
            preferred_merchant_name="Demo Coffee",
            category_id=cafe.id,
        )
    )
    db.flush()
    own = ClassificationService(db, account.user_id).classify(raw, None, "EXPENSE")
    assert own.merchant_normalized == "Demo Coffee" and own.category_id == cafe.id
    assert own.category_source == "USER" and own.review_status == "AUTO_CONFIRMED"
    other = ClassificationService(db, uuid4()).classify(raw, None, "EXPENSE")
    assert other.category_source != "USER" and other.merchant_normalized != "Demo Coffee"


def test_partial_user_rule_preserves_field_precedence(db, account):
    raw = "TRENDYOL MARKET"
    db.add(
        UserMerchantRule(
            user_id=account.user_id,
            merchant_key=merchant_rule_key(raw, None),
            preferred_merchant_name="My preferred merchant",
        )
    )
    db.flush()
    result = ClassificationService(db, account.user_id).classify(raw, None, "EXPENSE")
    assert result.merchant_normalized == "My preferred merchant"
    assert result.category_source == "MERCHANT_RULE"
    assert result.category_id == CategoryRepository(db).by_code("SHOPPING").id


@pytest.mark.parametrize(
    "kind,code",
    [
        ("TRANSFER", "TRANSFER"),
        ("CARD_PAYMENT", "TRANSFER"),
        ("INCOME", "INCOME"),
        ("FEE", "FINANCIAL_FEES"),
        ("INTEREST", "OTHER"),
        ("UNKNOWN", "OTHER"),
    ],
)
def test_semantic_types_gate_all_merchant_rule_layers(db, account, kind, code):
    raw = "TRENDYOL MARKET"
    db.add(
        UserMerchantRule(
            user_id=account.user_id,
            merchant_key=merchant_rule_key(raw, raw),
            preferred_merchant_name="Demo Coffee",
            category_id=CategoryRepository(db).by_code("CAFE").id,
        )
    )
    db.flush()
    result = ClassificationService(db, account.user_id).classify(raw, raw, kind)
    assert result.merchant_normalized is None
    assert result.category_id == CategoryRepository(db).by_code(code).id
    assert result.category_source == ("UNKNOWN" if code == "OTHER" else "SYSTEM_RULE")


@pytest.mark.parametrize("kind", ["EXPENSE", "REFUND", "CASH_WITHDRAWAL"])
def test_merchant_types_classify_without_changing_financial_type(db, kind, monkeypatch):
    service = ClassificationService(db, uuid4())

    def forbidden(*args, **kwargs):
        pytest.fail("Classification attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = service.classify("STARBUCKS", None, kind)
    assert result.merchant_normalized == "Starbucks"
    assert result.category_source == "MERCHANT_RULE"
    assert result.category_id == service.categories["CAFE"]
