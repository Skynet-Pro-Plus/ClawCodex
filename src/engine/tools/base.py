"""Shared contracts for orchestrator tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolContext:
    task_id: str
    repo_path: str
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=lambda: [".env", ".env.local", ".env.production"])
    dry_run: bool = False
    confirmed: bool = False


class Tool(Protocol):
    name: str

    def validate(self, payload: dict, context: ToolContext) -> None:
        ...

    def execute(self, payload: dict, context: ToolContext) -> dict:
        ...
