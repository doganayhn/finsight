from dataclasses import fields, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pdf_factory import synthetic_pdf

from app.modules.imports.enums import ValidationStatus
from app.modules.imports.exceptions import (
    StatementParseError,
    StatementValidationError,
    UnsupportedStatementError,
)
from app.modules.imports.parsers.yapikredi_tlcard import (
    YapiKrediTLCardPDFParser,
    parse_turkish_money,
)
from app.modules.imports.schemas import (
    CanonicalTransactionCandidate,
    ExtractedDocument,
    ExtractedPage,
    ParsedStatement,
)

FIXTURE = Path(__file__).parent / "fixtures" / "tlcard_synthetic.txt"


def document(text=None):
    text = FIXTURE.read_text(encoding="utf-8") if text is None else text
    return ExtractedDocument(
        tuple(ExtractedPage(i, page) for i, page in enumerate(text.split("\f"), 1))
    )


@pytest.fixture
def parser():
    return YapiKrediTLCardPDFParser()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1.234,56", "1234.56"),
        ("9.324,79", "9324.79"),
        ("880,00", "880.00"),
        ("0,01", "0.01"),
        ("12.345.678,90", "12345678.90"),
    ],
)
def test_turkish_money_exact(source, expected):
    result = parse_turkish_money(source)
    assert isinstance(result, Decimal) and result == Decimal(expected)


@pytest.mark.parametrize(
    "source",
    [
        "1,234.56",
        "12.34,56",
        "1.234,5",
        "1.234,567",
        "1 234,56",
        "NaN",
        "Infinity",
        "-50,00",
        "+50,00",
        "(50,00)",
        "",
        "50",
        "00,10",
        "10000000000000000,00",
    ],
)
def test_malformed_money_rejected_without_echo(source):
    with pytest.raises(StatementParseError, match="monetary|Monetary") as error:
        parse_turkish_money(source)
    if source:
        assert source not in str(error.value)


def test_recognition_requires_combined_markers(parser):
    assert parser.can_parse(document())
    for marker in ["Yapı Kredi", "TLcard", "Hesap Özeti Dönemi", "İşlem Tarihi", "Toplam Dönem"]:
        other = document(FIXTURE.read_text(encoding="utf-8").replace(marker, "UNRELATED"))
        assert not parser.can_parse(other)
        with pytest.raises(UnsupportedStatementError):
            parser.parse(other)
    assert not parser.can_parse(document("Yapı Kredi unrelated loan advertisement"))


def test_synthetic_statement_provenance_points_and_no_normalization(parser):
    statement = parser.parse(document())
    assert statement.statement_period == "2024-01"
    assert statement.statement_period_start is None and statement.statement_period_end is None
    assert statement.currency == "TRY" and statement.reported_total == Decimal("1340.00")
    assert statement.parser_name == "yapikredi_tlcard_pdf" and statement.parser_version == "1.0.0"
    rows = statement.transactions
    assert [r.amount for r in rows] == [Decimal("-1234.56"), Decimal("-80.00"), Decimal("-25.44")]
    assert all(isinstance(r.amount, Decimal) and r.transaction_type == "EXPENSE" for r in rows)
    assert [r.transaction_date for r in rows] == [
        date(2024, 1, 2),
        date(2024, 1, 7),
        date(2024, 1, 9),
    ]
    assert [r.source_row_number for r in rows] == [1, 2, 3]
    assert [r.source_page_number for r in rows] == [1, 1, 2]
    assert rows[1].description_raw == rows[1].merchant_raw == "DEMO CAFE  İSTANBUL TR"
    assert rows[2].description_raw == "DEMO PAY *ÖRNEK UZUN\nMAĞAZA ISTANBUL TR"
    assert rows[2].merchant_raw == rows[2].description_raw
    result = parser.validate(statement)
    assert result.status == ValidationStatus.PASSED
    assert result.parsed_purchase_magnitude == Decimal("1340.00")
    assert result.qualifying_purchase_count == 3 and result.issues == ()
    result.require_passed()


def test_reported_total_mismatch_is_structured_failure(parser):
    text = FIXTURE.read_text(encoding="utf-8").replace("Tutarı : 1.340,00", "Tutarı : 1.341,00")
    result = parser.validate(parser.parse(document(text)))
    assert result.status == ValidationStatus.FAILED
    assert result.issues == ("purchase_total_mismatch",)
    with pytest.raises(StatementValidationError):
        result.require_passed()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("1.234,56 777", "12.34,56 777"),
        ("1.234,56 777", "12.34,56 0,25"),
        ("1.234,56 777", "1.234,56 BAD_POINTS"),
        ("1.234,56 777", "1.234,567 777"),
        ("1.234,56 777", "-1.234,56 777"),
        ("2 Ocak 2024", "32 Ocak 2024"),
        ("2 Ocak 2024", "2 INVALID 2024"),
        ("2 Ocak 2024", "2 Ocak"),
        ("Dönemi : Ocak 2024", "Dönemi : INVALID"),
        ("Tutarı : 1.340,00", "Tutarı : 1.34,00"),
        ("TOPLAM 1.340,00 777,25", "TOPLAM 1.341,00 777,25"),
        ("TOPLAM 1.340,00 777,25", ""),
    ],
)
def test_broken_critical_rows_or_metadata_fail(parser, old, new):
    text = FIXTURE.read_text(encoding="utf-8").replace(old, new)
    with pytest.raises(StatementParseError):
        parser.parse(document(text))


def test_dates_keep_explicit_year_across_boundary(parser):
    text = FIXTURE.read_text(encoding="utf-8").replace("2 Ocak 2024", "31 Aralık 2023")
    statement = parser.parse(document(text))
    assert statement.transactions[0].transaction_date == date(2023, 12, 31)
    assert statement.transactions[1].transaction_date == date(2024, 1, 7)


def test_cash_excluded_and_unknown_rows_fail_review(parser):
    text = FIXTURE.read_text(encoding="utf-8")
    text = text.replace(
        "TOPLAM 1.340,00 777,25", "10 Ocak 2024 NAKİT ÇEKİM 100,00\nTOPLAM 1.440,00 777,25"
    )
    statement = parser.parse(document(text))
    assert statement.transactions[-1].transaction_type == "CASH_WITHDRAWAL"
    assert statement.transactions[-1].merchant_raw is None
    assert parser.validate(statement).status == ValidationStatus.PASSED
    unknown = parser.parse(document(text.replace("NAKİT ÇEKİM", "İADE")))
    assert unknown.transactions[-1].transaction_type == "UNKNOWN"
    assert "unclassified_rows" in parser.validate(unknown).issues


def test_validation_never_abs_arbitrary_income_or_wrong_sign(parser):
    statement = parser.parse(document())
    incoming = replace(
        statement.transactions[0], amount=Decimal("1234.56"), transaction_type="INCOME"
    )
    result = parser.validate(
        replace(statement, transactions=(incoming, *statement.transactions[1:]))
    )
    assert result.status == ValidationStatus.FAILED
    assert result.parsed_purchase_magnitude == Decimal("105.44")
    wrong = replace(statement.transactions[0], amount=Decimal("1234.56"))
    assert (
        parser.validate(replace(statement, transactions=(wrong,))).status == ValidationStatus.FAILED
    )


def test_empty_table_and_conflicting_metadata_fail(parser):
    text = FIXTURE.read_text(encoding="utf-8")
    for addition in [
        "Hesap Özeti Dönemi : Şubat 2024",
        "Toplam Dönem Alışveriş Tutarı : 1.350,00 TL",
    ]:
        with pytest.raises(StatementParseError):
            parser.parse(document(text + "\n" + addition))
    empty = text.split("İşlem Tarihi")[0] + "İşlem Tarihi İşlemler Tutar (TL) Puan\nTOPLAM 0,00"
    with pytest.raises(StatementParseError):
        parser.parse(document(empty))


def test_dto_privacy_and_no_orm_or_database_use(parser, monkeypatch, caplog):
    import sqlalchemy
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Session

    def forbidden(*args, **kwargs):
        pytest.fail("Parser attempted database access")

    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr(Connection, "execute", forbidden)
    monkeypatch.setattr(Session, "add", forbidden)
    monkeypatch.setattr(Session, "commit", forbidden)
    statement = parser.parse(document())
    parser.validate(statement).require_passed()
    prohibited = {
        "customer_name",
        "address",
        "customer_number",
        "card_number",
        "account_number",
        "category_id",
        "merchant_normalized",
    }
    for model in [ParsedStatement, CanonicalTransactionCandidate]:
        assert not prohibited.intersection(f.name for f in fields(model))
        assert not hasattr(model, "__table__")
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in repr(statement)
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in str(statement.transactions)
    assert "FINMARKET" not in repr(document())
    assert not caplog.records


def test_real_extractor_with_independently_constructed_pdf(parser):
    from app.modules.imports.parsers.pdf_text import extract_pdf_text

    text = FIXTURE.read_text(encoding="utf-8")
    doc = extract_pdf_text(synthetic_pdf(text.split("\f")))
    assert len(doc.pages) == 2
    statement = parser.parse(doc)
    parser.validate(statement).require_passed()
    assert len(statement.transactions) == 3
    assert statement.transactions[2].merchant_raw == "DEMO PAY *ÖRNEK UZUN\nMAĞAZA ISTANBUL TR"
