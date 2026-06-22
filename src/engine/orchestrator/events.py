"""Event helpers and test-output parsing for orchestration."""

from __future__ import annotations

import re
from typing import Any


PYTEST_ERROR = re.compile(r"^(?P<file>[^:\s][^:]*\.py):(?P<line>\d+):", re.MULTILINE)
UNITTEST_ERROR = re.compile(r"^(?P<type>AssertionError|[A-Za-z_][\w.]*Error): (?P<message>.*)$", re.MULTILINE)
TS_ERROR = re.compile(r"(?P<file>[^()\s]+\.tsx?):(?P<line>\d+):(?P<col>\d+) - error (?P<code>TS\d+): (?P<message>.*)")
RUST_ERROR = re.compile(r"-->\s+(?P<file>[^:]+\.rs):(?P<line>\d+):(?P<col>\d+)")


def parse_test_errors(stdout: str, stderr: str) -> list[dict[str, Any]]:
    output = "\n".join(part for part in [stdout, stderr] if part)
    errors: list[dict[str, Any]] = []
    for match in PYTEST_ERROR.finditer(output):
        errors.append(
            {
                "type": "pytest",
                "message": _nearby_line(output, match.start()),
                "file": match.group("file"),
                "line": int(match.group("line")),
                "test_name": _find_test_name(output),
                "signature": f"{match.group('file')}:{match.group('line')}",
            }
        )
    for match in TS_ERROR.finditer(output):
        errors.append(
            {
                "type": "typescript",
                "message": match.group("message"),
                "file": match.group("file"),
                "line": int(match.group("line")),
                "test_name": "",
                "signature": f"{match.group('code')}:{match.group('file')}:{match.group('line')}",
            }
        )
    for match in RUST_ERROR.finditer(output):
        errors.append(
            {
                "type": "rust",
                "message": _nearby_line(output, match.start()),
                "file": match.group("file").strip(),
                "line": int(match.group("line")),
                "test_name": "",
                "signature": f"rust:{match.group('file')}:{match.group('line')}",
            }
        )
    for match in UNITTEST_ERROR.finditer(output):
        errors.append(
            {
                "type": match.group("type"),
                "message": match.group("message"),
                "file": "",
                "line": None,
                "test_name": _find_test_name(output),
                "signature": f"{match.group('type')}:{match.group('message')[:120]}",
            }
        )
    if not errors and output.strip():
        errors.append(
            {
                "type": "generic",
                "message": output.strip()[-1000:],
                "file": "",
                "line": None,
                "test_name": "",
                "signature": str(abs(hash(output.strip()[-1000:]))),
            }
        )
    return errors


def _nearby_line(output: str, offset: int) -> str:
    prefix = output[:offset]
    line_start = prefix.rfind("\n") + 1
    line_end = output.find("\n", offset)
    if line_end == -1:
        line_end = len(output)
    return output[line_start:line_end].strip()


def _find_test_name(output: str) -> str:
    match = re.search(r"(test_[\w\[\].:-]+)", output)
    return match.group(1) if match else ""
