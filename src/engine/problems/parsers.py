"""Normalize compiler, linter, and test output into Problems-panel diagnostics."""

from __future__ import annotations

import re
from typing import Any

TS = re.compile(r"(?P<file>[^()\s]+\.tsx?)[:(](?P<line>\d+)[,:](?P<column>\d+)\)?\s+-?\s*(?:error\s+)?(?P<code>TS\d+)?:?\s*(?P<message>.+)")
PY = re.compile(r'File "(?P<file>[^"]+\.py)", line (?P<line>\d+)')
PYTEST = re.compile(r"(?P<file>[^:\s]+\.py):(?P<line>\d+):(?P<message>.+)")
RUST = re.compile(r"-->\s+(?P<file>[^:]+\.rs):(?P<line>\d+):(?P<column>\d+)")
ESLINT = re.compile(r"(?P<file>[^:\n]+\.[jt]sx?)\n\s+(?P<line>\d+):(?P<column>\d+)\s+(?P<severity>error|warning)\s+(?P<message>.+)")


def parse_diagnostics(stdout: str = "", stderr: str = "", source: str = "test") -> list[dict[str, Any]]:
    text = "\n".join(part for part in [stdout, stderr] if part)
    diagnostics: list[dict[str, Any]] = []
    for pattern, parser_source in [(TS, "typescript"), (PYTEST, "pytest"), (RUST, "rust"), (ESLINT, "eslint")]:
        for match in pattern.finditer(text):
            data = match.groupdict()
            diagnostics.append(_diagnostic(data, parser_source, match.group(0)))
    for match in PY.finditer(text):
        data = match.groupdict()
        diagnostics.append(_diagnostic({**data, "column": None, "message": _nearby_message(text, match.end())}, "python", match.group(0)))
    if not diagnostics and text.strip():
        first = text.strip().splitlines()[0][:500]
        diagnostics.append({"file": "", "line": None, "column": None, "severity": "error", "source": source, "code": "", "message": first, "raw": text[-2000:]})
    return diagnostics


def _diagnostic(data: dict[str, str | None], source: str, raw: str) -> dict[str, Any]:
    return {
        "file": data.get("file") or "",
        "line": _int(data.get("line")),
        "column": _int(data.get("column")),
        "severity": data.get("severity") or "error",
        "source": source,
        "code": data.get("code") or "",
        "message": (data.get("message") or raw).strip(),
        "raw": raw,
    }


def _int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def _nearby_message(text: str, offset: int) -> str:
    tail = text[offset:].splitlines()
    return next((line.strip() for line in tail if line.strip()), "Python traceback")
