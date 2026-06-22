"""Heuristics for safe project test command detection."""

from __future__ import annotations

import json
from pathlib import Path


def detect_test_commands(repo_path: str) -> list[dict[str, object]]:
    repo = Path(repo_path)
    commands: list[dict[str, object]] = []
    if (repo / "pytest.ini").is_file() or (repo / "pyproject.toml").is_file():
        commands.append({"command": "python -m pytest -q", "confidence": 0.9, "source": "pytest config"})
    if (repo / "tests").is_dir():
        commands.append({"command": "python -m unittest discover -s tests -v", "confidence": 0.7, "source": "tests directory"})
    package_json = repo / "package.json"
    if package_json.is_file():
        try:
            scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
            if "test" in scripts:
                commands.append({"command": "npm test --silent", "confidence": 0.9, "source": "package.json scripts.test"})
        except Exception:
            pass
    if (repo / "Cargo.toml").is_file():
        commands.append({"command": "cargo test", "confidence": 0.9, "source": "Cargo.toml"})
    return commands
