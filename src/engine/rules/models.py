"""Rule and pack data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RuleSource:
    id: str
    scope: str
    path: str
    priority: int
    enabled: bool = True
    content: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResolvedRules:
    repo_path: str
    sources: list[RuleSource] = field(default_factory=list)
    temporary_instruction: str = ""

    @property
    def merged_content(self) -> str:
        parts = [f"## {source.scope}: {Path(source.path).name}\n{source.content}" for source in self.sources if source.enabled and source.content]
        if self.temporary_instruction:
            parts.append(f"## temporary_user_instruction\n{self.temporary_instruction}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "sources": [source.to_dict() for source in self.sources],
            "temporary_instruction": self.temporary_instruction,
            "merged_content": self.merged_content,
            "summary": self.summary(),
        }

    def summary(self) -> list[str]:
        return [source.summary or source.content.strip().splitlines()[0][:160] for source in self.sources if source.enabled and source.content.strip()]


def summarize_rule_text(text: str) -> str:
    lines = [line.strip(" -#\t") for line in text.splitlines() if line.strip()]
    return lines[0][:180] if lines else "Empty rule source"
