"""Pydantic request/response schemas for the ClawCodex API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiEnvelope(BaseModel):
    ok: bool = True
    data: Any = None
    error: ApiError | None = None


class TaskCreateRequest(BaseModel):
    repo_path: str
    prompt: str
    max_debug_attempts: int = 3
    role_config: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    attachment_ids: list[str] = Field(default_factory=list)


class TaskStartRequest(BaseModel):
    test_command: str | None = None


class CheckpointRequest(BaseModel):
    task_id: str
    repo_path: str
    attempt: int = 0


class DiffPreviewRequest(BaseModel):
    task_id: str
    repo_path: str
    file_path: str
    content: str
    mode: Literal["replace", "create"] = "replace"
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=lambda: [".env", ".env.local", ".env.production"])


class DiffContentUpdateRequest(BaseModel):
    content: str


class RollbackRequest(BaseModel):
    task_id: str
    checkpoint_id: str
    mode: Literal["clean", "restore_dirty"] = "clean"


class ProjectScanRequest(BaseModel):
    repo_path: str
    force_refresh: bool = False


class ProjectMemoryRequest(BaseModel):
    repo_path: str
    kind: Literal["style", "fix", "failure", "bug", "note"]
    content: str
    evidence: list[Any] = Field(default_factory=list)


class ModelRoleConfigRequest(BaseModel):
    planner: str
    coder: str
    tester: str = "openai/gpt-4.1-mini"
    debugger: str
    reviewer: str
    budget_usd: float | None = None
    optimize_for: Literal["speed", "quality", "cost", "balanced"] = "balanced"


class ModelRecommendRequest(BaseModel):
    stage: str
    task_type: str | None = None
    risk_level: str = "medium"
    repo_size: str = "medium"
    budget_usd: float | None = None
    optimize_for: Literal["speed", "quality", "cost", "balanced"] = "balanced"


class ModelKeyRequest(BaseModel):
    provider: Literal["openrouter"] = "openrouter"
    api_key: str


class ReadFileRequest(BaseModel):
    repo_path: str
    path: str
    task_id: str = "manual"
    start_line: int | None = None
    end_line: int | None = None


class WriteFileRequest(BaseModel):
    repo_path: str
    path: str
    content: str
    task_id: str
    mode: Literal["replace", "create"] = "replace"
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=lambda: [".env", ".env.local", ".env.production"])


class SearchRepoRequest(BaseModel):
    repo_path: str
    query: str
    kind: Literal["text", "glob", "filename", "symbol", "todo", "recent", "related_tests"] = "text"
    limit: int = 50
    task_id: str = "manual"


class RunCommandRequest(BaseModel):
    repo_path: str
    command: str
    task_id: str = "manual"
    timeout_sec: int = 120
    requires_confirmation: bool = False
    confirmed: bool = False


class RunTestsRequest(BaseModel):
    repo_path: str
    task_id: str
    command: str | None = None
    target: str | None = None
    timeout_sec: int = 120


class GitDiffRequest(BaseModel):
    repo_path: str
    base: str = "HEAD"
    paths: list[str] = Field(default_factory=list)


class AttachmentResponse(BaseModel):
    id: str
    task_id: str | None = None
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    preview_url: str
    analysis_status: Literal["pending", "ready", "failed"] = "ready"
    analysis: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class RulesActiveRequest(BaseModel):
    repo_path: str
    task_id: str | None = None
    enabled_packs: list[str] | None = None
    task_rules: str | None = None
    temporary_instruction: str | None = None


class RulesTaskOverrideRequest(BaseModel):
    task_id: str
    rules: str


class PackImportRequest(BaseModel):
    repo_path: str
    source_dir: str


class DiagnosticsRequest(BaseModel):
    repo_path: str
    task_id: str = "manual"


class DefinitionRequest(BaseModel):
    repo_path: str
    symbol: str
    task_id: str = "manual"


class HoverRequest(BaseModel):
    repo_path: str
    file_path: str
    line: int


class CodeActionRequest(BaseModel):
    diagnostic: dict[str, Any]
