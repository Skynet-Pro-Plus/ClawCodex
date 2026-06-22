"""SQLite persistence for orchestrated coding tasks."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
import atexit
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .stages import Stage, StageStatus, assert_transition


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@dataclass
class TaskRecord:
    id: str
    repo_path: str
    prompt: str
    stage: str = Stage.IDLE.value
    max_debug_attempts: int = 3
    debug_attempts: int = 0
    model_config: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageRunRecord:
    id: str
    task_id: str
    stage: str
    model: str
    status: str = StageStatus.QUEUED.value
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrchestratorStore:
    """Small durable store used by API routes, tools, and the runner."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else Path.home() / ".claw-engine" / "orchestrator.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection"):
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    repo_path TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    max_debug_attempts INTEGER NOT NULL DEFAULT 3,
                    debug_attempts INTEGER NOT NULL DEFAULT 0,
                    model_config TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stage_runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input TEXT NOT NULL DEFAULT '{}',
                    output TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input TEXT NOT NULL DEFAULT '{}',
                    output TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS git_checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    head_sha TEXT NOT NULL,
                    checkpoint_ref TEXT NOT NULL,
                    dirty_patch_path TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diff_previews (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    before_sha256 TEXT,
                    after_sha256 TEXT NOT NULL,
                    proposed_content TEXT NOT NULL,
                    unified_diff TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS test_runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    parsed_errors TEXT NOT NULL DEFAULT '[]',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_profiles (
                    repo_path TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_memory (
                    id TEXT PRIMARY KEY,
                    repo_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_role_configs (
                    scope TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    path TEXT NOT NULL,
                    preview_url TEXT NOT NULL,
                    analysis_status TEXT NOT NULL,
                    analysis TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_rules (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    sources TEXT NOT NULL DEFAULT '[]',
                    merged_content TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rule_decisions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    affected_by TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_evidence (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    query TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    results TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diagnostics (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    file TEXT NOT NULL DEFAULT '',
                    line INTEGER,
                    column INTEGER,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL,
                    raw TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diff_hunks (
                    id TEXT PRIMARY KEY,
                    preview_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    header TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    risk_level TEXT NOT NULL DEFAULT 'Low',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS worktree_records (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_stage_runs_task ON stage_runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_diff_previews_task ON diff_previews(task_id);
                CREATE INDEX IF NOT EXISTS idx_test_runs_task ON test_runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_attachments_task ON attachments(task_id);
                CREATE INDEX IF NOT EXISTS idx_task_rules_task ON task_rules(task_id);
                CREATE INDEX IF NOT EXISTS idx_search_evidence_task ON search_evidence(task_id);
                CREATE INDEX IF NOT EXISTS idx_diagnostics_task ON diagnostics(task_id);
                CREATE INDEX IF NOT EXISTS idx_diff_hunks_preview ON diff_hunks(preview_id);
                """
            )
            self._ensure_column(conn, "diff_previews", "risk_level", "TEXT NOT NULL DEFAULT 'Low'")
            self._ensure_column(conn, "diff_previews", "approval_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "diff_previews", "patch_summary", "TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column not in {row["name"] for row in rows}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def close(self) -> None:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            delattr(self._local, "connection")

    def create_task(
        self,
        repo_path: str,
        prompt: str,
        max_debug_attempts: int = 3,
        model_config: dict[str, Any] | None = None,
    ) -> TaskRecord:
        task = TaskRecord(
            id=uuid.uuid4().hex,
            repo_path=str(Path(repo_path).resolve()),
            prompt=prompt,
            max_debug_attempts=max_debug_attempts,
            model_config=model_config or {},
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks
                (id, repo_path, prompt, stage, max_debug_attempts, debug_attempts, model_config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.repo_path,
                    task.prompt,
                    task.stage,
                    task.max_debug_attempts,
                    task.debug_attempts,
                    _json(task.model_config),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        row = self._connection().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(self, limit: int = 100) -> list[TaskRecord]:
        cap = max(1, min(int(limit), 500))
        rows = self._connection().execute(
            "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
            (cap,),
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_recent_repos(self, limit: int = 50) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit), 200))
        rows = self._connection().execute(
            """
            SELECT repo_path, MAX(updated_at) AS last_used_at
            FROM tasks
            GROUP BY repo_path
            ORDER BY last_used_at DESC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            repo_path = str(row["repo_path"])
            profile = self.get_project_profile(repo_path)
            entry: dict[str, Any] = {
                "repo_path": repo_path,
                "last_used_at": row["last_used_at"],
                "project_profile": profile,
            }
            result.append(entry)
        return result

    def delete_task(self, task_id: str) -> bool:
        if self.get_task(task_id) is None:
            return False
        with self.transaction() as conn:
            for table in (
                "diff_hunks",
                "diff_previews",
                "stage_runs",
                "tool_calls",
                "git_checkpoints",
                "test_runs",
                "task_rules",
                "rule_decisions",
                "search_evidence",
                "diagnostics",
                "worktree_records",
            ):
                conn.execute(f"DELETE FROM {table} WHERE task_id = ?", (task_id,))
            conn.execute("UPDATE attachments SET task_id = NULL WHERE task_id = ?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return True

    def update_task_stage(self, task_id: str, target: Stage | str) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        assert_transition(task.stage, target)
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE tasks SET stage = ?, updated_at = ? WHERE id = ?",
                (Stage(target).value, now, task_id),
            )
        updated = self.get_task(task_id)
        if updated is None:
            raise KeyError(f"task not found after update: {task_id}")
        return updated

    def increment_debug_attempts(self, task_id: str) -> int:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE tasks SET debug_attempts = debug_attempts + 1, updated_at = ? WHERE id = ?",
                (utc_now(), task_id),
            )
            row = conn.execute("SELECT debug_attempts FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return int(row["debug_attempts"]) if row else 0

    def create_stage_run(
        self,
        task_id: str,
        stage: Stage | str,
        model: str,
        input_data: dict[str, Any] | None = None,
        status: StageStatus | str = StageStatus.RUNNING,
    ) -> StageRunRecord:
        record = StageRunRecord(
            id=uuid.uuid4().hex,
            task_id=task_id,
            stage=Stage(stage).value,
            model=model,
            status=StageStatus(status).value,
            input=input_data or {},
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO stage_runs
                (id, task_id, stage, model, status, input, output, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.task_id,
                    record.stage,
                    record.model,
                    record.status,
                    _json(record.input),
                    _json(record.output),
                    record.started_at,
                    record.finished_at,
                ),
            )
        return record

    def finish_stage_run(
        self,
        run_id: str,
        status: StageStatus | str,
        output: dict[str, Any] | None = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE stage_runs SET status = ?, output = ?, finished_at = ? WHERE id = ?",
                (StageStatus(status).value, _json(output or {}), utc_now(), run_id),
            )

    def record_tool_call(self, task_id: str, tool_name: str, status: str, input_data: dict[str, Any], output: Any) -> str:
        call_id = uuid.uuid4().hex
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO tool_calls (id, task_id, tool_name, status, input, output, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (call_id, task_id, tool_name, status, _json(input_data), _json(output), utc_now()),
            )
        return call_id

    def insert_task_rules(self, task_id: str, repo_path: str, resolved: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "task_id": task_id,
            "repo_path": str(Path(repo_path).resolve()),
            "sources": resolved.get("sources", []),
            "merged_content": resolved.get("merged_content", ""),
            "summary": resolved.get("summary", []),
            "created_at": utc_now(),
        }
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO task_rules (id, task_id, repo_path, sources, merged_content, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record["id"], task_id, record["repo_path"], _json(record["sources"]), record["merged_content"], _json(record["summary"]), record["created_at"]),
            )
        return record

    def latest_task_rules(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM task_rules WHERE task_id = ? ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["sources"] = _load_json(data.get("sources"), [])
        data["summary"] = _load_json(data.get("summary"), [])
        return data

    def record_rule_decision(self, task_id: str, decision: str, affected_by: list[dict[str, Any]]) -> dict[str, Any]:
        record = {"id": uuid.uuid4().hex, "task_id": task_id, "decision": decision, "affected_by": affected_by, "created_at": utc_now()}
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO rule_decisions (id, task_id, decision, affected_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (record["id"], task_id, decision, _json(affected_by), record["created_at"]),
            )
        return record

    def insert_search_evidence(self, task_id: str, repo_path: str, query: str, kind: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "task_id": task_id,
            "repo_path": str(Path(repo_path).resolve()),
            "query": query,
            "kind": kind,
            "results": results,
            "created_at": utc_now(),
        }
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO search_evidence (id, task_id, repo_path, query, kind, results, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record["id"], task_id, record["repo_path"], query, kind, _json(results), record["created_at"]),
            )
        return record

    def list_search_evidence(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection().execute("SELECT * FROM search_evidence WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        return [{**dict(row), "results": _load_json(row["results"], [])} for row in rows]

    def insert_diagnostic(self, task_id: str, diagnostic: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "task_id": task_id,
            "file": diagnostic.get("file", ""),
            "line": diagnostic.get("line"),
            "column": diagnostic.get("column"),
            "severity": diagnostic.get("severity", "error"),
            "source": diagnostic.get("source", diagnostic.get("type", "unknown")),
            "code": diagnostic.get("code", ""),
            "message": diagnostic.get("message", ""),
            "raw": diagnostic.get("raw", ""),
            "created_at": utc_now(),
        }
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO diagnostics (id, task_id, file, line, column, severity, source, code, message, raw, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["id"],
                    task_id,
                    record["file"],
                    record["line"],
                    record["column"],
                    record["severity"],
                    record["source"],
                    record["code"],
                    record["message"],
                    record["raw"],
                    record["created_at"],
                ),
            )
        return record

    def list_diagnostics(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection().execute("SELECT * FROM diagnostics WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_worktree_record(self, task_id: str, repo_path: str, workspace_path: str, branch: str, status: str) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "task_id": task_id,
            "repo_path": str(Path(repo_path).resolve()),
            "workspace_path": workspace_path,
            "branch": branch,
            "status": status,
            "created_at": utc_now(),
        }
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO worktree_records (id, task_id, repo_path, workspace_path, branch, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record["id"], task_id, record["repo_path"], workspace_path, branch, status, record["created_at"]),
            )
        return record

    def latest_worktree_record(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM worktree_records WHERE task_id = ? ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
        return dict(row) if row else None

    def insert_checkpoint(self, data: dict[str, Any]) -> dict[str, Any]:
        checkpoint = {
            "id": data.get("id") or uuid.uuid4().hex,
            "created_at": data.get("created_at") or utc_now(),
            **data,
        }
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO git_checkpoints
                (id, task_id, repo_path, head_sha, checkpoint_ref, dirty_patch_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint["id"],
                    checkpoint["task_id"],
                    checkpoint["repo_path"],
                    checkpoint["head_sha"],
                    checkpoint["checkpoint_ref"],
                    checkpoint.get("dirty_patch_path"),
                    checkpoint["created_at"],
                ),
            )
        return checkpoint

    def list_checkpoints(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            "SELECT * FROM git_checkpoints WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM git_checkpoints WHERE id = ?", (checkpoint_id,)).fetchone()
        return dict(row) if row else None

    def insert_diff_preview(self, data: dict[str, Any]) -> dict[str, Any]:
        preview = {
            "id": data.get("id") or uuid.uuid4().hex,
            "status": data.get("status", "pending"),
            "risk_level": data.get("risk_level", "Low"),
            "approval_reason": data.get("approval_reason", ""),
            "patch_summary": data.get("patch_summary", ""),
            "created_at": data.get("created_at") or utc_now(),
            "updated_at": data.get("updated_at") or utc_now(),
            **data,
        }
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO diff_previews
                (id, task_id, repo_path, file_path, before_sha256, after_sha256, proposed_content, unified_diff, status, created_at, updated_at, risk_level, approval_reason, patch_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview["id"],
                    preview["task_id"],
                    preview["repo_path"],
                    preview["file_path"],
                    preview.get("before_sha256"),
                    preview["after_sha256"],
                    preview["proposed_content"],
                    preview["unified_diff"],
                    preview["status"],
                    preview["created_at"],
                    preview["updated_at"],
                    preview.get("risk_level", "Low"),
                    preview.get("approval_reason", ""),
                    preview.get("patch_summary", ""),
                ),
            )
        return preview

    def update_diff_status(self, preview_id: str, status: str) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE diff_previews SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), preview_id),
            )
        preview = self.get_diff_preview(preview_id)
        if preview is None:
            raise KeyError(f"diff preview not found: {preview_id}")
        return preview

    def update_diff_content(self, preview_id: str, content: str, after_sha256: str, unified_diff: str, risk: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE diff_previews
                SET proposed_content = ?, after_sha256 = ?, unified_diff = ?, risk_level = ?, approval_reason = ?, patch_summary = ?, status = 'pending', updated_at = ?
                WHERE id = ?
                """,
                (
                    content,
                    after_sha256,
                    unified_diff,
                    risk.get("risk_level", "Low"),
                    risk.get("approval_reason", ""),
                    risk.get("patch_summary", ""),
                    utc_now(),
                    preview_id,
                ),
            )
        preview = self.get_diff_preview(preview_id)
        if preview is None:
            raise KeyError(f"diff preview not found: {preview_id}")
        return preview

    def get_diff_preview(self, preview_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM diff_previews WHERE id = ?", (preview_id,)).fetchone()
        return dict(row) if row else None

    def list_diff_previews(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            "SELECT * FROM diff_previews WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_diff_hunk(self, data: dict[str, Any]) -> dict[str, Any]:
        hunk = {
            "id": data.get("id") or uuid.uuid4().hex,
            "status": data.get("status", "pending"),
            "risk_level": data.get("risk_level", "Low"),
            "created_at": data.get("created_at") or utc_now(),
            "updated_at": data.get("updated_at") or utc_now(),
            **data,
        }
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO diff_hunks
                (id, preview_id, task_id, file_path, header, body, status, risk_level, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hunk["id"],
                    hunk["preview_id"],
                    hunk["task_id"],
                    hunk["file_path"],
                    hunk["header"],
                    hunk["body"],
                    hunk["status"],
                    hunk["risk_level"],
                    hunk["created_at"],
                    hunk["updated_at"],
                ),
            )
        return hunk

    def update_diff_hunk_status(self, hunk_id: str, status: str) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute("UPDATE diff_hunks SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now(), hunk_id))
        row = self._connection().execute("SELECT * FROM diff_hunks WHERE id = ?", (hunk_id,)).fetchone()
        if row is None:
            raise KeyError(f"diff hunk not found: {hunk_id}")
        return dict(row)

    def list_diff_hunks(self, task_id: str | None = None, preview_id: str | None = None) -> list[dict[str, Any]]:
        if preview_id:
            rows = self._connection().execute("SELECT * FROM diff_hunks WHERE preview_id = ? ORDER BY created_at", (preview_id,)).fetchall()
        elif task_id:
            rows = self._connection().execute("SELECT * FROM diff_hunks WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        else:
            rows = []
        return [dict(row) for row in rows]

    def insert_test_run(self, data: dict[str, Any]) -> dict[str, Any]:
        run = {"id": data.get("id") or uuid.uuid4().hex, "created_at": data.get("created_at") or utc_now(), **data}
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO test_runs
                (id, task_id, command, status, exit_code, stdout, stderr, parsed_errors, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    run["task_id"],
                    run["command"],
                    run["status"],
                    run.get("exit_code"),
                    run.get("stdout", ""),
                    run.get("stderr", ""),
                    _json(run.get("parsed_errors", [])),
                    int(run.get("duration_ms", 0)),
                    run["created_at"],
                ),
            )
        return run

    def upsert_project_profile(self, repo_path: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {**data, "repo_path": str(Path(repo_path).resolve())}
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO project_profiles (repo_path, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(repo_path) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (payload["repo_path"], _json(payload), utc_now()),
            )
        return payload

    def get_project_profile(self, repo_path: str) -> dict[str, Any] | None:
        resolved = str(Path(repo_path).resolve())
        row = self._connection().execute("SELECT data FROM project_profiles WHERE repo_path = ?", (resolved,)).fetchone()
        return _load_json(row["data"], None) if row else None

    def insert_project_memory(self, repo_path: str, kind: str, content: str, evidence: list[Any] | None = None) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "repo_path": str(Path(repo_path).resolve()),
            "kind": kind,
            "content": content,
            "evidence": evidence or [],
            "created_at": utc_now(),
        }
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO project_memory (id, repo_path, kind, content, evidence, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (record["id"], record["repo_path"], kind, content, _json(record["evidence"]), record["created_at"]),
            )
        return record

    def list_project_memory(self, repo_path: str) -> list[dict[str, Any]]:
        resolved = str(Path(repo_path).resolve())
        rows = self._connection().execute(
            "SELECT * FROM project_memory WHERE repo_path = ? ORDER BY created_at DESC",
            (resolved,),
        ).fetchall()
        return [{**dict(row), "evidence": _load_json(row["evidence"], [])} for row in rows]

    def set_model_role_config(self, scope: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO model_role_configs (scope, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (scope, _json(data), utc_now()),
            )
        return data

    def get_model_role_config(self, scope: str = "default") -> dict[str, Any] | None:
        row = self._connection().execute("SELECT data FROM model_role_configs WHERE scope = ?", (scope,)).fetchone()
        return _load_json(row["data"], None) if row else None

    def insert_attachment(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO attachments
                (id, task_id, filename, content_type, size_bytes, sha256, path, preview_url, analysis_status, analysis, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data.get("task_id"),
                    data["filename"],
                    data["content_type"],
                    int(data["size_bytes"]),
                    data["sha256"],
                    data["path"],
                    data["preview_url"],
                    data.get("analysis_status", "ready"),
                    _json(data.get("analysis", {})),
                    data.get("created_at") or utc_now(),
                ),
            )
        return data

    def get_attachment(self, attachment_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        return self._row_to_attachment(row) if row else None

    def list_attachments(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            "SELECT * FROM attachments WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        return [self._row_to_attachment(row) for row in rows]

    def update_attachment_task(self, attachment_id: str, task_id: str, path: str) -> dict[str, Any]:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE attachments SET task_id = ?, path = ?, preview_url = ? WHERE id = ?",
                (task_id, path, f"/api/attachments/{attachment_id}/content", attachment_id),
            )
        updated = self.get_attachment(attachment_id)
        if updated is None:
            raise KeyError(f"attachment not found: {attachment_id}")
        return updated

    def delete_attachment(self, attachment_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))

    def timeline(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        conn = self._connection()
        stage_runs = [self._row_to_stage(row).to_dict() for row in conn.execute("SELECT * FROM stage_runs WHERE task_id = ? ORDER BY started_at", (task_id,))]
        tool_calls = [dict(row) for row in conn.execute("SELECT * FROM tool_calls WHERE task_id = ? ORDER BY created_at", (task_id,))]
        checkpoints = self.list_checkpoints(task_id)
        previews = self.list_diff_previews(task_id)
        tests = []
        for row in conn.execute("SELECT * FROM test_runs WHERE task_id = ? ORDER BY created_at", (task_id,)):
            item = dict(row)
            item["parsed_errors"] = _load_json(item.get("parsed_errors"), [])
            tests.append(item)
        hunks = self.list_diff_hunks(task_id=task_id)
        return {
            "task": task.to_dict(),
            "stage_runs": stage_runs,
            "tool_calls": tool_calls,
            "git_checkpoints": checkpoints,
            "diff_previews": previews,
            "diff_hunks": hunks,
            "test_runs": tests,
            "attachments": self.list_attachments(task_id),
            "rules": self.latest_task_rules(task_id),
            "search_evidence": self.list_search_evidence(task_id),
            "diagnostics": self.list_diagnostics(task_id),
            "worktree": self.latest_worktree_record(task_id),
        }

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            repo_path=row["repo_path"],
            prompt=row["prompt"],
            stage=row["stage"],
            max_debug_attempts=row["max_debug_attempts"],
            debug_attempts=row["debug_attempts"],
            model_config=_load_json(row["model_config"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_stage(self, row: sqlite3.Row) -> StageRunRecord:
        return StageRunRecord(
            id=row["id"],
            task_id=row["task_id"],
            stage=row["stage"],
            model=row["model"],
            status=row["status"],
            input=_load_json(row["input"], {}),
            output=_load_json(row["output"], {}),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    @staticmethod
    def _row_to_attachment(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["analysis"] = _load_json(item.get("analysis"), {})
        return item


_default_store: OrchestratorStore | None = None
_store_lock = threading.Lock()
_atexit_registered = False


def get_store() -> OrchestratorStore:
    global _default_store, _atexit_registered
    with _store_lock:
        if _default_store is None:
            _default_store = OrchestratorStore()
        if not _atexit_registered:
            atexit.register(close_default_store)
            _atexit_registered = True
        return _default_store


def close_default_store() -> None:
    global _default_store
    if _default_store is not None:
        _default_store.close()
