"""Guarded subprocess execution."""

from __future__ import annotations

import subprocess
import time

from ..safety.destructive_ops import SafetyPolicy
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
        confirmed=getattr(raw, "elevated_permissions", kwargs.pop("confirmed", False)),
    )


def run_command(command: str, timeout_sec: int = 120, requires_confirmation: bool = False, **kwargs) -> dict:
    context = _context_from_kwargs(kwargs)
    policy = SafetyPolicy(context.repo_path, context.allowed_paths, context.denied_paths)
    policy.check_command(command, confirmed=context.confirmed and not requires_confirmation)
    start = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=context.repo_path,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        status = "passed" if result.returncode == 0 else "failed"
        return {
            "command": command,
            "status": status,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "timeout",
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_ms": int(timeout_sec * 1000),
        }
