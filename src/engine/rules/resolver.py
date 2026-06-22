"""Resolve task rules in the order ClawCodex applies them."""

from __future__ import annotations

from .loader import load_rule_sources
from .models import ResolvedRules, RuleSource, summarize_rule_text


def resolve_rules(
    repo_path: str,
    enabled_packs: list[str] | None = None,
    task_rules: str | None = None,
    agent_rules: str | None = None,
    temporary_instruction: str | None = None,
) -> ResolvedRules:
    sources = load_rule_sources(repo_path, enabled_packs=enabled_packs)
    if agent_rules:
        sources.append(_inline_source("per-agent", agent_rules, 50))
    if task_rules:
        sources.append(_inline_source("task", task_rules, 60))
    return ResolvedRules(repo_path=repo_path, sources=sorted(sources, key=lambda item: item.priority), temporary_instruction=temporary_instruction or "")


def _inline_source(scope: str, content: str, priority: int) -> RuleSource:
    return RuleSource(
        id=f"{scope}:{abs(hash(content))}",
        scope=scope,
        path=f"inline://{scope}",
        priority=priority,
        content=content,
        summary=summarize_rule_text(content),
    )
