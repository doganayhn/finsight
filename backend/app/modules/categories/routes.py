from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.categories.repository import CategoryRepository

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    display_name: str
    parent_id: UUID | None


@router.get("", response_model=list[CategoryResponse])
def catalog(user_id: UserContext, session: Annotated[Session, Depends(get_session)]):
    return CategoryRepository(session).catalog()
