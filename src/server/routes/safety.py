"""Git safety routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.engine.orchestrator.runner import OrchestratorRunner
from src.engine.orchestrator.store import OrchestratorStore
from src.engine.safety.diff_preview import DiffPreviewService
from src.engine.safety.git_checkpoints import GitCheckpointService
from src.engine.safety.rollback import RollbackService
from src.server.dependencies import runner, store
from src.server.routes.tasks import advance_after_all_diffs_resolved
from src.server.schemas import ApiEnvelope, CheckpointRequest, DiffContentUpdateRequest, DiffPreviewRequest, RollbackRequest

router = APIRouter()


@router.post("/checkpoint")
def checkpoint(payload: CheckpointRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    data = GitCheckpointService(db).create_checkpoint(payload.task_id, payload.repo_path, payload.attempt)
    return ApiEnvelope(data=data)


@router.post("/diff-preview")
def diff_preview(payload: DiffPreviewRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    data = DiffPreviewService(db).create_preview(
        payload.task_id,
        payload.repo_path,
        payload.file_path,
        payload.content,
        payload.mode,
        payload.allowed_paths,
        payload.denied_paths,
    )
    return ApiEnvelope(data=data)


@router.post("/diff-preview/{preview_id}/approve")
def approve(
    preview_id: str,
    db: OrchestratorStore = Depends(store),
    orch: OrchestratorRunner = Depends(runner),
) -> ApiEnvelope:
    preview = DiffPreviewService(db).approve(preview_id)
    verification = advance_after_all_diffs_resolved(str(preview["task_id"]), db, orch)
    return ApiEnvelope(data={**preview, "verification": verification})


@router.post("/diff-preview/{preview_id}/reject")
def reject(preview_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=DiffPreviewService(db).reject(preview_id))


@router.post("/diff-preview/{preview_id}/content")
def update_content(preview_id: str, payload: DiffContentUpdateRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=DiffPreviewService(db).update_content(preview_id, payload.content))


@router.post("/diff-preview/{preview_id}/hunks/{hunk_id}/approve")
def approve_hunk(preview_id: str, hunk_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    hunk = DiffPreviewService(db).approve_hunk(hunk_id)
    return ApiEnvelope(data={**hunk, "preview_id": preview_id})


@router.post("/diff-preview/{preview_id}/hunks/{hunk_id}/reject")
def reject_hunk(preview_id: str, hunk_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    hunk = DiffPreviewService(db).reject_hunk(hunk_id)
    return ApiEnvelope(data={**hunk, "preview_id": preview_id})


@router.post("/rollback")
def rollback(payload: RollbackRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=RollbackService(db).rollback(payload.task_id, payload.checkpoint_id, payload.mode))


@router.get("/tasks/{task_id}/checkpoints")
def checkpoints(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.list_checkpoints(task_id))
