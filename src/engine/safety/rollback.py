"""One-call rollback to a stored git checkpoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..orchestrator.store import OrchestratorStore, get_store


class RollbackError(RuntimeError):
    """Raised when rollback cannot complete cleanly."""


class RollbackService:
    """Restore tracked files to a task checkpoint and optionally restore dirty state."""

    def __init__(self, store: OrchestratorStore | None = None):
        self.store = store or get_store()

    def rollback(self, task_id: str, checkpoint_id: str, mode: str = "clean") -> dict[str, object]:
        if mode not in {"clean", "restore_dirty"}:
            raise ValueError("mode must be 'clean' or 'restore_dirty'")
        checkpoint = self.store.get_checkpoint(checkpoint_id)
        if checkpoint is None or checkpoint["task_id"] != task_id:
            raise KeyError(f"checkpoint not found for task: {checkpoint_id}")
        repo = Path(checkpoint["repo_path"]).resolve()
        self._git(repo, ["restore", "--source", checkpoint["checkpoint_ref"], "--staged", "--worktree", "."])
        if mode == "restore_dirty" and checkpoint.get("dirty_patch_path"):
            patch = Path(checkpoint["dirty_patch_path"])
            if patch.is_file():
                self._git(repo, ["apply", str(patch)])
        status = self._git(repo, ["status", "--short"], allow_empty=True)
        return {
            "task_id": task_id,
            "checkpoint_id": checkpoint_id,
            "mode": mode,
            "repo_path": str(repo),
            "status": status.splitlines(),
        }

    @staticmethod
    def _git(repo: Path, args: list[str], allow_empty: bool = False) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 and not allow_empty:
            raise RollbackError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout
