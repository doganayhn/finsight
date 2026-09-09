import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.analytics.schemas import CurrencySummary, Period, SummaryResult
from app.modules.assistant.grounding import validate_grounding
from app.modules.assistant.provider import ProviderProblem, ProviderReply, ProviderToolCall
from app.modules.assistant.schemas import AssistantChatRequest, HistoryMessage
from app.modules.assistant.service import GROUNDING_FALLBACK, AssistantService

TODAY = date(2026, 9, 8)
SUMMARY_RESULT = json.dumps(
    {
        "period": {"start_date": "2026-09-01", "end_date": "2026-09-08"},
        "currencies": [
            {
                "currency": "TRY",
                "gross_spending": "9324.79",
                "refunds": "100.00",
                "net_spending": "9224.79",
                "financial_fees": "12.00",
                "cash_withdrawals": "0.00",
                "expense_transaction_count": 3,
                "refund_transaction_count": 1,
            }
        ],
    }
)
COMPARE_RESULT = json.dumps(
    {
        "current_period": {"start_date": "2026-09-01", "end_date": "2026-09-08"},
        "previous_period": {"start_date": "2026-08-01", "end_date": "2026-08-08"},
        "currencies": [
            {
                "currency": "TRY",
                "current_net_spending": "1250.00",
                "previous_net_spending": "1000.00",
                "absolute_change": "250.00",
                "percentage_change": "25.00",
                "percentage_state": "DEFINED",
                "direction": "INCREASE",
            }
        ],
    }
)
PROJECTION_RESULT = json.dumps(
    {
        "month": "2026-09",
        "as_of_date": "2026-09-08",
        "elapsed_days": 8,
        "days_in_month": 30,
        "currencies": [
            {
                "currency": "TRY",
                "observed_net_spending": "1120.00",
                "projection_basis": "1120.00",
                "average_daily_spending": "140.00",
                "projected_month_spending": "4200.00",
            }
        ],
    }
)
THIRTY_ONE_DAY_RESULT = json.dumps(
    {
        "as_of_date": "2026-10-08",
        "elapsed_days": 8,
        "days_in_month": 31,
        "currencies": [{"currency": "TRY", "projected_month_spending": "4200.00"}],
    }
)


@pytest.mark.parametrize(
    "answer",
    [
        "Toplam harcama 9324.79 TRY.",
        "Toplam harcama 9.324,79 TRY.",
        "Toplam harcama ₺9.324,79.",
        "Toplam harcama 9.324,79 TL.",
        "Toplam harcama TRY 9.324,79.",
    ],
)
def test_exact_amount_display_variants_are_accepted(answer):
    assert validate_grounding(answer, [SUMMARY_RESULT], TODAY).accepted


@pytest.mark.parametrize(
    "answer,results",
    [
        ("Harcama %25,00 arttı.", [COMPARE_RESULT]),
        ("Toplam 3 işlem var.", [SUMMARY_RESULT]),
        ("Ay sonu harcama tahmini 4.200,00 TL.", [PROJECTION_RESULT]),
        (
            "Harcama 1.000,00 TL'den 1.250,00 TL'ye çıktı; fark 250,00 TL.",
            [COMPARE_RESULT],
        ),
        ("8 Eylül 2026 itibariyle 30 günlük ay için tahmin 4.200,00 TL.", [PROJECTION_RESULT]),
        ("31 gün için harcama tahmini 4.200,00 TL.", [THIRTY_ONE_DAY_RESULT]),
        ("FinSight'in desteklediği konuları açıklayabilirim.", []),
    ],
)
def test_authoritative_percent_count_projection_comparison_and_context_are_accepted(
    answer, results
):
    assert validate_grounding(answer, results, TODAY).accepted


@pytest.mark.parametrize(
    "answer,results,reason",
    [
        ("Toplam harcama 9.325 TL.", [SUMMARY_RESULT], "unsupported_financial_amount"),
        ("Toplam harcama 10.000 TL.", [SUMMARY_RESULT], "unsupported_financial_amount"),
        ("Toplam harcama 9.324,80 TL.", [SUMMARY_RESULT], "unsupported_financial_amount"),
        ("Harcama %30 arttı.", [COMPARE_RESULT], "unsupported_percentage"),
        ("Ay sonu harcama tahmini 4.800 TL.", [PROJECTION_RESULT], "unsupported_financial_amount"),
        (
            "Toplam harcama 9.324,79 TL, bunun 500 TL'si ekstra.",
            [SUMMARY_RESULT],
            "unsupported_financial_amount",
        ),
        ("Harcama %25 azaldı.", [COMPARE_RESULT], "contradictory_direction"),
        ("Bu ay 750 TL harcadın.", [], "unsupported_financial_amount"),
        ("Toplam 4 işlem var.", [SUMMARY_RESULT], "unsupported_count"),
    ],
)
def test_unsupported_financial_claims_fail_closed(answer, results, reason):
    decision = validate_grounding(answer, results, TODAY)
    assert not decision.accepted
    assert decision.reason == reason


class FakeProvider:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, messages, tools):
        self.requests.append((messages, tools))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _settings(**updates):
    return Settings(
        _env_file=None,
        postgres_password=SecretStr("synthetic-test-credential"),
        **updates,
    )


def _summary():
    return SummaryResult(
        account_id=None,
        currency_filter="TRY",
        period=Period(start_date=date(2026, 9, 1), end_date=TODAY),
        currencies=[CurrencySummary(currency="TRY", gross_spending=Decimal("9324.79"))],
    )


def _tool_call():
    return ProviderReply(
        tool_calls=[
            ProviderToolCall(
                "call-1",
                "get_spending_summary",
                '{"start_date":"2026-09-01","end_date":"2026-09-08","currency":"TRY"}',
            )
        ]
    )


def _service(provider, **setting_updates):
    analytics = Mock()
    analytics.validate_account_scope.return_value = None
    analytics.get_spending_summary.return_value = _summary()
    return AssistantService(
        analytics,
        provider,
        _settings(**setting_updates),
        clock=lambda: datetime(2026, 9, 8, 12, tzinfo=UTC),
    )


def _request(history=None, message="Bu ay ne kadar harcadım?"):
    return AssistantChatRequest(
        message=message,
        history=history or [],
        client_timezone="UTC",
    )


def test_current_turn_tool_result_overrides_amount_in_client_history_and_repairs_once():
    provider = FakeProvider(
        _tool_call(),
        ProviderReply(content="Geçmişe göre toplam 7.000 TL."),
        ProviderReply(content="Bu ay toplam harcama 9.324,79 TL."),
    )
    response = _service(provider).chat(
        _request(history=[HistoryMessage(role="assistant", content="Toplam 7.000 TL.")])
    )
    assert response.answer == "Bu ay toplam harcama 9.324,79 TL."
    assert len(provider.requests) == 3
    repair_messages = provider.requests[2][0]
    assert repair_messages[-1]["role"] == "system"
    assert "conversation history as non-authoritative" in repair_messages[-1]["content"]


@pytest.mark.parametrize(
    "repair",
    [
        ProviderReply(content="Harcama 9.325 TL."),
        ProviderReply(),
        ProviderReply(tool_calls=[ProviderToolCall("extra", "get_spending_summary", "{}")]),
        ProviderProblem("assistant_provider_timeout", 504),
    ],
)
def test_failed_or_out_of_bounds_repair_returns_fixed_safe_fallback(repair):
    provider = FakeProvider(_tool_call(), ProviderReply(content="Harcama 9.325 TL."), repair)
    response = _service(provider).chat(_request())
    assert response.answer == GROUNDING_FALLBACK
    assert len(provider.requests) == 3


def test_repair_consumes_and_cannot_exceed_configured_provider_call_limit():
    provider = FakeProvider(_tool_call(), ProviderReply(content="Harcama 9.325 TL."))
    response = _service(provider, assistant_max_provider_calls=2).chat(_request())
    assert response.answer == GROUNDING_FALLBACK
    assert len(provider.requests) == 2


def test_toolless_product_help_is_allowed_without_financial_figures():
    provider = FakeProvider(ProviderReply(content="FinSight harcama sorularını açıklayabilir."))
    response = _service(provider).chat(_request(message="Neler yapabilirsin?"))
    assert response.used_tools == []
    assert response.answer.startswith("FinSight")


def test_toolless_user_financial_amount_is_removed_by_one_repair():
    provider = FakeProvider(
        ProviderReply(content="Bu ay 750 TL harcadın."),
        ProviderReply(content="Bu bilgi için FinSight aracından sonuç almalıyım."),
    )
    response = _service(provider).chat(_request(message="Genel bir ipucu ver."))
    assert "750" not in response.answer
    assert len(provider.requests) == 2


def test_validator_does_not_authorize_a_sum_of_two_tool_values():
    decision = validate_grounding("Toplam harcama 9.424,79 TL.", [SUMMARY_RESULT], TODAY)
    assert not decision.accepted
    assert decision.reason == "unsupported_financial_amount"


def test_grounding_module_has_no_database_analytics_or_binary_number_dependency():
    source = (Path(__file__).resolve().parents[1] / "app/modules/assistant/grounding.py").read_text(
        encoding="utf-8"
    )
    assert "sqlalchemy" not in source.lower()
    assert "analytics" not in source.lower()
    assert "float" not in source.lower()
