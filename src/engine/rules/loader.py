"""Load global, workspace, and pack rule files."""

from __future__ import annotations

import os
from pathlib import Path

from .models import RuleSource, summarize_rule_text

RULE_FILENAMES = ("CLAWRULES.md", "CLAWCODEX.md", ".clawcodexrules", ".windsurfrules", "global_rules.md")


def load_rule_sources(repo_path: str, enabled_packs: list[str] | None = None) -> list[RuleSource]:
    """When ``enabled_packs`` is None, all pack directories are included. When it is an empty list, no pack rules are loaded (workspace + system rules still apply)."""
    repo = Path(repo_path).resolve()
    pack_filter: set[str] | None
    if enabled_packs is None:
        pack_filter = None
    else:
        pack_filter = set(enabled_packs)
    sources: list[RuleSource] = []
    sources.extend(_system_rules())
    sources.extend(_global_rules())
    sources.extend(_workspace_rules(repo))
    sources.extend(_pack_rules(repo, pack_filter))
    return sorted(sources, key=lambda item: item.priority)


def _system_rules() -> list[RuleSource]:
    content = "\n".join(
        [
            "Never edit denied files without explicit approval.",
            "Create a checkpoint before meaningful patches.",
            "Prefer test evidence before marking a mission complete.",
            "Pause for high-risk shell, auth, config, migration, or deletion actions.",
        ]
    )
    return [RuleSource(id="system-safety", scope="system", path="system://safety", priority=10, content=content, summary="Built-in safety and verification rules")]


def _global_rules() -> list[RuleSource]:
    config_dir = Path(os.environ.get("CLAWCODEX_CONFIG_DIR", Path.home() / ".clawcodex"))
    paths = [config_dir / "global_rules.md", config_dir / "CLAWRULES.md"]
    return [_source("global", path, 20) for path in paths if path.is_file()]


def _workspace_rules(repo: Path) -> list[RuleSource]:
    sources = []
    for name in RULE_FILENAMES:
        path = repo / name
        if path.is_file():
            sources.append(_source("workspace", path, 30))
    rules_dir = repo / ".clawcodex" / "rules"
    if rules_dir.is_dir():
        for path in sorted(rules_dir.glob("*.md")):
            sources.append(_source("workspace", path, 31))
    return sources


def _pack_rules(repo: Path, pack_filter: set[str] | None) -> list[RuleSource]:
    roots = [repo / "clawcodex-packs", repo.parent / "clawcodex-packs", Path.cwd() / "clawcodex-packs"]
    sources = []
    for root in roots:
        if not root.is_dir():
            continue
        for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if pack_filter is not None and pack_dir.name not in pack_filter:
                continue
            rules = pack_dir / "rules.md"
            if rules.is_file():
                sources.append(_source("pack", rules, 40, source_id=f"pack:{pack_dir.name}"))
    return sources


def _source(scope: str, path: Path, priority: int, source_id: str | None = None) -> RuleSource:
    content = path.read_text(encoding="utf-8", errors="ignore")
    return RuleSource(
        id=source_id or f"{scope}:{path.name}:{abs(hash(str(path)))}",
        scope=scope,
        path=str(path),
        priority=priority,
        content=content,
        summary=summarize_rule_text(content),
    )
