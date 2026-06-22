"""Local rule pack catalog."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

PACK_FILES = ("README.md", "rules.md", "examples.md", "forbidden_patterns.md", "test_commands.md")


def pack_roots(repo_path: str | None = None) -> list[Path]:
    roots = []
    if repo_path:
        repo = Path(repo_path).resolve()
        roots.extend([repo / "clawcodex-packs", repo.parent / "clawcodex-packs"])
    roots.append(Path.cwd() / "clawcodex-packs")
    return roots


def list_packs(repo_path: str | None = None) -> list[dict[str, Any]]:
    seen = set()
    packs = []
    for root in pack_roots(repo_path):
        if not root.is_dir():
            continue
        for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if pack_dir.name in seen:
                continue
            seen.add(pack_dir.name)
            packs.append(_pack_info(pack_dir))
    return packs


def import_pack(source_dir: str, repo_path: str) -> dict[str, Any]:
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"pack source not found: {source}")
    target_root = Path(repo_path).resolve() / "clawcodex-packs"
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / source.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return _pack_info(target)


def _pack_info(pack_dir: Path) -> dict[str, Any]:
    meta_path = pack_dir / "pack.json"
    metadata = {}
    if meta_path.is_file():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
    return {
        "id": pack_dir.name,
        "name": metadata.get("name", pack_dir.name.replace("-", " ").title()),
        "path": str(pack_dir),
        "files": {name: (pack_dir / name).is_file() for name in PACK_FILES},
        "description": metadata.get("description", _read_first_line(pack_dir / "README.md")),
    }


def _read_first_line(path: Path) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip() and not line.strip().startswith("#"):
            return line.strip()
    return ""
