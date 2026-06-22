"""Policy defaults for orchestrated tasks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrchestratorPolicy:
    max_debug_attempts: int = 3
    # Review rejections allowed before the task fails instead of bouncing back to CODE forever.
    max_review_attempts: int = 2
    # Hard ceiling on total stage runs per task; no transition combination can exceed it.
    max_stage_runs: int = 30
    test_timeout_sec: int = 120
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=lambda: [".env", ".env.local", ".env.production"])
    allow_budget_override: bool = False
