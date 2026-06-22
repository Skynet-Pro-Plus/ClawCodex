"""Attachment upload and preview routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.engine.attachments.store import AttachmentStore
from src.engine.orchestrator.store import OrchestratorStore
from src.server.dependencies import store
from src.server.schemas import ApiEnvelope

router = APIRouter()


@router.post("")
def upload_attachment(
    file: UploadFile = File(...),
    task_id: str | None = Form(default=None),
    db: OrchestratorStore = Depends(store),
) -> ApiEnvelope:
    saved = AttachmentStore(db).save(file.file, file.filename or "attachment", file.content_type or "application/octet-stream", task_id)
    return ApiEnvelope(data=saved.to_dict())


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    record = AttachmentStore(db).get(attachment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    return ApiEnvelope(data=record.to_dict())


@router.get("/{attachment_id}/content")
def attachment_content(attachment_id: str, db: OrchestratorStore = Depends(store)) -> FileResponse:
    record = AttachmentStore(db).get(attachment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    path = Path(record.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="attachment content missing")
    return FileResponse(path, media_type=record.content_type, filename=record.filename)


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    deleted = AttachmentStore(db).delete(attachment_id)
    return ApiEnvelope(data={"deleted": deleted})
