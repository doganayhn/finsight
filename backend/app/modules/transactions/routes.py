from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.transactions.classification import (
    ClassificationResponse,
    CorrectionRequest,
    CorrectionService,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.patch("/{transaction_id}/classification", response_model=ClassificationResponse)
def correct_classification(
    transaction_id: UUID,
    body: CorrectionRequest,
    user_id: UserContext,
    session: Annotated[Session, Depends(get_session)],
):
    return CorrectionService(session).correct(user_id, transaction_id, body)
