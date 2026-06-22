"""Git checkpoint creation before mutating CODE stages."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from ..orchestrator.store import OrchestratorStore, get_store, utc_now


class GitCheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be created."""


class GitCheckpointService:
    """Create durable git refs and dirty-state patches for task rollback."""

    def __init__(self, store: OrchestratorStore | None = None):
        self.store = store or get_store()

    def create_checkpoint(self, task_id: str, repo_path: str, attempt: int = 0) -> dict[str, str | None]:
        repo = Path(repo_path).resolve()
        head_sha = self._git(repo, ["rev-parse", "HEAD"]).strip()
        checkpoint_id = uuid.uuid4().hex
        checkpoint_ref = f"refs/claw/checkpoints/{task_id}/{attempt}-{checkpoint_id[:8]}"
        self._git(repo, ["update-ref", checkpoint_ref, head_sha])
        dirty_patch_path = self._write_dirty_patch(repo, task_id, checkpoint_id)
        return self.store.insert_checkpoint(
            {
                "id": checkpoint_id,
                "task_id": task_id,
                "repo_path": str(repo),
                "head_sha": head_sha,
                "checkpoint_ref": checkpoint_ref,
                "dirty_patch_path": str(dirty_patch_path) if dirty_patch_path else None,
                "created_at": utc_now(),
            }
        )

    def _write_dirty_patch(self, repo: Path, task_id: str, checkpoint_id: str) -> Path | None:
        diff = self._git(repo, ["diff", "--binary"], allow_empty=True)
        if not diff.strip():
            return None
        patch_dir = repo / ".claw" / "checkpoints" / task_id
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch_path = patch_dir / f"{checkpoint_id}.patch"
        patch_path.write_text(diff, encoding="utf-8")
        return patch_path

    @staticmethod
    def _git(repo: Path, args: list[str], allow_empty: bool = False) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 and not allow_empty:
            raise GitCheckpointError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout
