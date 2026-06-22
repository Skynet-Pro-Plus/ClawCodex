"""Repository discovery routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.engine.orchestrator.store import OrchestratorStore
from src.server.dependencies import store
from src.server.schemas import ApiEnvelope

router = APIRouter()


@router.get("/recent")
def recent_repos(limit: int = Query(50, ge=1, le=200), db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.list_recent_repos(limit))
