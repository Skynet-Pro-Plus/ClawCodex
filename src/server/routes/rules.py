"""Rules, packs, and self-check routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.engine.orchestrator.store import OrchestratorStore
from src.engine.rules import import_pack, list_packs, resolve_rules
from src.server.dependencies import store
from src.server.schemas import ApiEnvelope, PackImportRequest, RulesActiveRequest, RulesTaskOverrideRequest

router = APIRouter()


@router.post("/active")
def active_rules(payload: RulesActiveRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    resolved = resolve_rules(payload.repo_path, enabled_packs=payload.enabled_packs, task_rules=payload.task_rules, temporary_instruction=payload.temporary_instruction)
    data = resolved.to_dict()
    if payload.task_id:
        db.insert_task_rules(payload.task_id, payload.repo_path, data)
    return ApiEnvelope(data=data)


@router.post("/task-override")
def task_override(payload: RulesTaskOverrideRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    task = db.get_task(payload.task_id)
    if task is None:
        return ApiEnvelope(ok=False, error={"code": "NOT_FOUND", "message": "task not found", "details": {}})
    resolved = resolve_rules(task.repo_path, task_rules=payload.rules)
    data = db.insert_task_rules(task.id, task.repo_path, resolved.to_dict())
    return ApiEnvelope(data=data)


@router.get("/packs")
def packs(repo_path: str | None = None) -> ApiEnvelope:
    return ApiEnvelope(data=list_packs(repo_path))


@router.post("/packs/import")
def import_pack_route(payload: PackImportRequest) -> ApiEnvelope:
    return ApiEnvelope(data=import_pack(payload.source_dir, payload.repo_path))


@router.post("/packs/{pack_id}/apply")
def apply_pack(pack_id: str, repo_path: str) -> ApiEnvelope:
    resolved = resolve_rules(repo_path, enabled_packs=[pack_id])
    return ApiEnvelope(data={"pack_id": pack_id, "rules": resolved.to_dict()})
