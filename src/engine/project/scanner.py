"""Repository stack detection."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .test_detection import detect_test_commands

IGNORES = {".git", ".claw", ".venv", "venv", "node_modules", "__pycache__", "target", "dist", "build"}
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java"}


class ProjectScanner:
    """Detect languages, frameworks, package managers, commands, and configs."""

    CONFIG_FILES = [
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "next.config.js",
        "Cargo.toml",
        "go.mod",
    ]

    def scan(self, repo_path: str, force_refresh: bool = False) -> dict:
        repo = Path(repo_path).resolve()
        package = self._package_json(repo)
        languages = self._languages(repo, package)
        frameworks = self._frameworks(repo, package)
        return {
            "repo_path": str(repo),
            "languages": languages,
            "frameworks": frameworks,
            "package_manager": self._package_manager(repo),
            "test_commands": detect_test_commands(str(repo)),
            "entry_points": self._entry_points(repo, package),
            "config_files": [name for name in self.CONFIG_FILES if (repo / name).exists()],
            "force_refresh": force_refresh,
        }

    def _languages(self, repo: Path, package: dict) -> list[str]:
        seen = {
            "Python": (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists() or (repo / "setup.py").exists(),
            "JavaScript/Node.js": bool(package) or (repo / "package.json").exists(),
            "TypeScript": (repo / "tsconfig.json").exists(),
            "Rust": (repo / "Cargo.toml").exists(),
            "Go": (repo / "go.mod").exists(),
            "Java": False,
        }

        for path in self._walk(repo):
            suffix = path.suffix.lower()
            if suffix == ".py":
                seen["Python"] = True
            elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
                seen["JavaScript/Node.js"] = True
            elif suffix in {".ts", ".tsx"}:
                seen["TypeScript"] = True
            elif suffix == ".rs":
                seen["Rust"] = True
            elif suffix == ".go":
                seen["Go"] = True
            elif suffix == ".java":
                seen["Java"] = True

        return [name for name, present in seen.items() if present]

    @staticmethod
    def _frameworks(repo: Path, package: dict) -> list[str]:
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if package else {}
        frameworks = []
        if "react" in deps:
            frameworks.append("React")
        if "next" in deps:
            frameworks.append("Next.js")
        if "vite" in deps or (repo / "vite.config.ts").exists():
            frameworks.append("Vite")
        if "@nestjs/core" in deps:
            frameworks.append("NestJS")
        if (repo / "pytest.ini").exists():
            frameworks.append("pytest")
        return frameworks

    @staticmethod
    def _package_manager(repo: Path) -> str | None:
        markers = [
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("package-lock.json", "npm"),
            ("requirements.txt", "pip"),
            ("uv.lock", "uv"),
            ("Cargo.lock", "cargo"),
        ]
        for marker, manager in markers:
            if (repo / marker).exists():
                return manager
        return None

    @staticmethod
    def _entry_points(repo: Path, package: dict) -> list[str]:
        entries = []
        for candidate in ["src/main.py", "src/app.py", "main.py", "app.py", "src/main.ts", "src/index.ts", "src/main.rs"]:
            if (repo / candidate).exists():
                entries.append(candidate)
        main = package.get("main") if package else None
        if main:
            entries.append(main)
        return sorted(set(entries))

    @staticmethod
    def _package_json(repo: Path) -> dict:
        path = repo / "package.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _walk(repo: Path):
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in IGNORES]
            root_path = Path(root)
            for name in files:
                yield root_path / name
