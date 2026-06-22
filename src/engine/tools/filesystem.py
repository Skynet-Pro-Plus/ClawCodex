"""File read/write tools with path guards and diff previews."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..safety.destructive_ops import SafetyPolicy
from ..safety.diff_preview import DiffPreviewService
from .base import ToolContext


def _context_from_kwargs(kwargs: dict) -> ToolContext:
    raw = kwargs.pop("context", None)
    if isinstance(raw, ToolContext):
        return raw
    return ToolContext(
        task_id=getattr(raw, "task_id", kwargs.pop("task_id", "manual")),
        repo_path=kwargs.pop("repo_path", "."),
        allowed_paths=getattr(raw, "allowed_paths", kwargs.pop("allowed_paths", [])) or [],
        denied_paths=getattr(raw, "denied_paths", kwargs.pop("denied_paths", [".env", ".env.local", ".env.production"])) or [".env", ".env.local", ".env.production"],
        dry_run=kwargs.pop("dry_run", False),
        confirmed=getattr(raw, "elevated_permissions", kwargs.pop("confirmed", False)),
    )


def read_file(path: str, start_line: int | None = None, end_line: int | None = None, **kwargs) -> dict:
    context = _context_from_kwargs(kwargs)
    policy = SafetyPolicy(context.repo_path, context.allowed_paths, context.denied_paths)
    target = policy.check_read_path(path)
    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()
    if start_line is not None or end_line is not None:
        start = max((start_line or 1) - 1, 0)
        end = end_line if end_line is not None else len(lines)
        selected = "\n".join(lines[start:end])
        if selected and content.endswith("\n"):
            selected += "\n"
        content = selected
    return {
        "path": str(target),
        "content": content,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "line_count": len(content.splitlines()),
    }


def write_file(path: str, content: str, mode: str = "replace", **kwargs) -> dict:
    context = _context_from_kwargs(kwargs)
    service = DiffPreviewService()
    preview = service.create_preview(
        task_id=context.task_id,
        repo_path=context.repo_path,
        file_path=path,
        content=content,
        mode=mode,
        allowed_paths=context.allowed_paths,
        denied_paths=context.denied_paths,
    )
    if context.dry_run:
        return preview
    return preview


def atomic_apply_preview(preview_id: str) -> dict:
    return DiffPreviewService().apply(preview_id)


def relative_to_repo(repo_path: str, path: str | Path) -> str:
    target = Path(path).resolve()
    try:
        return str(target.relative_to(Path(repo_path).resolve()))
    except ValueError:
        return str(target)
