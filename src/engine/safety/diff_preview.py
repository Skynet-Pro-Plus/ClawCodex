"""Diff preview generation and approved atomic writes."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from ..orchestrator.store import OrchestratorStore, get_store
from .destructive_ops import SafetyPolicy
from .risk import assess_file_change


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DiffPreviewService:
    """Create previews for proposed writes and apply approved previews."""

    def __init__(self, store: OrchestratorStore | None = None):
        self.store = store or get_store()

    def create_preview(
        self,
        task_id: str,
        repo_path: str,
        file_path: str,
        content: str,
        mode: str = "replace",
        allowed_paths: list[str] | None = None,
        denied_paths: list[str] | None = None,
    ) -> dict[str, str | None]:
        policy = SafetyPolicy(repo_path, allowed_paths=allowed_paths or [], denied_paths=denied_paths or None or [".env"])
        target = policy.check_write_path(file_path)
        if mode == "create" and target.exists():
            raise FileExistsError(f"file already exists: {target}")
        if mode not in {"create", "replace"}:
            raise ValueError("mode must be 'create' or 'replace'")
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        before_hash = sha256_text(before) if target.exists() else None
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=str(target),
                tofile=str(target),
            )
        )
        risk = assess_file_change(str(target), diff)
        preview_id = None
        preview = self.store.insert_diff_preview(
            {
                "task_id": task_id,
                "repo_path": str(Path(repo_path).resolve()),
                "file_path": str(target),
                "before_sha256": before_hash,
                "after_sha256": sha256_text(content),
                "proposed_content": content,
                "unified_diff": diff,
                "status": "pending",
                "risk_level": risk["risk_level"],
                "approval_reason": risk["approval_reason"],
                "patch_summary": risk["patch_summary"],
            }
        )
        preview_id = str(preview["id"])
        for hunk in _split_hunks(diff):
            self.store.insert_diff_hunk(
                {
                    "preview_id": preview_id,
                    "task_id": task_id,
                    "file_path": str(target),
                    "header": hunk["header"],
                    "body": hunk["body"],
                    "risk_level": risk["risk_level"],
                }
            )
        return preview

    def approve(self, preview_id: str, apply: bool = True) -> dict[str, str | None]:
        preview = self.store.update_diff_status(preview_id, "approved")
        if apply:
            self.apply(preview_id)
            preview = self.store.get_diff_preview(preview_id) or preview
        return preview

    def reject(self, preview_id: str) -> dict[str, str | None]:
        return self.store.update_diff_status(preview_id, "rejected")

    def approve_hunk(self, hunk_id: str) -> dict[str, str | None]:
        return self.store.update_diff_hunk_status(hunk_id, "approved")

    def reject_hunk(self, hunk_id: str) -> dict[str, str | None]:
        return self.store.update_diff_hunk_status(hunk_id, "rejected")

    def update_content(self, preview_id: str, content: str) -> dict[str, str | None]:
        preview = self.store.get_diff_preview(preview_id)
        if preview is None:
            raise KeyError(f"diff preview not found: {preview_id}")
        target = Path(preview["file_path"])
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=str(target),
                tofile=str(target),
            )
        )
        risk = assess_file_change(str(target), diff)
        return self.store.update_diff_content(preview_id, content, sha256_text(content), diff, risk)

    def approve_all(self, task_id: str) -> list[dict[str, str | None]]:
        applied = []
        for preview in self.store.list_diff_previews(task_id):
            if preview["status"] in {"pending", "approved"}:
                applied.append(self.approve(preview["id"]))
        return applied

    def reject_all(self, task_id: str) -> list[dict[str, str | None]]:
        rejected = []
        for preview in self.store.list_diff_previews(task_id):
            if preview["status"] in {"pending", "approved"}:
                rejected.append(self.reject(preview["id"]))
        return rejected

    def apply(self, preview_id: str) -> dict[str, str | None]:
        preview = self.store.get_diff_preview(preview_id)
        if preview is None:
            raise KeyError(f"diff preview not found: {preview_id}")
        if preview["status"] not in {"approved", "pending"}:
            raise ValueError(f"cannot apply preview with status {preview['status']}")
        target = Path(preview["file_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        existing_hash = sha256_text(existing) if target.exists() else None
        if preview.get("before_sha256") != existing_hash:
            raise RuntimeError("file changed since diff preview was created")
        target.write_text(preview["proposed_content"], encoding="utf-8")
        return self.store.update_diff_status(preview_id, "applied")


def _split_hunks(diff: str) -> list[dict[str, str]]:
    hunks: list[dict[str, str]] = []
    current_header = ""
    current_lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith("@@"):
            if current_header or current_lines:
                hunks.append({"header": current_header or "file header", "body": "\n".join(current_lines)})
            current_header = line
            current_lines = []
        elif current_header:
            current_lines.append(line)
    if current_header or current_lines:
        hunks.append({"header": current_header or "file header", "body": "\n".join(current_lines)})
    if not hunks and diff:
        hunks.append({"header": "file change", "body": diff})
    return hunks
