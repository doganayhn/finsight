import json
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.modules.analytics.schemas import (
    CompareQuery,
    ExplorerQuery,
    MerchantQuery,
    PeriodQuery,
    ProjectionQuery,
)
from app.modules.analytics.service import AnalyticsService
from app.modules.assistant.schemas import (
    CompareToolArgs,
    MerchantToolArgs,
    PeriodToolArgs,
    ProjectionToolArgs,
    SearchTransactionsToolArgs,
)


class ToolProblem(Exception):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    description: str
    arguments: type[BaseModel]

    def provider_schema(self) -> dict[str, Any]:
        schema = self.arguments.model_json_schema()
        schema["additionalProperties"] = False
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": schema},
        }


DEFINITIONS = (
    ToolDefinition(
        "get_spending_summary",
        "Harcama özeti",
        "Deterministic spending summary for an explicit inclusive calendar period.",
        PeriodToolArgs,
    ),
    ToolDefinition(
        "get_category_breakdown",
        "Kategori dağılımı",
        "Deterministic spending breakdown by canonical category.",
        PeriodToolArgs,
    ),
    ToolDefinition(
        "get_merchant_breakdown",
        "İşyeri dağılımı",
        "Deterministic top merchant spending breakdown; limit is at most 10 per currency.",
        MerchantToolArgs,
    ),
    ToolDefinition(
        "get_monthly_trend",
        "Aylık eğilim",
        "Deterministic monthly spending trend for an explicit inclusive period.",
        PeriodToolArgs,
    ),
    ToolDefinition(
        "compare_periods",
        "Dönem karşılaştırması",
        "Compare two explicit periods, optionally for one canonical category code.",
        CompareToolArgs,
    ),
    ToolDefinition(
        "project_month_spending",
        "Ay sonu harcama tahmini",
        "Project spending pace through as_of_date; this is not remaining cash.",
        ProjectionToolArgs,
    ),
    ToolDefinition(
        "search_transactions",
        "İşlem arama",
        "Search at most 20 canonical transactions. Prefer aggregate tools when possible.",
        SearchTransactionsToolArgs,
    ),
)
BY_NAME = {definition.name: definition for definition in DEFINITIONS}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = "".join(ch for ch in value if not unicodedata.category(ch).startswith("C"))
        return value[:160]
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if key not in {"account_id", "category_id", "id", "description_raw"}
        }
    return value


class AssistantToolRegistry:
    def __init__(self, analytics: AnalyticsService, account_id: UUID | None):
        self.analytics, self.account_id = analytics, account_id

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [definition.provider_schema() for definition in DEFINITIONS]

    def execute(self, name: str, raw_arguments: str) -> tuple[str, str]:
        definition = BY_NAME.get(name)
        if definition is None:
            raise ToolProblem("assistant_unknown_tool")
        try:
            values = json.loads(raw_arguments)
            args = definition.arguments.model_validate(values)
        except (json.JSONDecodeError, TypeError, ValidationError) as error:
            raise ToolProblem("assistant_invalid_tool_arguments") from error
        scope = {"account_id": self.account_id}
        if name == "get_spending_summary":
            result = self.analytics.get_spending_summary(PeriodQuery(**args.model_dump(), **scope))
        elif name == "get_category_breakdown":
            result = self.analytics.get_category_breakdown(
                PeriodQuery(**args.model_dump(), **scope)
            )
        elif name == "get_merchant_breakdown":
            result = self.analytics.get_merchant_breakdown(
                MerchantQuery(**args.model_dump(), **scope)
            )
        elif name == "get_monthly_trend":
            result = self.analytics.get_monthly_trend(PeriodQuery(**args.model_dump(), **scope))
        elif name == "compare_periods":
            result = self.analytics.compare_periods(CompareQuery(**args.model_dump(), **scope))
        elif name == "project_month_spending":
            result = self.analytics.project_month_spending(
                ProjectionQuery(**args.model_dump(), **scope)
            )
        elif name == "search_transactions":
            page = self.analytics.list_transactions(
                ExplorerQuery(**args.model_dump(), offset=0, **scope)
            )
            result = {
                "data_scope": page.data_scope,
                "period": page.period.model_dump(mode="json"),
                "has_more": page.has_more,
                "transactions": [
                    {
                        "date": row.transaction_date.isoformat(),
                        "merchant": row.merchant_normalized,
                        "category": None
                        if row.category is None
                        else {"code": row.category.code, "name": row.category.display_name},
                        "amount": format(row.amount, ".2f"),
                        "currency": row.currency,
                        "transaction_type": row.transaction_type.value,
                        "review_status": row.review_status.value,
                    }
                    for row in page.transactions
                ],
            }
        else:  # Explicit mapping above is exhaustive; no dynamic dispatch.
            raise ToolProblem("assistant_unknown_tool")
        payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        return definition.label, json.dumps(
            _clean(payload), ensure_ascii=False, separators=(",", ":")
        )
