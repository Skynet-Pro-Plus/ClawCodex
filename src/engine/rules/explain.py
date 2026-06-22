"""Explain how active rules affect decisions."""

from __future__ import annotations

from .models import ResolvedRules


def explain_decision(rules: ResolvedRules, decision: str) -> dict[str, object]:
    keywords = {word.lower().strip(".,:;") for word in decision.split() if len(word) > 3}
    affected_by = []
    for source in rules.sources:
        text = source.content.lower()
        if any(word in text for word in keywords):
            affected_by.append(source.to_dict())
    if not affected_by:
        affected_by = [source.to_dict() for source in rules.sources[:3]]
    return {"decision": decision, "affected_by": affected_by, "rule_count": len(rules.sources)}
