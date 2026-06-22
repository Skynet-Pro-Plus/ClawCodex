"""Project awareness routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.engine.orchestrator.store import OrchestratorStore
from src.engine.project.memory import ProjectMemoryStore
from src.engine.project.repo_map import RepoMapBuilder
from src.server.dependencies import store
from src.server.schemas import ApiEnvelope, ProjectMemoryRequest, ProjectScanRequest

router = APIRouter()


@router.post("/scan")
def scan(payload: ProjectScanRequest) -> ApiEnvelope:
    return ApiEnvelope(data=RepoMapBuilder().build(payload.repo_path, payload.force_refresh))


@router.get("/profile")
def profile(repo_path: str = Query(...), db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    data = db.get_project_profile(repo_path)
    return ApiEnvelope(data=data)


@router.get("/memory")
def memory(repo_path: str = Query(...), db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=ProjectMemoryStore(db).list(repo_path))


@router.post("/memory")
def add_memory(payload: ProjectMemoryRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    data = ProjectMemoryStore(db).add(payload.repo_path, payload.kind, payload.content, payload.evidence)
    return ApiEnvelope(data=data)
