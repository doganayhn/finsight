import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MONEY_KEYS = {
    "amount",
    "gross_spending",
    "refunds",
    "net_spending",
    "financial_fees",
    "cash_withdrawals",
    "current_net_spending",
    "previous_net_spending",
    "absolute_change",
    "observed_net_spending",
    "projection_basis",
    "average_daily_spending",
    "projected_month_spending",
}
PERCENTAGE_KEYS = {"percentage_change"}
COUNT_KEYS = {
    "expense_transaction_count",
    "refund_transaction_count",
    "transaction_count",
    "elapsed_days",
    "days_in_month",
}
CURRENCY_ALIASES = {
    "₺": "TRY",
    "TL": "TRY",
    "TRY": "TRY",
    "$": "USD",
    "USD": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
}
NUMBER_PATTERN = re.compile(
    r"(?<![\w])[-+]?(?:\d{1,3}(?:[.\s\u00a0]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\w])"
)
ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
CURRENCY_PREFIX = re.compile(r"(?:₺|\$|€|£|TRY|TL|USD|EUR|GBP)\s*$", re.IGNORECASE)
CURRENCY_SUFFIX = re.compile(r"^\s*(?:(?:TRY|TL|USD|EUR|GBP)\b|[₺$€£])", re.IGNORECASE)
PERCENT_CONTEXT = re.compile(r"%|\byüzde\b|\bpercent(?:age)?\b|\boran\w*\b", re.IGNORECASE)
COUNT_CONTEXT = re.compile(r"\b(?:işlem|transaction|adet)\w*\b", re.IGNORECASE)
DAY_CONTEXT = re.compile(
    r"\b(?:gün|day|ay|month|yıl|year|ocak|şubat|mart|nisan|mayıs|haziran|temmuz|"
    r"ağustos|eylül|ekim|kasım|aralık|january|february|march|april|may|june|"
    r"july|august|september|october|november|december)\w*\b",
    re.IGNORECASE,
)
FINANCIAL_CONTEXT = re.compile(
    r"harca|harcama|tutar|toplam|iade|refund|ücret|fee|nakit|cash|"
    r"tahmin|projeksiyon|projection|spend|spent|amount|artış|azalış",
    re.IGNORECASE,
)
INCREASE_PATTERN = re.compile(r"arttı|artış|yükseldi|daha fazla|increas", re.IGNORECASE)
DECREASE_PATTERN = re.compile(r"azaldı|azalış|düştü|daha az|decreas", re.IGNORECASE)
UNCHANGED_PATTERN = re.compile(r"değişmedi|aynı kaldı|unchanged", re.IGNORECASE)


@dataclass(frozen=True)
class MoneyFact:
    value: Decimal
    currency: str | None


@dataclass(frozen=True)
class GroundingAuthority:
    money: frozenset[MoneyFact]
    percentages: frozenset[Decimal]
    counts: frozenset[int]
    context_numbers: frozenset[int]
    directions: frozenset[str]


@dataclass(frozen=True)
class GroundingDecision:
    accepted: bool
    reason: str | None = None


def _decimal_from_display(raw: str) -> Decimal | None:
    value = raw.replace(" ", "").replace("\u00a0", "")
    if not value:
        return None
    sign = ""
    if value[0] in "+-":
        sign, value = value[0], value[1:]
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        value = value.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in value:
        whole, fraction = value.rsplit(",", 1)
        value = whole.replace(",", "") + (f".{fraction}" if len(fraction) <= 2 else fraction)
    elif "." in value:
        whole, fraction = value.rsplit(".", 1)
        if len(fraction) == 3 and len(whole) <= 3:
            value = whole.replace(".", "") + fraction
    try:
        return Decimal(sign + value)
    except InvalidOperation:
        return None


def _currency_near(answer: str, start: int, end: int) -> str | None:
    prefix = CURRENCY_PREFIX.search(answer[max(0, start - 8) : start])
    suffix = CURRENCY_SUFFIX.search(answer[end : end + 8])
    token = prefix.group(0).strip() if prefix else suffix.group(0).strip() if suffix else None
    return CURRENCY_ALIASES.get(token.upper() if token else token)


def _collect_dates(value: str, context_numbers: set[int]) -> None:
    for raw_date in ISO_DATE_PATTERN.findall(value):
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        context_numbers.update((parsed.year, parsed.month, parsed.day))


def _collect(
    value: Any,
    money: set[MoneyFact],
    percentages: set[Decimal],
    counts: set[int],
    context_numbers: set[int],
    directions: set[str],
    inherited_currency: str | None = None,
) -> None:
    if isinstance(value, dict):
        currency_value = value.get("currency")
        currency = (
            currency_value.upper()
            if isinstance(currency_value, str) and currency_value.upper() in CURRENCY_ALIASES
            else inherited_currency
        )
        for key, item in value.items():
            if key in MONEY_KEYS and isinstance(item, str):
                try:
                    money.add(MoneyFact(Decimal(item), currency))
                except InvalidOperation:
                    pass
            elif key in PERCENTAGE_KEYS and isinstance(item, str):
                try:
                    percentages.add(Decimal(item))
                except InvalidOperation:
                    pass
            elif key in COUNT_KEYS and isinstance(item, int) and not isinstance(item, bool):
                counts.add(item)
                context_numbers.add(item)
            elif key == "direction" and isinstance(item, str):
                directions.add(item.upper())
            if isinstance(item, str):
                _collect_dates(item, context_numbers)
            _collect(item, money, percentages, counts, context_numbers, directions, currency)
    elif isinstance(value, list):
        for item in value:
            _collect(
                item, money, percentages, counts, context_numbers, directions, inherited_currency
            )


def authority_from_results(tool_results: list[str], today: date) -> GroundingAuthority:
    money: set[MoneyFact] = set()
    percentages: set[Decimal] = set()
    counts: set[int] = set()
    context_numbers = {today.year, today.month, today.day}
    directions: set[str] = set()
    for raw_result in tool_results:
        try:
            value = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            continue
        _collect(value, money, percentages, counts, context_numbers, directions)
    return GroundingAuthority(
        money=frozenset(money),
        percentages=frozenset(percentages),
        counts=frozenset(counts),
        context_numbers=frozenset(context_numbers),
        directions=frozenset(directions),
    )


def _inside_date(start: int, end: int, date_spans: list[tuple[int, int]]) -> bool:
    return any(start < date_end and end > date_start for date_start, date_end in date_spans)


def _money_is_authorized(
    value: Decimal, currency: str | None, authority: GroundingAuthority
) -> bool:
    return any(
        fact.value == value and (currency is None or fact.currency == currency)
        for fact in authority.money
    )


def validate_grounding(answer: str, tool_results: list[str], today: date) -> GroundingDecision:
    authority = authority_from_results(tool_results, today)
    date_spans = [match.span() for match in ISO_DATE_PATTERN.finditer(answer)]
    for match in NUMBER_PATTERN.finditer(answer):
        start, end = match.span()
        if _inside_date(start, end, date_spans):
            continue
        value = _decimal_from_display(match.group(0))
        if value is None:
            return GroundingDecision(False, "unparseable_numeric_claim")
        nearby = answer[max(0, start - 36) : min(len(answer), end + 36)]
        immediate = answer[max(0, start - 10) : min(len(answer), end + 10)]
        currency = _currency_near(answer, start, end)
        if PERCENT_CONTEXT.search(immediate):
            if value not in authority.percentages:
                return GroundingDecision(False, "unsupported_percentage")
            continue
        if COUNT_CONTEXT.search(immediate):
            if value != value.to_integral_value() or int(value) not in authority.counts:
                return GroundingDecision(False, "unsupported_count")
            continue
        if DAY_CONTEXT.search(immediate) and value == value.to_integral_value():
            if int(value) in authority.context_numbers:
                continue
        if currency is not None or FINANCIAL_CONTEXT.search(nearby):
            if not _money_is_authorized(value, currency, authority):
                return GroundingDecision(False, "unsupported_financial_amount")

    meaningful_directions = authority.directions & {"INCREASE", "DECREASE", "UNCHANGED"}
    if len(meaningful_directions) == 1:
        expected = next(iter(meaningful_directions))
        if expected == "INCREASE" and (
            DECREASE_PATTERN.search(answer) or UNCHANGED_PATTERN.search(answer)
        ):
            return GroundingDecision(False, "contradictory_direction")
        if expected == "DECREASE" and (
            INCREASE_PATTERN.search(answer) or UNCHANGED_PATTERN.search(answer)
        ):
            return GroundingDecision(False, "contradictory_direction")
        if expected == "UNCHANGED" and (
            INCREASE_PATTERN.search(answer) or DECREASE_PATTERN.search(answer)
        ):
            return GroundingDecision(False, "contradictory_direction")
    return GroundingDecision(True)
