"""Repository search tools."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path

from ..safety.destructive_ops import SafetyPolicy
from .base import ToolContext

DEFAULT_IGNORES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "target", "dist", "build"}
RG_IGNORE_GLOBS = ["!**/.git/**", "!**/.venv/**", "!**/venv/**", "!**/node_modules/**", "!**/__pycache__/**", "!**/.pytest_cache/**", "!**/target/**", "!**/dist/**", "!**/build/**"]


def _context_from_kwargs(kwargs: dict) -> ToolContext:
    raw = kwargs.pop("context", None)
    if isinstance(raw, ToolContext):
        return raw
    return ToolContext(
        task_id=getattr(raw, "task_id", kwargs.pop("task_id", "manual")),
        repo_path=kwargs.pop("repo_path", "."),
        allowed_paths=getattr(raw, "allowed_paths", kwargs.pop("allowed_paths", [])) or [],
        denied_paths=getattr(raw, "denied_paths", kwargs.pop("denied_paths", [".env", ".env.local", ".env.production"])) or [".env", ".env.local", ".env.production"],
    )


def search_repo(query: str, kind: str = "text", limit: int = 50, **kwargs) -> dict:
    context = _context_from_kwargs(kwargs)
    policy = SafetyPolicy(context.repo_path, context.allowed_paths, context.denied_paths)
    repo = policy.check_read_path(context.repo_path)
    if kind in {"text", "symbol", "todo"}:
        rg_result = _search_with_rg(repo, query, kind, limit)
        if rg_result is not None:
            _record_evidence(context.task_id, repo, query, kind, rg_result["matches"])
            return rg_result
    matches: list[dict] = []
    if kind in {"glob", "filename"}:
        for path in _walk(repo):
            rel = path.relative_to(repo).as_posix()
            if fnmatch.fnmatch(rel, query):
                matches.append({"path": str(path), "relative_path": rel})
                if len(matches) >= limit:
                    break
    elif kind in {"text", "symbol", "todo"}:
        raw_query = r"TODO|FIXME|XXX" if kind == "todo" else query
        pattern = re.compile(raw_query if kind in {"text", "todo"} else rf"\b{re.escape(query)}\b", re.IGNORECASE)
        for path in _walk(repo):
            if not path.is_file() or _looks_binary(path):
                continue
            try:
                for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                    if pattern.search(line):
                        matches.append({"path": str(path), "line": line_no, "text": line.strip()})
                        if len(matches) >= limit:
                            result = {"matches": matches, "count": len(matches), "engine": "python"}
                            _record_evidence(context.task_id, repo, query, kind, matches)
                            return result
            except OSError:
                continue
    elif kind == "recent":
        files = sorted([path for path in _walk(repo) if path.is_file()], key=lambda item: item.stat().st_mtime, reverse=True)
        matches = [{"path": str(path), "relative_path": path.relative_to(repo).as_posix()} for path in files[:limit]]
    elif kind == "related_tests":
        stem = Path(query).stem.replace("test_", "")
        for path in _walk(repo):
            rel = path.relative_to(repo).as_posix()
            if ("test" in rel.lower() or rel.lower().endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))) and stem.lower() in rel.lower():
                matches.append({"path": str(path), "relative_path": rel})
                if len(matches) >= limit:
                    break
    else:
        raise ValueError("kind must be text, glob, filename, symbol, todo, recent, or related_tests")
    _record_evidence(context.task_id, repo, query, kind, matches)
    return {"matches": matches, "count": len(matches), "engine": "python"}


def _search_with_rg(repo: Path, query: str, kind: str, limit: int) -> dict | None:
    pattern = r"TODO|FIXME|XXX" if kind == "todo" else (rf"\b{re.escape(query)}\b" if kind == "symbol" else query)
    try:
        result = subprocess.run(
            [
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                "--no-messages",
                "--max-count",
                "1",
                "-i",
                *RG_IGNORE_GLOBS,
                pattern,
                str(repo),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode not in {0, 1}:
        return None
    matches = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        matches.append({"path": parts[0], "line": int(parts[1]) if parts[1].isdigit() else None, "text": parts[2].strip()})
        if len(matches) >= limit:
            break
    return {"matches": matches, "count": len(matches), "engine": "rg"}


def _record_evidence(task_id: str, repo: Path, query: str, kind: str, matches: list[dict]) -> None:
    if not task_id or task_id == "manual":
        return
    try:
        from ..orchestrator.store import get_store

        get_store().insert_search_evidence(task_id, str(repo), query, kind, matches[:100])
    except Exception:
        pass


def _walk(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORES]
        root_path = Path(root)
        for name in files:
            yield root_path / name


def _looks_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:1024]
    except OSError:
        return True
    return b"\0" in chunk
