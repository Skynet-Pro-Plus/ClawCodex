"""Lightweight LSP-like code intelligence helpers.

This is intentionally conservative: it provides deterministic local
definitions/references/hover while leaving room for real language-server
process integration.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..tools.search import search_repo


def diagnostics(repo_path: str, task_id: str = "manual") -> list[dict[str, Any]]:
    repo = Path(repo_path)
    results = []
    for py_file in repo.rglob("*.py"):
        if _skip(py_file):
            continue
        try:
            ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as exc:
            results.append({"file": str(py_file), "line": exc.lineno, "column": exc.offset, "severity": "error", "source": "python-ast", "code": "SyntaxError", "message": exc.msg, "raw": str(exc)})
    return results


def definition(repo_path: str, symbol: str, task_id: str = "manual") -> dict[str, Any]:
    result = search_repo(rf"(def|class|const|function|let|var)\s+{re.escape(symbol)}\b", "text", 20, repo_path=repo_path, task_id=task_id)
    return {"symbol": symbol, "definitions": result.get("matches", [])}


def references(repo_path: str, symbol: str, task_id: str = "manual") -> dict[str, Any]:
    result = search_repo(symbol, "symbol", 100, repo_path=repo_path, task_id=task_id)
    return {"symbol": symbol, "references": result.get("matches", [])}


def hover(repo_path: str, file_path: str, line: int) -> dict[str, Any]:
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(repo_path) / path
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    text = lines[line - 1].strip() if 0 < line <= len(lines) else ""
    return {"file": str(path), "line": line, "text": text, "documentation": _doc_hint(text)}


def code_actions(diagnostic: dict[str, Any]) -> list[dict[str, Any]]:
    message = str(diagnostic.get("message", ""))
    actions = []
    if "format" in message.lower() or "prettier" in message.lower():
        actions.append({"title": "Run formatter", "kind": "quickfix.format"})
    if "import" in message.lower() or "not defined" in message.lower():
        actions.append({"title": "Inspect missing import or symbol reference", "kind": "quickfix.import"})
    if not actions:
        actions.append({"title": "Open file at diagnostic", "kind": "quickfix.inspect"})
    return actions


def _doc_hint(text: str) -> str:
    if text.startswith("def "):
        return "Python function definition"
    if text.startswith("class "):
        return "Python class definition"
    if "=>" in text or text.startswith("function "):
        return "JavaScript/TypeScript function"
    return "Source context"


def _skip(path: Path) -> bool:
    return any(part in {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"} for part in path.parts)
