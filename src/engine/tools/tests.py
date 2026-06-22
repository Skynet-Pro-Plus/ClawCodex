"""Safe test command detection and execution."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..orchestrator.events import parse_test_errors
from ..orchestrator.store import OrchestratorStore, get_store
from ..problems import parse_diagnostics
from .base import ToolContext
from .commands import run_command


SAFE_TEST_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "python -m unittest",
    "python3 -m unittest",
    "python -m py_compile",
    "npm test",
    "pnpm test",
    "yarn test",
    "cargo test",
    "cargo nextest",
)


def detect_test_command(repo_path: str) -> str | None:
    repo = Path(repo_path)
    if (repo / "pytest.ini").is_file() or (repo / "tests").is_dir():
        return "python -m pytest -q" if (repo / "pytest.ini").is_file() else "python -m unittest discover -s tests -v"
    if (repo / "package.json").is_file():
        text = (repo / "package.json").read_text(encoding="utf-8", errors="ignore")
        if re.search(r'"test"\s*:', text):
            return "npm test --silent"
    if (repo / "Cargo.toml").is_file():
        return "cargo test"
    return None


def verify_applied_html_files(
    task_id: str,
    repo_path: str,
    *,
    store: OrchestratorStore | None = None,
    timeout_sec: int = 60,
) -> dict | None:
    """Parse applied HTML preview files with html.parser (read-only structural check)."""
    store = store or get_store()
    paths: list[str] = []
    for diff in store.list_diff_previews(task_id):
        if diff.get("status") != "applied":
            continue
        fp = str(diff.get("file_path", "")).lower()
        if fp.endswith((".html", ".htm")):
            paths.append(str(diff["file_path"]))
    if not paths:
        return None
    script = (
        "import json,sys\n"
        "from pathlib import Path\n"
        "from html.parser import HTMLParser\n"
        f"paths=json.loads(sys.argv[1])\n"
        "parser=HTMLParser()\n"
        "for p in paths:\n"
        "    parser.feed(Path(p).read_text(encoding='utf-8'))\n"
    )
    payload = json.dumps(paths)
    start_cmd = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script, payload],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        status = "passed" if proc.returncode == 0 else "failed"
        duration_ms = int((time.perf_counter() - start_cmd) * 1000)
    except subprocess.TimeoutExpired as exc:
        return store.insert_test_run(
            {
                "task_id": task_id,
                "command": "python -c <html.parser verify>",
                "status": "timeout",
                "exit_code": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "parsed_errors": [],
                "duration_ms": timeout_sec * 1000,
            }
        )
    test_run = {
        "task_id": task_id,
        "command": "python -c <html.parser verify>",
        "status": status,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "parsed_errors": [],
        "duration_ms": duration_ms,
    }
    return store.insert_test_run(test_run)


def run_tests(command: str | None = None, target: str | None = None, timeout_sec: int = 120, **kwargs) -> dict:
    raw = kwargs.pop("context", None)
    context = raw if isinstance(raw, ToolContext) else ToolContext(
        task_id=getattr(raw, "task_id", kwargs.pop("task_id", "manual")),
        repo_path=kwargs.pop("repo_path", "."),
        allowed_paths=getattr(raw, "allowed_paths", kwargs.pop("allowed_paths", [])) or [],
        denied_paths=getattr(raw, "denied_paths", kwargs.pop("denied_paths", [".env", ".env.local", ".env.production"])) or [".env", ".env.local", ".env.production"],
        confirmed=True,
    )
    selected = command or detect_test_command(context.repo_path)
    if not selected:
        result = {
            "task_id": context.task_id,
            "command": "",
            "status": "skipped",
            "exit_code": None,
            "stdout": "",
            "stderr": "No automated test harness detected for this repo type.",
            "parsed_errors": [],
            "duration_ms": 0,
        }
        return get_store().insert_test_run(result)
    if not selected.startswith(SAFE_TEST_PREFIXES):
        result = {
            "task_id": context.task_id,
            "command": selected,
            "status": "blocked",
            "exit_code": None,
            "stdout": "",
            "stderr": "Test command is not in the safe allowlist",
            "parsed_errors": [],
            "duration_ms": 0,
        }
        return get_store().insert_test_run(result)
    runner = selected.split()[0]
    if shutil.which(runner) is None:
        result = {
            "task_id": context.task_id,
            "command": selected,
            "status": "blocked",
            "exit_code": None,
            "stdout": "",
            "stderr": f"Test runner '{runner}' is not installed on this machine; blocking instead of retrying a command that can never succeed.",
            "parsed_errors": [],
            "duration_ms": 0,
        }
        return get_store().insert_test_run(result)
    if target:
        selected = f"{selected} {target}"
    command_result = run_command(selected, timeout_sec=timeout_sec, context=context)
    parsed = parse_test_errors(command_result.get("stdout", ""), command_result.get("stderr", ""))
    diagnostics = parse_diagnostics(command_result.get("stdout", ""), command_result.get("stderr", ""), source="test")
    test_run = {
        "task_id": context.task_id,
        "command": selected,
        "status": "passed" if command_result["status"] == "passed" else command_result["status"],
        "exit_code": command_result["exit_code"],
        "stdout": command_result["stdout"],
        "stderr": command_result["stderr"],
        "parsed_errors": parsed,
        "duration_ms": command_result["duration_ms"],
    }
    store = get_store()
    for diagnostic in diagnostics:
        store.insert_diagnostic(context.task_id, diagnostic)
    return store.insert_test_run(test_run)
