"""Model role configuration and recommendation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.engine.coding.openrouter_client import ModelResponseError, list_openrouter_models
from src.engine.orchestrator.store import OrchestratorStore
from src.engine.routing.model_selector import MODELS
from src.engine.routing.model_selector import ModelSelector
from src.server.dependencies import store
from src.server.schemas import ApiEnvelope, ModelRecommendRequest, ModelRoleConfigRequest

router = APIRouter()

DEFAULT_ROLE_CONFIG = {
    "planner": "anthropic/claude-opus-4.1",
    "coder": "openai/gpt-4.1-mini",
    "tester": "openai/gpt-4.1-mini",
    "debugger": "anthropic/claude-sonnet-4",
    "reviewer": "anthropic/claude-opus-4.1",
    "budget_usd": None,
    "optimize_for": "balanced",
}


@router.get("/roles")
def get_roles(db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    stored = db.get_model_role_config("default") or {}
    return ApiEnvelope(data={**DEFAULT_ROLE_CONFIG, **stored})


@router.put("/roles")
def put_roles(payload: ModelRoleConfigRequest, db: OrchestratorStore = Depends(store)) -> ApiEnvelope:
    return ApiEnvelope(data=db.set_model_role_config("default", payload.dict()))


@router.get("/openrouter")
def openrouter_models() -> ApiEnvelope:
    try:
        models = list_openrouter_models()
        source = "openrouter"
    except ModelResponseError:
        models = [
            {"id": model_id, "name": model_id, "context_length": info.get("context_window"), "pricing": {}}
            for model_id, info in MODELS.items()
            if info.get("provider") == "openrouter"
        ]
        source = "fallback"
    models.sort(key=lambda item: (str(item.get("company") or item["id"].split("/", 1)[0]).lower(), item["id"].lower()))
    return ApiEnvelope(data={"source": source, "models": models})


@router.post("/recommend")
def recommend(payload: ModelRecommendRequest) -> ApiEnvelope:
    selector = ModelSelector(prefer_cheap=payload.optimize_for == "cost")
    result = selector.recommend(
        stage=payload.stage,
        task_type=payload.task_type,
        risk_level=payload.risk_level,
        repo_size=payload.repo_size,
    )
    data = result.to_dict()
    data["optimize_for"] = payload.optimize_for
    data["budget_usd"] = payload.budget_usd
    return ApiEnvelope(data=data)
