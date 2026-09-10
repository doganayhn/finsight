from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.integrations.groq.client import GroqProvider
from app.modules.analytics.service import AnalyticsService
from app.modules.assistant.provider import LLMProvider
from app.modules.assistant.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantStatus,
)
from app.modules.assistant.service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


def provider(request: Request) -> LLMProvider | None:
    settings = request.app.state.settings
    key = settings.groq_api_key
    if key is None or not key.get_secret_value().strip():
        return None
    return GroqProvider(
        key.get_secret_value(),
        settings.groq_model,
        settings.assistant_provider_timeout_seconds,
        settings.assistant_max_output_tokens,
    )


def assistant_service(
    request: Request,
    user_id: UserContext,
    session: Annotated[Session, Depends(get_session)],
    llm: Annotated[LLMProvider | None, Depends(provider)],
) -> AssistantService:
    return AssistantService(AnalyticsService(session, user_id), llm, request.app.state.settings)


Service = Annotated[AssistantService, Depends(assistant_service)]


@router.get("/status", response_model=AssistantStatus)
def status(request: Request, user_id: UserContext):
    settings = request.app.state.settings
    key = settings.groq_api_key
    return AssistantStatus(
        enabled=key is not None and bool(key.get_secret_value().strip()), model=settings.groq_model
    )


@router.post("/chat", response_model=AssistantChatResponse)
def chat(payload: AssistantChatRequest, service: Service):
    return service.chat(payload)
