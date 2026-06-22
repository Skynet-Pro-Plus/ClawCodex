"""API dependencies."""

from __future__ import annotations

from src.engine.orchestrator.runner import OrchestratorRunner
from src.engine.orchestrator.store import OrchestratorStore, get_store


def store() -> OrchestratorStore:
    return get_store()


def runner() -> OrchestratorRunner:
    return OrchestratorRunner(store())
