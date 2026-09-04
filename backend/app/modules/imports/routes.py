from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import UserContext
from app.db.session import get_session
from app.modules.imports.api_schemas import ConfirmRequest, ImportPreview
from app.modules.imports.service import ImportService

router = APIRouter(prefix="/imports", tags=["imports"])


def import_service(request: Request, session: Annotated[Session, Depends(get_session)]):
    return ImportService(session, request.app.state.settings)


Service = Annotated[ImportService, Depends(import_service)]


@router.post("/preview", response_model=ImportPreview, status_code=201)
async def preview(
    user_id: UserContext,
    service: Service,
    account_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
):
    try:
        # The ASGI body limit bounds multipart parsing/spooling, including chunked requests.
        # A separate limit here applies to the file itself, not just Content-Length.
        data = await file.read(service.settings.max_upload_bytes + 1)
        return await run_in_threadpool(
            service.preview, user_id, account_id, data, file.filename or "", file.content_type or ""
        )
    finally:
        await file.close()


@router.get("/{batch_id}", response_model=ImportPreview)
def get_preview(batch_id: UUID, user_id: UserContext, service: Service):
    return service.get(user_id, batch_id)


@router.post("/{batch_id}/confirm", response_model=ImportPreview)
def confirm(batch_id: UUID, body: ConfirmRequest, user_id: UserContext, service: Service):
    return service.confirm(user_id, batch_id, body.decisions)
