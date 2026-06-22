"""Generate structured file-change proposals for CODE stage."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..routing.model_selector import ModelSelector
from ..safety.destructive_ops import SafetyPolicy, SafetyViolation
from .openrouter_client import ModelNotConfigured, ModelResponseError, request_code_json_with_usage


@dataclass(frozen=True)
class ProposedChange:
    path: str
    mode: str
    content: str


@dataclass
class CodeGenerationResult:
    summary: str
    changes: list[ProposedChange] = field(default_factory=list)
    test_command: str | None = None
    notes: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["changes"] = [asdict(change) for change in self.changes]
        return data


def generate_code_changes(
    prompt: str,
    repo_path: str,
    attachments: list[dict[str, Any]] | None = None,
    project_profile: dict[str, Any] | None = None,
    denied_paths: list[str] | None = None,
    model: str | None = None,
) -> CodeGenerationResult:
    """Generate a strict proposal: never writes files, only returns changes."""
    local = _local_template(prompt, repo_path)
    if local:
        return _validate_result(local, repo_path, denied_paths)

    selected_model = model or ModelSelector().recommend("coder").model
    system_prompt = (
        "You are ClawCodex Coder. Return only JSON with keys summary, changes, test_command, notes. "
        "Each change must include path, mode create|replace, and full file content. "
        "Do not edit denied paths. Do not include markdown fences."
    )
    user_prompt = json.dumps(
        {
            "task": prompt,
            "repo_path": repo_path,
            "attachments": attachments or [],
            "project_profile": project_profile or {},
            "denied_paths": denied_paths or [".env", ".env.local", "secrets.json"],
            "schema": {
                "summary": "string",
                "changes": [{"path": "string", "mode": "create|replace", "content": "string"}],
                "test_command": "string|null",
                "notes": ["string"],
            },
        },
        indent=2,
    )
    try:
        response = request_code_json_with_usage(selected_model, system_prompt, user_prompt)
        raw = response["json"]
    except ModelNotConfigured as exc:
        return CodeGenerationResult(
            summary="Code generation blocked",
            blocked_reason=str(exc),
            model=selected_model,
        )
    except ModelResponseError as exc:
        return CodeGenerationResult(
            summary="Code generation failed",
            blocked_reason=str(exc),
            model=selected_model,
        )
    result = _from_raw(raw, selected_model)
    result.usage = response.get("usage") or {}
    result.cost_usd = _usage_cost_usd(result.usage)
    return _validate_result(result, repo_path, denied_paths)


def _from_raw(raw: dict[str, Any], model: str) -> CodeGenerationResult:
    changes = [
        ProposedChange(
            path=str(item.get("path", "")),
            mode=str(item.get("mode", "create")),
            content=str(item.get("content", "")),
        )
        for item in raw.get("changes", [])
    ]
    return CodeGenerationResult(
        summary=str(raw.get("summary", "Proposed code changes")),
        changes=changes,
        test_command=raw.get("test_command"),
        notes=[str(note) for note in raw.get("notes", [])],
        model=model,
    )


def _validate_result(result: CodeGenerationResult, repo_path: str, denied_paths: list[str] | None) -> CodeGenerationResult:
    if result.blocked_reason:
        return result
    policy = SafetyPolicy(repo_path, denied_paths=denied_paths or [".env", ".env.local", "secrets.json"])
    valid: list[ProposedChange] = []
    for change in result.changes:
        if change.mode not in {"create", "replace"}:
            raise ValueError(f"invalid change mode: {change.mode}")
        if not change.path or not change.content:
            raise ValueError("change path and content are required")
        try:
            resolved = policy.check_write_path(change.path)
        except SafetyViolation as exc:
            raise ValueError(str(exc)) from exc
        resolved_path = Path(resolved)
        mode = change.mode
        if mode == "create" and resolved_path.is_file():
            mode = "replace"
        valid.append(ProposedChange(path=str(resolved_path), mode=mode, content=change.content))
    result.changes = valid
    if not result.changes:
        result.blocked_reason = "No code changes were proposed. Add more implementation detail or configure a model."
    return result


def _usage_cost_usd(usage: dict[str, Any]) -> float | None:
    value = usage.get("cost")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _local_template(prompt: str, repo_path: str) -> CodeGenerationResult | None:
    normalized = prompt.lower()
    print_match = re.search(r"(?:create|add|build|make)\s+(?:a\s+)?(?:new\s+)?(?:python\s+)?(?:file\s+)?([a-z0-9_-]+\.py).*?(?:prints?|says?)\s+([a-z0-9 _.,!'-]+)", normalized)
    if print_match:
        filename = print_match.group(1)
        message = print_match.group(2).strip(" .")
        content = f'''"""Small Python program generated by ClawCodex."""

from __future__ import annotations


def main() -> None:
    print({message.title()!r})


if __name__ == "__main__":
    main()
'''
        return CodeGenerationResult(
            summary=f"Create {filename} as a small Python program.",
            changes=[ProposedChange(path=str(Path(repo_path) / filename), mode="create", content=content)],
            test_command=f"python -m py_compile {filename}",
            notes=["Generated locally because this simple Python file request can be safely templated."],
            model="local-template",
        )

    if ("hello world" in normalized or "hello-world" in normalized) and (
        "html" in normalized or ".html" in normalized or ".htm" in normalized
    ):
        html_path = Path(repo_path) / "hello.html"
        html_body = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hello</title>
</head>
<body>
  <h1>Hello, world!</h1>
</body>
</html>
"""
        return CodeGenerationResult(
            summary="Add a minimal hello world HTML page at hello.html.",
            changes=[ProposedChange(path=str(html_path), mode="create", content=html_body)],
            test_command=None,
            notes=["Generated locally for simple hello-world HTML requests."],
            model="local-template",
        )

    if "python" in normalized and "gui" in normalized and "hello world" in normalized:
        title_match = re.search(r"says?\s+([a-z0-9 _-]+)", normalized)
        message = "Hello World"
        if title_match:
            candidate = title_match.group(1).strip(" .")
            if candidate:
                message = candidate.title()
        content = f'''"""Simple Windows-friendly Python GUI generated by ClawCodex."""

from __future__ import annotations

import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title("ClawCodex Hello World")
    root.geometry("420x180")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=28, pady=28)
    frame.pack(expand=True, fill="both")

    label = tk.Label(frame, text="{message}", font=("Segoe UI", 24, "bold"))
    label.pack(expand=True)

    close_button = tk.Button(frame, text="Close", command=root.destroy)
    close_button.pack(pady=(12, 0))

    root.mainloop()


if __name__ == "__main__":
    main()
'''
        return CodeGenerationResult(
            summary="Create a Windows-friendly Tkinter hello world GUI.",
            changes=[ProposedChange(path=str(Path(repo_path) / "hello_world_gui.py"), mode="create", content=content)],
            test_command="python -m py_compile hello_world_gui.py",
            notes=["Generated locally because this common starter task can be safely templated."],
            model="local-template",
        )
    return None
