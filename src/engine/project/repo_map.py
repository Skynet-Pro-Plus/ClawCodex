"""Build a compact repository map for planning and review."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..orchestrator.store import get_store
from .scanner import ProjectScanner

IGNORES = {".git", ".claw", ".venv", "venv", "node_modules", "__pycache__", "target", "dist", "build"}
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java", ".json", ".toml", ".md"}


class RepoMapBuilder:
    """Create file/dependency/entry-point metadata from a repository."""

    def __init__(self):
        self.scanner = ProjectScanner()

    def build(self, repo_path: str, force_refresh: bool = False) -> dict:
        repo = Path(repo_path).resolve()
        profile = self.scanner.scan(str(repo), force_refresh)
        files = []
        dependencies = self._dependencies(repo)
        for path in self._walk(repo):
            if path.suffix not in SOURCE_EXTENSIONS:
                continue
            try:
                content = path.read_bytes()
            except OSError:
                continue
            files.append(
                {
                    "path": path.relative_to(repo).as_posix(),
                    "language": _language_for(path),
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        snapshot = hashlib.sha256(str(repo).encode("utf-8"))
        for file in files:
            snapshot.update(file["path"].encode("utf-8"))
            snapshot.update(file["sha256"].encode("utf-8"))
        snapshot_id = snapshot.hexdigest()[:16]
        data = {
            **profile,
            "repo_map_snapshot_id": snapshot_id,
            "files": files,
            "dependencies": dependencies,
            "file_count": len(files),
        }
        get_store().upsert_project_profile(str(repo), data)
        return data

    @staticmethod
    def _walk(repo: Path):
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in IGNORES]
            root_path = Path(root)
            for name in files:
                yield root_path / name

    @staticmethod
    def _dependencies(repo: Path) -> list[dict[str, str]]:
        deps = []
        requirements = repo / "requirements.txt"
        if requirements.is_file():
            for line in requirements.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append({"manager": "pip", "name": line, "source": "requirements.txt"})
        cargo = repo / "Cargo.toml"
        if cargo.is_file():
            deps.append({"manager": "cargo", "name": "Cargo.toml", "source": "Cargo.toml"})
        package = repo / "package.json"
        if package.is_file():
            deps.append({"manager": "npm", "name": "package.json", "source": "package.json"})
        return deps


def _language_for(path: Path) -> str:
    return {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".rs": "Rust",
        ".go": "Go",
        ".java": "Java",
        ".json": "JSON",
        ".toml": "TOML",
        ".md": "Markdown",
    }.get(path.suffix, "Text")
