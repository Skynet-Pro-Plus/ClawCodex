"""Persistent project memory for style, fixes, failures, bugs, and notes."""

from __future__ import annotations

from ..orchestrator.store import OrchestratorStore, get_store


class ProjectMemoryStore:
    def __init__(self, store: OrchestratorStore | None = None):
        self.store = store or get_store()

    def add(self, repo_path: str, kind: str, content: str, evidence: list | None = None) -> dict:
        if kind not in {"style", "fix", "failure", "bug", "note"}:
            raise ValueError("kind must be one of style, fix, failure, bug, note")
        return self.store.insert_project_memory(repo_path, kind, content, evidence or [])

    def list(self, repo_path: str) -> list[dict]:
        return self.store.list_project_memory(repo_path)
