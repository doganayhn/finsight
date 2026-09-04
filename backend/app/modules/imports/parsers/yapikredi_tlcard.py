"""Yapı Kredi TLcard purchase statement adapter, verified against its text layer.

This source is card activity, never a complete account ledger. Only explicitly
bounded table descriptions survive extraction; identity/rewards sections do not.
"""

import re
from datetime import date
from decimal import Decimal

from app.modules.imports.enums import ValidationStatus
from app.modules.imports.exceptions import StatementParseError, UnsupportedStatementError
from app.modules.imports.schemas import (
    CanonicalTransactionCandidate,
    ExtractedDocument,
    ParsedStatement,
    StatementValidation,
)
from app.modules.transactions.enums import TransactionType

MONTHS = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}
MONEY = r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:\.\d{3})+),\d{2}"
POINTS = r"\d+(?:\.\d{3})*(?:,\d+)?"
DATE_START = re.compile(r"^(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})\s+(.+)$")
ROW_END = re.compile(rf"^(.+?)\s+({MONEY})(?:\s+({POINTS}))?$")
HEADER = "işlem tarihi işlemler tutar (tl) puan"
TOTAL_LABEL = r"toplam dönem alışveri\s*ş tutarı\s*:"


def _fold(value: str) -> str:
    return " ".join(value.replace("İ", "i").replace("I", "ı").lower().split())


def parse_turkish_money(value: str) -> Decimal:
    if re.fullmatch(MONEY, value) is None:
        raise StatementParseError("Malformed Turkish monetary value")
    amount = Decimal(value.replace(".", "").replace(",", "."))
    if amount >= Decimal("10000000000000000"):
        raise StatementParseError("Monetary value exceeds canonical precision")
    return amount


def _date(day: str, month: str, year: str) -> date:
    try:
        return date(int(year), MONTHS[_fold(month)], int(day))
    except (ValueError, KeyError):
        raise StatementParseError("Invalid transaction date") from None


class YapiKrediTLCardPDFParser:
    name = "yapikredi_tlcard_pdf"
    version = "1.0.0"

    def can_parse(self, document: ExtractedDocument) -> bool:
        lines = [_fold(line) for page in document.pages for line in page.text.splitlines()]
        text = "\n".join(lines)
        return (
            "yapı kredi" in text
            and re.search(r"\btlcard\b", text) is not None
            and any(line.startswith("hesap özeti dönemi") for line in lines)
            and HEADER in lines
            and any(re.match(TOTAL_LABEL, line) for line in lines)
        )

    def parse(self, document: ExtractedDocument) -> ParsedStatement:
        if not self.can_parse(document):
            raise UnsupportedStatementError("Document is not a supported TLcard statement")
        lines = [_fold(line) for page in document.pages for line in page.text.splitlines()]
        periods = [line for line in lines if line.startswith("hesap özeti dönemi")]
        totals = [line for line in lines if re.match(TOTAL_LABEL, line)]
        period_values = set()
        for line in periods:
            match = re.fullmatch(r"hesap özeti dönemi\s*:\s*([^\W\d_]+)\s+(\d{4})", line)
            if not match:
                raise StatementParseError("Unsupported statement period")
            period_date = _date("1", match[1], match[2])
            period_values.add(f"{period_date.year:04d}-{period_date.month:02d}")
        total_values = set()
        for line in totals:
            match = re.fullmatch(rf"{TOTAL_LABEL}\s*({MONEY})\s+tl", line)
            if not match:
                raise StatementParseError("Invalid reported purchase total")
            total_values.add(parse_turkish_money(match[1]))
        if len(period_values) != 1 or len(total_values) != 1:
            raise StatementParseError("Conflicting statement metadata")
        rows = self._transactions(document)
        return ParsedStatement(
            institution_code="YAPI_KREDI",
            statement_type="TLCARD",
            currency="TRY",
            statement_period=period_values.pop(),
            reported_total=total_values.pop(),
            transactions=tuple(rows),
            parser_name=self.name,
            parser_version=self.version,
        )

    def _transactions(self, document: ExtractedDocument) -> list[CanonicalTransactionCandidate]:
        rows = []
        active = False
        closed = False
        pending = None
        table_total = None
        for page in document.pages:
            # Repeated headers are required before continuing a table on a new page.
            active = False
            for raw_line in page.text.splitlines():
                line = raw_line.strip()
                folded = _fold(line)
                if not line:
                    continue
                if folded == HEADER:
                    if closed:
                        raise StatementParseError("Multiple transaction tables are unsupported")
                    active = True
                    continue
                if not active:
                    continue
                if folded.startswith("toplam"):
                    match = re.fullmatch(rf"toplam\s+({MONEY})(?:\s+({POINTS}))?", folded)
                    if not match or pending is not None:
                        raise StatementParseError("Invalid transaction table total")
                    table_total = parse_turkish_money(match[1])
                    active = False
                    closed = True
                    continue
                if re.fullmatch(r"sayfa\s+\d+\s*/\s*\d+", folded):
                    continue
                dated = DATE_START.fullmatch(line)
                if dated:
                    if pending is not None:
                        raise StatementParseError("Incomplete transaction row")
                    pending = (_date(dated[1], dated[2], dated[3]), dated[4], page.number)
                elif pending is not None:
                    # Wrapped descriptions are retained only while a dated row is incomplete.
                    pending = (pending[0], pending[1] + "\n" + line, pending[2])
                else:
                    raise StatementParseError("Unexpected content in transaction table")
                end = ROW_END.fullmatch(pending[1].replace("\n", " "))
                if end is None:
                    # A line ending in a numeric token is malformed, not a description wrap.
                    if re.search(r"\s+[+-]?[\d.,]+$", line):
                        raise StatementParseError("Malformed transaction amount or points")
                    continue
                # Capture description by matching the tail against the original multiline text.
                tail = re.search(rf"\s+{re.escape(end[2])}(?:\s+{POINTS})?$", pending[1])
                if tail is None:
                    raise StatementParseError("Ambiguous transaction columns")
                description = pending[1][: tail.start()].rstrip()
                if re.search(r"\s+[+-]?[\d.,]*[.,][\d.,]*$", description):
                    raise StatementParseError("Ambiguous monetary columns")
                amount = parse_turkish_money(end[2])
                if amount == 0:
                    raise StatementParseError("Zero purchase amount requires review")
                kind = self._kind(description)
                rows.append(
                    CanonicalTransactionCandidate(
                        transaction_date=pending[0],
                        description_raw=description,
                        merchant_raw=description if kind == TransactionType.EXPENSE else None,
                        amount=-amount,
                        currency="TRY",
                        transaction_type=kind,
                        source_row_number=len(rows) + 1,
                        source_page_number=pending[2],
                    )
                )
                pending = None
        if pending is not None or not rows or not closed:
            raise StatementParseError("Transaction table is incomplete or empty")
        # The table footer is independent evidence and must agree with the parsed rows.
        if sum((-row.amount for row in rows), Decimal("0.00")) != table_total:
            raise StatementParseError("Transaction table total does not reconcile")
        return rows

    @staticmethod
    def _kind(description: str) -> TransactionType:
        value = _fold(description)
        if re.match(r"^(?:nakit çekim|para çekme)(?:\s|$)", value):
            return TransactionType.CASH_WITHDRAWAL
        # Explicit non-purchase operation labels require review; do not guess money-in semantics.
        if re.match(r"^(?:iade|iptal|transfer|havale|eft)(?:\s|$)", value):
            return TransactionType.UNKNOWN
        # Normal rows belong to the recognized card purchase table; no merchant/category rules.
        return TransactionType.EXPENSE

    def validate(self, statement: ParsedStatement) -> StatementValidation:
        issues = []
        if (statement.institution_code, statement.statement_type, statement.currency) != (
            "YAPI_KREDI",
            "TLCARD",
            "TRY",
        ):
            issues.append("unsupported_statement")
        purchases = [
            t for t in statement.transactions if t.transaction_type == TransactionType.EXPENSE
        ]
        if not statement.transactions or statement.reported_total < 0:
            issues.append("invalid_statement")
        if any(t.currency != "TRY" or t.amount >= 0 for t in statement.transactions):
            issues.append("invalid_row_currency_or_sign")
        if any(
            t.transaction_type not in {TransactionType.EXPENSE, TransactionType.CASH_WITHDRAWAL}
            for t in statement.transactions
        ):
            issues.append("unclassified_rows")
        magnitude = sum((-t.amount for t in purchases), Decimal("0.00"))
        if magnitude != statement.reported_total:
            issues.append("purchase_total_mismatch")
        return StatementValidation(
            status=ValidationStatus.FAILED if issues else ValidationStatus.PASSED,
            reported_total=statement.reported_total,
            parsed_purchase_magnitude=magnitude,
            qualifying_purchase_count=len(purchases),
            issues=tuple(issues),
        )
