"""Risk labels and approval reasons for proposed actions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

HIGH_RISK_PATTERNS = (
    re.compile(r"(^|/)(\.env|secrets|credentials|auth|security|deploy|deployment|migration|migrations)(/|\.|$)", re.IGNORECASE),
    re.compile(r"(Dockerfile|docker-compose|\.github/workflows|package-lock\.json|Cargo\.lock)", re.IGNORECASE),
)
MEDIUM_RISK_PATTERNS = (
    re.compile(r"(package\.json|pyproject\.toml|Cargo\.toml|requirements\.txt|config|settings)", re.IGNORECASE),
)


def assess_file_change(file_path: str, unified_diff: str = "") -> dict[str, Any]:
    normalized = Path(file_path).as_posix()
    added = sum(1 for line in unified_diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in unified_diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    reasons = []
    risk = "Low"
    if any(pattern.search(normalized) for pattern in HIGH_RISK_PATTERNS):
        risk = "High"
        reasons.append("Touches security, environment, deployment, migration, or lock/config-sensitive files.")
    elif any(pattern.search(normalized) for pattern in MEDIUM_RISK_PATTERNS):
        risk = "Medium"
        reasons.append("Touches project configuration or dependency metadata.")
    if removed > 100 or added + removed > 300:
        risk = "High"
        reasons.append("Large patch size needs explicit review.")
    elif removed > 20 and risk == "Low":
        risk = "Medium"
        reasons.append("Removes enough code to deserve closer review.")
    if not reasons:
        reasons.append("Low-risk source change with checkpoint and diff preview available.")
    return {
        "risk_level": risk,
        "approval_reason": " ".join(reasons),
        "patch_summary": f"{added} added, {removed} removed",
        "added_lines": added,
        "removed_lines": removed,
    }


def assess_command(command: str) -> dict[str, Any]:
    lower = command.lower()
    high = ("rm -rf", "git reset --hard", "drop database", "push --force", "remove-item")
    medium = ("npm install", "pip install", "cargo add", "pnpm add", "yarn add", "git push")
    if any(item in lower for item in high):
        return {"risk_level": "High", "approval_reason": "Destructive or remote-changing command requires approval."}
    if any(item in lower for item in medium):
        return {"risk_level": "Medium", "approval_reason": "Dependency, package, network, or remote command requires confirmation."}
    return {"risk_level": "Low", "approval_reason": "Read-only or safe local command."}
