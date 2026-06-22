"""Fail-closed guards for paths and shell commands."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class SafetyViolation(PermissionError):
    """Raised when a path or command violates the safety policy."""


_DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+(-[^\s]*r[^\s]*f|-f[^\s]*r)\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/(s|q)\b", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b.*(?:^|\s)-Recurse\b", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\b", re.IGNORECASE),
    re.compile(r"\brmdir\s+/(s|q)\b", re.IGNORECASE),
]

_INSTALL_OR_NETWORK_PATTERNS = [
    re.compile(r"\b(npm|pnpm|yarn)\s+(install|add)\b", re.IGNORECASE),
    re.compile(r"\b(pip|pip3|python\s+-m\s+pip)\s+install\b", re.IGNORECASE),
    re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr)\b", re.IGNORECASE),
]


@dataclass
class SafetyPolicy:
    """Conservative local guardrails for tools and orchestrated writes."""

    repo_path: str
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=lambda: [".env", ".env.local", ".env.production"])
    require_confirmation_patterns: list[re.Pattern[str]] = field(default_factory=lambda: list(_INSTALL_OR_NETWORK_PATTERNS))
    max_delete_files: int = 25
    max_delete_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_path).resolve()
        if not self.allowed_paths:
            self.allowed_paths = [str(self.repo_root)]

    def resolve_path(self, path: str | Path) -> Path:
        raw = Path(path)
        candidate = raw if raw.is_absolute() else self.repo_root / raw
        resolved = candidate.resolve()
        if not self._under_any(resolved, [Path(p).resolve() for p in self.allowed_paths]):
            raise SafetyViolation(f"path outside allowed folders: {resolved}")
        if self._matches_denied(resolved):
            raise SafetyViolation(f"path is protected by denied_paths: {resolved}")
        return resolved

    def check_read_path(self, path: str | Path) -> Path:
        return self.resolve_path(path)

    def check_write_path(self, path: str | Path) -> Path:
        return self.resolve_path(path)

    def check_delete_path(self, path: str | Path) -> Path:
        resolved = self.resolve_path(path)
        if resolved.is_dir():
            file_count = 0
            total_bytes = 0
            for child in resolved.rglob("*"):
                if child.is_file():
                    file_count += 1
                    total_bytes += child.stat().st_size
                if file_count > self.max_delete_files or total_bytes > self.max_delete_bytes:
                    raise SafetyViolation(f"refusing large folder delete: {resolved}")
        return resolved

    def check_command(self, command: str, confirmed: bool = False) -> None:
        for pattern in _DANGEROUS_COMMAND_PATTERNS:
            if pattern.search(command):
                raise SafetyViolation(f"blocked destructive command: {command}")
        if not confirmed:
            for pattern in self.require_confirmation_patterns:
                if pattern.search(command):
                    raise SafetyViolation(f"command requires confirmation: {command}")

    def _matches_denied(self, path: Path) -> bool:
        normalized = path.as_posix().lower()
        for denied in self.denied_paths:
            denied_path = Path(denied)
            if denied_path.is_absolute():
                try:
                    if path == denied_path.resolve() or denied_path.resolve() in path.parents:
                        return True
                except OSError:
                    continue
            else:
                parts = [part.lower() for part in path.parts]
                if denied.lower() in parts or normalized.endswith("/" + denied.lower()):
                    return True
        return False

    @staticmethod
    def _under_any(path: Path, roots: list[Path]) -> bool:
        return any(path == root or root in path.parents for root in roots)
