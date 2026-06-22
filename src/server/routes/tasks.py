"""Task lifecycle routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.engine.attachments.store import AttachmentStore
from src.engine.orchestrator.runner import OrchestratorRunner
from src.engine.orchestrator.store import OrchestratorStore
from src.engine.safety.diff_preview import DiffPreviewService
from src.server.dependencies import runner, store
from src.server.schemas import ApiEnvelope, TaskCreateRequest, TaskStartRequest

router = APIRouter()


@router.get("")
def list_tasks(limit: int = Query(100, ge=1, le=500), db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=[task.to_dict() for task in db.list_tasks(limit)])


@router.post("")
def create_task(payload: TaskCreateRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    task = db.create_task(payload.repo_path, payload.prompt, payload.max_debug_attempts, payload.role_config)
    attachment_store = AttachmentStore(db)
    for attachment_id in payload.attachment_ids:
        attachment_store.link_to_task(task.id, attachment_id)
    return ApiEnvelope(data=task.to_dict())


@router.get("/{task_id}")
def get_task(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    task = db.get_task(task_id)
    if task is None:
        return ApiEnvelope(ok=False, error={"code": "NOT_FOUND", "message": "task not found", "details": {}})
    return ApiEnvelope(data=task.to_dict())


@router.delete("/{task_id}")
def delete_task(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    deleted = db.delete_task(task_id)
    if not deleted:
        return ApiEnvelope(ok=False, error={"code": "NOT_FOUND", "message": "task not found", "details": {"task_id": task_id}})
    return ApiEnvelope(data={"task_id": task_id, "deleted": True})


@router.post("/{task_id}/start")
def start_task(task_id: str, payload: TaskStartRequest, orch: OrchestratorRunner = Depends(runner)) -> ApiEnvelope:
    result = orch.start(task_id)
    if payload.test_command:
        result["test_command"] = payload.test_command
    return ApiEnvelope(data=result)


@router.post("/{task_id}/approve-plan")
def approve_plan(task_id: str, orch: OrchestratorRunner = Depends(runner)) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=orch.approve_plan(task_id))
    except ValueError as exc:
        return ApiEnvelope(ok=False, error={"code": "INVALID_STAGE", "message": str(exc), "details": {"task_id": task_id}})


@router.post("/{task_id}/retry-code")
def retry_code(task_id: str, orch: OrchestratorRunner = Depends(runner)) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=orch.retry_code(task_id))
    except ValueError as exc:
        return ApiEnvelope(ok=False, error={"code": "INVALID_STAGE", "message": str(exc), "details": {"task_id": task_id}})


@router.get("/{task_id}/timeline")
def timeline(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.timeline(task_id))


@router.post("/{task_id}/self-check")
def self_check(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    timeline_data = db.timeline(task_id)
    rules = timeline_data.get("rules") or {}
    searches = timeline_data.get("search_evidence") or []
    tests = timeline_data.get("test_runs") or []
    diagnostics = timeline_data.get("diagnostics") or []
    diffs = timeline_data.get("diff_previews") or []
    output = {
        "rules_loaded": rules.get("summary", []),
        "assumptions_made": ["Mission should follow active rule priority order.", "High-risk work pauses for approval."],
        "files_inspected": sorted({match.get("path", "") for evidence in searches for match in evidence.get("results", []) if match.get("path")})[:50],
        "tests_planned": [test.get("command") for test in tests if test.get("command")] or ["No tests run yet."],
        "risks_found": [f"{diff.get('risk_level', 'Low')}: {diff.get('approval_reason', '')}" for diff in diffs],
        "missing_context": [] if searches else ["No search evidence has been recorded yet."],
        "next_action": "Review pending approvals." if any(diff.get("status") == "pending" for diff in diffs) else "Continue mission flow.",
        "diagnostics": diagnostics,
    }
    db.record_tool_call(task_id, "self-check", "passed", {"task_id": task_id}, output)
    return ApiEnvelope(data=output)


@router.get("/{task_id}/attachments")
def attachments(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=[item.to_dict() for item in AttachmentStore(db).list_for_task(task_id)])


@router.post("/{task_id}/attachments/{attachment_id}")
def link_attachment(task_id: str, attachment_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=AttachmentStore(db).link_to_task(task_id, attachment_id).to_dict())


@router.get("/{task_id}/diffs")
def diffs(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.list_diff_previews(task_id))


@router.post("/{task_id}/diffs/approve-all")
def approve_all_diffs(
    task_id: str,
    db: OrchestratorStore = Depends(store),
    orch: OrchestratorRunner = Depends(runner),
) -> ApiEnvelope:
    previews = DiffPreviewService(db).approve_all(task_id)
    task = db.get_task(task_id)
    result = orch.after_code(task_id) if task is not None else None
    return ApiEnvelope(data={"diffs": previews, "verification": result})


def advance_after_all_diffs_resolved(task_id: str, db: OrchestratorStore, orch: OrchestratorRunner) -> dict | None:
    pending = [diff for diff in db.list_diff_previews(task_id) if diff["status"] == "pending"]
    task = db.get_task(task_id)
    if pending or task is None or task.stage != "CODE":
        return None
    return orch.after_code(task_id)


@router.post("/{task_id}/diffs/reject-all")
def reject_all_diffs(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    previews = DiffPreviewService(db).reject_all(task_id)
    return ApiEnvelope(data={"diffs": previews})


@router.get("/{task_id}/tests")
def tests(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.timeline(task_id)["test_runs"])


@router.get("/{task_id}/costs")
def costs(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    timeline = db.timeline(task_id)
    models = [run["model"] for run in timeline["stage_runs"] if run.get("model")]
    return ApiEnvelope(data={"task_id": task_id, "models_used": models, "stage_count": len(timeline["stage_runs"])})


@router.post("/{task_id}/pause")
def pause(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    db.record_tool_call(task_id, "pause", "paused", {}, {"message": "Task pause requested"})
    return ApiEnvelope(data={"task_id": task_id, "paused": True})


@router.post("/{task_id}/resume")
def resume(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    db.record_tool_call(task_id, "resume", "resumed", {}, {"message": "Task resume requested"})
    return ApiEnvelope(data={"task_id": task_id, "resumed": True})


@router.post("/{task_id}/cancel")
def cancel(task_id: str, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    task = db.update_task_stage(task_id, "FAILED")
    return ApiEnvelope(data=task.to_dict())
