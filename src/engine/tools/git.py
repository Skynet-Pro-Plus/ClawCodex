"""Git inspection tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .base import ToolContext


def git_diff(base: str = "HEAD", paths: list[str] | None = None, **kwargs) -> dict:
    raw = kwargs.pop("context", None)
    context = raw if isinstance(raw, ToolContext) else ToolContext(
        task_id=getattr(raw, "task_id", kwargs.pop("task_id", "manual")),
        repo_path=kwargs.pop("repo_path", "."),
    )
    repo = Path(context.repo_path).resolve()
    args = ["git", "diff", base, "--"]
    args.extend(paths or [])
    result = subprocess.run(args, cwd=repo, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    summary = subprocess.run(
        ["git", "diff", "--stat", base, "--", *(paths or [])],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "base": base,
        "paths": paths or [],
        "summary": summary.stdout,
        "files": _changed_files(repo, base, paths or []),
        "unified_diff": result.stdout,
    }


def _changed_files(repo: Path, base: str, paths: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, "--", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]
