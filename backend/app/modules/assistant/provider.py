from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ProviderReply:
    content: str | None = None
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ProviderReply:
        """Return one provider-neutral assistant turn."""


class ProviderProblem(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)
