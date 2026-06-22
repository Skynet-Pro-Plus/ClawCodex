"""LSP-style code intelligence routes."""

from __future__ import annotations

from fastapi import APIRouter

from src.engine.lsp import code_actions, definition, diagnostics, hover, references
from src.server.schemas import ApiEnvelope, CodeActionRequest, DefinitionRequest, DiagnosticsRequest, HoverRequest

router = APIRouter()


@router.post("/diagnostics")
def diagnostics_route(payload: DiagnosticsRequest) -> ApiEnvelope:
    return ApiEnvelope(data=diagnostics(payload.repo_path, payload.task_id))


@router.post("/definition")
def definition_route(payload: DefinitionRequest) -> ApiEnvelope:
    return ApiEnvelope(data=definition(payload.repo_path, payload.symbol, payload.task_id))


@router.post("/references")
def references_route(payload: DefinitionRequest) -> ApiEnvelope:
    return ApiEnvelope(data=references(payload.repo_path, payload.symbol, payload.task_id))


@router.post("/hover")
def hover_route(payload: HoverRequest) -> ApiEnvelope:
    return ApiEnvelope(data=hover(payload.repo_path, payload.file_path, payload.line))


@router.post("/code-actions")
def code_actions_route(payload: CodeActionRequest) -> ApiEnvelope:
    return ApiEnvelope(data=code_actions(payload.diagnostic))
