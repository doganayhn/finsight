from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.modules.imports.errors import ImportProblem


def development_user(request: Request, x_dev_user_id: Annotated[UUID, Header()]) -> UUID:
    """Caller-asserted development identity, NOT authentication. Never enable for hosted use."""
    if request.app.state.settings.app_env != "development":
        raise ImportProblem("development_context_disabled", 403)
    return x_dev_user_id


UserContext = Annotated[UUID, Depends(development_user)]
