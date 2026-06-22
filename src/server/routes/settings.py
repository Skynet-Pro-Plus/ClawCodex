"""Local settings routes."""

from __future__ import annotations

from src.engine.coding.openrouter_client import ModelNotConfigured, ModelResponseError, validate_openrouter_key
from src.engine.settings.local_config import clear_model_key, model_key_status, save_model_key
from src.server.schemas import ApiEnvelope, ModelKeyRequest

from fastapi import APIRouter

router = APIRouter()


@router.get("/model-key/status")
def get_model_key_status() -> ApiEnvelope:
    return ApiEnvelope(data=model_key_status("openrouter"))


@router.post("/model-key")
def post_model_key(payload: ModelKeyRequest) -> ApiEnvelope:
    try:
        model_count = validate_openrouter_key(payload.api_key)
        status = save_model_key(payload.api_key, payload.provider)
        return ApiEnvelope(data={**status, "validated": True, "model_count": model_count})
    except ModelNotConfigured as exc:
        return ApiEnvelope(ok=False, error={"code": "INVALID_MODEL_KEY", "message": str(exc), "details": {}})
    except ModelResponseError as exc:
        return ApiEnvelope(ok=False, error={"code": "MODEL_KEY_VALIDATION_FAILED", "message": str(exc), "details": {}})
    except ValueError as exc:
        return ApiEnvelope(ok=False, error={"code": "INVALID_MODEL_KEY", "message": str(exc), "details": {}})


@router.delete("/model-key")
def delete_model_key() -> ApiEnvelope:
    return ApiEnvelope(data=clear_model_key("openrouter"))
