from typing import Any

import groq
from groq import Groq

from app.modules.assistant.provider import ProviderProblem, ProviderReply, ProviderToolCall


class GroqProvider:
    """Groq protocol adapter. It cannot execute tools or access application state."""

    def __init__(self, api_key: str, model: str, timeout: float, max_output_tokens: int):
        self.client = Groq(api_key=api_key, timeout=timeout, max_retries=0)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ProviderReply:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
                max_completion_tokens=self.max_output_tokens,
            )
        except groq.APITimeoutError as error:
            raise ProviderProblem("assistant_provider_timeout", 504) from error
        except groq.RateLimitError as error:
            raise ProviderProblem("assistant_rate_limited", 429) from error
        except groq.APIStatusError as error:
            code = (
                "assistant_provider_unavailable"
                if error.status_code >= 500
                else "assistant_provider_error"
            )
            raise ProviderProblem(code, 503 if error.status_code >= 500 else 502) from error
        except groq.APIConnectionError as error:
            raise ProviderProblem("assistant_provider_unavailable", 503) from error
        except groq.APIError as error:
            raise ProviderProblem("assistant_provider_error", 502) from error
        try:
            message = response.choices[0].message
            calls = [
                ProviderToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=call.function.arguments,
                )
                for call in (message.tool_calls or [])
            ]
            return ProviderReply(content=message.content, tool_calls=calls)
        except (AttributeError, IndexError, TypeError) as error:
            raise ProviderProblem("assistant_malformed_response", 502) from error
