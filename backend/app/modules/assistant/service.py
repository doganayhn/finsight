import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import Settings
from app.modules.analytics.service import AnalyticsProblem, AnalyticsService
from app.modules.assistant.grounding import validate_grounding
from app.modules.assistant.prompts import grounding_repair_prompt, system_prompt
from app.modules.assistant.provider import LLMProvider, ProviderProblem
from app.modules.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantScope,
    UsedTool,
)
from app.modules.assistant.tools import AssistantToolRegistry, ToolProblem


class AssistantProblem(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


Clock = Callable[[], datetime]
UNSUPPORTED_PATTERN = re.compile(
    r"\b(bakiye|bakiyem|net worth|net değer|tasarruf oran|kalan para|"
    r"hesabımda.{0,30}(ne kadar|kaç) para|remaining (cash|balance)|current balance)\b",
    re.IGNORECASE,
)
FACTUAL_PATTERN = re.compile(
    r"(harca|kategori|işyeri|mağaza|geçen ay|bu ay|trend|tahmin|ay sonunda|"
    r"\bspend|\bspent|\bcategory|\bmerchant|\bprojection)",
    re.IGNORECASE,
)
UNSUPPORTED_ANSWER = (
    "FinSight, içe aktarılan işlemlerden güncel ve kesin hesap bakiyesini, net değeri "
    "veya kalan parayı belirleyemez. Bankanızdaki güncel bakiyeyi kontrol edin."
)
GROUNDING_FALLBACK = (
    "Finansal yanıtı mevcut FinSight verileriyle güvenli biçimde doğrulayamadım. "
    "Lütfen tekrar deneyin."
)


class AssistantService:
    def __init__(
        self,
        analytics: AnalyticsService,
        provider: LLMProvider | None,
        settings: Settings,
        clock: Clock | None = None,
    ):
        self.analytics = analytics
        self.provider = provider
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def _validate_request(self, request: AssistantChatRequest) -> None:
        if len(request.message) > self.settings.assistant_max_message_chars:
            raise AssistantProblem("assistant_message_too_long", 422)
        if len(request.history) > self.settings.assistant_max_history_messages:
            raise AssistantProblem("assistant_history_too_long", 422)
        if (
            sum(len(item.content) for item in request.history)
            > self.settings.assistant_max_history_chars
        ):
            raise AssistantProblem("assistant_history_too_long", 422)

    def chat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        self._validate_request(request)
        try:
            zone = ZoneInfo(request.client_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise AssistantProblem("assistant_invalid_timezone", 422) from error
        self.analytics.validate_account_scope(request.account_id)
        scope = AssistantScope(account_id=request.account_id)
        if UNSUPPORTED_PATTERN.search(request.message):
            return AssistantChatResponse(answer=UNSUPPORTED_ANSWER, used_tools=[], scope=scope)
        if self.provider is None:
            raise AssistantProblem("assistant_unavailable", 503)

        registry = AssistantToolRegistry(self.analytics, request.account_id)
        local_today = self.clock().astimezone(zone).date()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt(
                    local_today,
                    request.client_timezone,
                    "the selected owned account"
                    if request.account_id
                    else "all accounts owned by the current user",
                ),
            },
            *(item.model_dump() for item in request.history),
            {"role": "user", "content": request.message},
        ]
        used: list[UsedTool] = []
        tool_results: list[str] = []
        calls = 0
        provider_calls = 0
        try:
            for _round in range(self.settings.assistant_max_tool_rounds + 1):
                if provider_calls >= self.settings.assistant_max_provider_calls:
                    raise AssistantProblem("assistant_provider_limit", 502)
                provider_calls += 1
                reply = self.provider.complete(messages, registry.schemas)
                if not reply.tool_calls:
                    answer = (reply.content or "").strip()
                    if not answer:
                        raise AssistantProblem("assistant_malformed_response", 502)
                    if not used and FACTUAL_PATTERN.search(request.message):
                        raise AssistantProblem("assistant_tool_required", 502)
                    decision = validate_grounding(answer, tool_results, local_today)
                    if not decision.accepted:
                        messages.extend(
                            (
                                {"role": "assistant", "content": answer},
                                {"role": "system", "content": grounding_repair_prompt()},
                            )
                        )
                        repaired = None
                        if provider_calls < self.settings.assistant_max_provider_calls:
                            provider_calls += 1
                            try:
                                repaired = self.provider.complete(messages, registry.schemas)
                            except ProviderProblem:
                                pass
                        if repaired is None or repaired.tool_calls:
                            answer = GROUNDING_FALLBACK
                        else:
                            candidate = (repaired.content or "").strip()
                            repaired_decision = validate_grounding(
                                candidate, tool_results, local_today
                            )
                            answer = (
                                candidate
                                if candidate and repaired_decision.accepted
                                else GROUNDING_FALLBACK
                            )
                    return AssistantChatResponse(answer=answer, used_tools=used, scope=scope)
                if _round >= self.settings.assistant_max_tool_rounds:
                    raise AssistantProblem("assistant_tool_limit", 502)
                calls += len(reply.tool_calls)
                if calls > self.settings.assistant_max_tool_calls:
                    raise AssistantProblem("assistant_tool_limit", 502)
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.content,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": call.arguments},
                            }
                            for call in reply.tool_calls
                        ],
                    }
                )
                for call in reply.tool_calls:
                    label, result = registry.execute(call.name, call.arguments)
                    used.append(UsedTool(name=call.name, label=label))
                    tool_results.append(result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": result,
                        }
                    )
        except AssistantProblem:
            raise
        except ToolProblem as error:
            raise AssistantProblem(str(error), 422) from error
        except AnalyticsProblem as error:
            raise AssistantProblem(error.code, error.status) from error
        except ProviderProblem as error:
            raise AssistantProblem(error.code, error.status) from error
        except Exception as error:
            raise AssistantProblem("assistant_tool_failed", 502) from error
        raise AssistantProblem("assistant_tool_limit", 502)
