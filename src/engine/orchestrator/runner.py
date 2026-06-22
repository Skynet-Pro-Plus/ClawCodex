"""Executable stage runner for ClawCodex tasks."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from ..coding import generate_code_changes
from ..coding.openrouter_client import ModelNotConfigured, ModelResponseError, request_code_json_with_usage
from ..memory.failure_patterns import record_failure_pattern
from ..routing.model_selector import ModelSelector
from ..rules import resolve_rules
from ..safety.risk import assess_file_change
from ..safety.diff_preview import DiffPreviewService
from ..safety.git_checkpoints import GitCheckpointService
from ..tools.base import ToolContext
from ..tools.git import git_diff
from ..tools.search import search_repo
from ..tools.tests import run_tests, verify_applied_html_files
from .policies import OrchestratorPolicy
from .stages import Stage, StageStatus
from .store import OrchestratorStore, get_store


class OrchestratorRunner:
    """Drive plan -> code -> test -> debug -> review -> complete transitions."""

    def __init__(self, store: OrchestratorStore | None = None):
        self.store = store or get_store()
        self.checkpoints = GitCheckpointService(self.store)
        self.diff_previews = DiffPreviewService(self.store)

    def start(self, task_id: str) -> dict[str, Any]:
        task = self.store.update_task_stage(task_id, Stage.PLAN)
        rules = self._resolve_and_store_rules(task.id)
        workspace = self._prepare_workspace(task.id)
        evidence = self._collect_search_evidence(task.id)
        plan = self.run_stage(
            task.id,
            Stage.PLAN,
            {"prompt": task.prompt, "attachments": self.store.list_attachments(task.id), "rules": rules, "workspace": workspace, "search_evidence": evidence},
        )
        if plan["status"] != StageStatus.PASSED.value:
            return plan
        plan["waiting_for_plan_approval"] = True
        plan["next_action"] = "approve_plan"
        return plan

    def approve_plan(self, task_id: str) -> dict[str, Any]:
        task = self._task(task_id)
        if task.stage != Stage.PLAN.value:
            raise ValueError(f"cannot approve PLAN while task is in {task.stage}")
        latest_plan = self._latest_stage_run(task_id, Stage.PLAN)
        if latest_plan is None or latest_plan.get("status") != StageStatus.PASSED.value:
            raise ValueError("latest PLAN run is not passed")
        self.store.update_task_stage(task_id, Stage.CODE)
        return self.enter_code(task_id)

    def enter_code(self, task_id: str) -> dict[str, Any]:
        halt = self._halt_if_budget_exhausted(task_id, Stage.CODE)
        if halt is not None:
            return halt
        task = self._task(task_id)
        checkpoint = self.checkpoints.create_checkpoint(task.id, task.repo_path, task.debug_attempts)
        attachments = self.store.list_attachments(task.id)
        rules = self.store.latest_task_rules(task.id) or self._resolve_and_store_rules(task.id)
        recommendation = self._model_selector().recommend(stage="coder")
        used, cap = self._stage_run_budget(task.id)
        input_data = {
            "checkpoint": checkpoint,
            "prompt": task.prompt,
            "attachments": attachments,
            "rules": rules,
            "execution": {
                "stage_runs_used": used,
                "max_stage_runs": cap,
                "debug_attempt": task.debug_attempts,
                "max_debug_attempts": task.max_debug_attempts,
            },
        }
        run = self.store.create_stage_run(task.id, Stage.CODE, recommendation.model, input_data, StageStatus.RUNNING)
        try:
            proposal = generate_code_changes(
                prompt=task.prompt,
                repo_path=task.repo_path,
                attachments=attachments,
                denied_paths=_extract_denied_paths(task.prompt),
                model=recommendation.model,
            )
            previews = []
            if not proposal.blocked_reason:
                for change in proposal.changes:
                    previews.append(
                        self.diff_previews.create_preview(
                            task_id=task.id,
                            repo_path=task.repo_path,
                            file_path=change.path,
                            content=change.content,
                            mode=change.mode,
                            denied_paths=_extract_denied_paths(task.prompt),
                        )
                    )
            output = {
                **proposal.to_dict(),
                "checkpoint": checkpoint,
                "diff_previews": previews,
                "waiting_for_approval": bool(previews),
            }
            status = StageStatus.BLOCKED if proposal.blocked_reason else StageStatus.PASSED
            self.store.finish_stage_run(run.id, status, output)
            return {
                "id": run.id,
                "task_id": task.id,
                "stage": Stage.CODE.value,
                "status": status.value,
                "model": proposal.model or recommendation.model,
                "output": output,
            }
        except Exception as exc:
            failure_output: dict[str, Any] = {
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                "checkpoint": checkpoint,
                "diff_previews": [],
                "waiting_for_approval": False,
                "summary": "Code generation crashed",
                "changes": [],
                "blocked_reason": None,
            }
            self.store.finish_stage_run(run.id, StageStatus.FAILED, failure_output)
            return {
                "id": run.id,
                "task_id": task.id,
                "stage": Stage.CODE.value,
                "status": StageStatus.FAILED.value,
                "model": recommendation.model,
                "output": failure_output,
            }

    def retry_code(self, task_id: str) -> dict[str, Any]:
        task = self._task(task_id)
        if task.stage != Stage.CODE.value:
            raise ValueError(f"cannot retry CODE while task is in {task.stage}")
        latest_code = self._latest_stage_run(task_id, Stage.CODE)
        if latest_code is None or latest_code.get("status") not in {
            StageStatus.BLOCKED.value,
            StageStatus.FAILED.value,
        }:
            raise ValueError("latest CODE run is not blocked or failed")
        return self.enter_code(task_id)

    def after_code(self, task_id: str, test_command: str | None = None) -> dict[str, Any]:
        if not self._phase_enabled(task_id, "TEST"):
            if self._phase_enabled(task_id, "REVIEW"):
                self.store.update_task_stage(task_id, Stage.REVIEW)
                return self.review(task_id)
            self.store.update_task_stage(task_id, Stage.COMPLETE)
            return {"task_id": task_id, "stage": Stage.COMPLETE.value, "status": StageStatus.PASSED.value, "skipped": ["TEST", "REVIEW"]}
        task = self.store.update_task_stage(task_id, Stage.TEST)
        context = ToolContext(task_id=task.id, repo_path=task.repo_path, confirmed=True)
        resolved_command = self._resolved_test_command(task_id, test_command) or self._fallback_verification_command(task_id)
        if resolved_command is None:
            html_run = verify_applied_html_files(task.id, task.repo_path, store=self.store)
            if html_run is not None:
                test_result = html_run
            else:
                test_result = self.store.insert_test_run(
                    {
                        "task_id": task.id,
                        "command": "",
                        "status": "skipped",
                        "exit_code": None,
                        "stdout": "",
                        "stderr": "No automated test harness detected for this repo type.",
                        "parsed_errors": [],
                        "duration_ms": 0,
                    }
                )
        else:
            test_result = run_tests(command=resolved_command, context=context)
        status = test_result.get("status")
        if status in {"passed", "skipped"}:
            if self._phase_enabled(task_id, "REVIEW"):
                self.store.update_task_stage(task_id, Stage.REVIEW)
                return self.review(task_id)
            self.store.update_task_stage(task_id, Stage.COMPLETE)
            return {"task_id": task_id, "stage": Stage.COMPLETE.value, "status": StageStatus.PASSED.value, "test_result": test_result}
        if status == "blocked":
            if self._phase_enabled(task_id, "REVIEW"):
                self.store.update_task_stage(task_id, Stage.REVIEW)
                return self.review(task_id)
            self.store.update_task_stage(task_id, Stage.COMPLETE)
            return {"task_id": task_id, "stage": Stage.COMPLETE.value, "status": StageStatus.BLOCKED.value, "test_result": test_result}
        if self._phase_enabled(task_id, "DEBUG") and task.debug_attempts < task.max_debug_attempts:
            if task.debug_attempts > 0 and self._is_repeat_failure(task_id):
                self.store.update_task_stage(task_id, Stage.FAILED)
                return {
                    "task_id": task_id,
                    "stage": Stage.FAILED.value,
                    "status": StageStatus.BLOCKED.value,
                    "test_result": test_result,
                    "halt_reason": "no_progress",
                    "summary": "The same test failure repeated after a debug attempt; stopping instead of burning the remaining attempts on an identical retry.",
                }
            self.store.update_task_stage(task_id, Stage.DEBUG)
            self.store.increment_debug_attempts(task_id)
            self._record_failure(test_result)
            return self.debug(task_id, test_result)
        self.store.update_task_stage(task_id, Stage.FAILED)
        return {"task_id": task_id, "stage": Stage.FAILED.value, "test_result": test_result}

    def debug(self, task_id: str, test_result: dict[str, Any]) -> dict[str, Any]:
        run = self.run_stage(task_id, Stage.DEBUG, {"test_result": test_result})
        if run.get("output", {}).get("halt_reason"):
            return run
        self.store.update_task_stage(task_id, Stage.CODE)
        return run

    def review(self, task_id: str) -> dict[str, Any]:
        task = self._task(task_id)
        diff = git_diff(repo_path=task.repo_path)
        run = self.run_stage(task_id, Stage.REVIEW, {"diff": diff})
        if run.get("output", {}).get("halt_reason"):
            return run
        approved = run.get("output", {}).get("approved", True)
        if approved:
            self.store.update_task_stage(task_id, Stage.COMPLETE)
            return run
        review_runs = sum(
            1 for item in self.store.timeline(task_id).get("stage_runs", []) if item.get("stage") == Stage.REVIEW.value
        )
        max_reviews = _config_int(task.model_config, "max_review_attempts", OrchestratorPolicy().max_review_attempts)
        if review_runs >= max_reviews:
            self.store.update_task_stage(task_id, Stage.FAILED)
            run["halt_reason"] = "review_attempts_exhausted"
            run["summary"] = (
                f"Review rejected the change {review_runs} times (limit {max_reviews}); "
                "stopping the review/code loop and surfacing the open findings."
            )
            return run
        self.store.update_task_stage(task_id, Stage.CODE)
        return run

    def run_stage(self, task_id: str, stage: Stage, input_data: dict[str, Any]) -> dict[str, Any]:
        halt = self._halt_if_budget_exhausted(task_id, stage)
        if halt is not None:
            return halt
        task = self._task(task_id)
        role = stage.value.lower()
        role = {"plan": "planner", "code": "coder", "debug": "debugger", "review": "reviewer"}.get(role, role)
        recommendation = self._model_selector().recommend(stage=role if role != "test" else "tester")
        used, cap = self._stage_run_budget(task_id)
        input_data = {**input_data, "execution": {"stage_runs_used": used, "max_stage_runs": cap}}
        run = self.store.create_stage_run(task_id, stage, recommendation.model, input_data, StageStatus.RUNNING)
        output, status = self._execute_non_code_stage(stage, input_data, recommendation.model)
        self.store.finish_stage_run(run.id, status, output)
        return {
            "id": run.id,
            "task_id": task_id,
            "stage": stage.value,
            "status": status.value,
            "model": recommendation.model,
            "output": output,
        }

    def _task(self, task_id: str):
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(f"task not found: {task_id}")
        return task

    def _stage_run_budget(self, task_id: str) -> tuple[int, int]:
        task = self._task(task_id)
        used = len(self.store.timeline(task_id).get("stage_runs", []))
        cap = _config_int(task.model_config, "max_stage_runs", OrchestratorPolicy().max_stage_runs)
        return used, cap

    def _halt_if_budget_exhausted(self, task_id: str, stage: Stage) -> dict[str, Any] | None:
        used, cap = self._stage_run_budget(task_id)
        if used < cap:
            return None
        task = self._task(task_id)
        if task.stage not in {Stage.COMPLETE.value, Stage.FAILED.value}:
            self.store.update_task_stage(task_id, Stage.FAILED)
        return {
            "id": None,
            "task_id": task_id,
            "stage": stage.value,
            "status": StageStatus.BLOCKED.value,
            "model": None,
            "output": {
                "halt_reason": "stage_run_budget_exhausted",
                "summary": (
                    f"Task stopped after {used} stage runs (budget {cap}). "
                    "Raise max_stage_runs in the task model_config only if the loop is genuinely making progress."
                ),
            },
        }

    def _is_repeat_failure(self, task_id: str) -> bool:
        failed = [run for run in self.store.timeline(task_id).get("test_runs", []) if run.get("status") == "failed"]
        if len(failed) < 2:
            return False
        current = _failure_signature(failed[-1])
        return bool(current) and current == _failure_signature(failed[-2])

    def _resolved_test_command(self, task_id: str, override: str | None) -> str | None:
        if override and override.strip():
            return override.strip()
        timeline = self.store.timeline(task_id)
        for run in reversed(timeline.get("stage_runs", [])):
            if run.get("stage") == Stage.CODE.value:
                out = run.get("output") or {}
                tc = out.get("test_command")
                if isinstance(tc, str) and tc.strip():
                    return tc.strip()
        return None

    def _latest_stage_run(self, task_id: str, stage: Stage) -> dict[str, Any] | None:
        for run in reversed(self.store.timeline(task_id).get("stage_runs", [])):
            if run.get("stage") == stage.value:
                return run
        return None

    def _fallback_verification_command(self, task_id: str) -> str | None:
        py_files = []
        for diff in self.store.list_diff_previews(task_id):
            if diff.get("status") == "applied" and str(diff.get("file_path", "")).lower().endswith(".py"):
                py_files.append(_quote_path(str(Path(diff["file_path"]))))
        if py_files:
            return f"python -m py_compile {' '.join(py_files)}"
        return None

    def _model_selector(self) -> ModelSelector:
        config = self.store.get_model_role_config("default") or {}
        overrides = {
            role: config[role]
            for role in ("planner", "coder", "tester", "debugger", "reviewer")
            if isinstance(config.get(role), str) and config.get(role)
        }
        return ModelSelector(role_overrides=overrides)

    def _phase_enabled(self, task_id: str, phase: str) -> bool:
        task = self._task(task_id)
        configured = task.model_config.get("enabled_phases") if isinstance(task.model_config, dict) else None
        if not isinstance(configured, list) or not configured:
            return True
        return phase.upper() in {str(item).upper() for item in configured}

    def _resolve_and_store_rules(self, task_id: str) -> dict[str, Any]:
        task = self._task(task_id)
        config = task.model_config if isinstance(task.model_config, dict) else {}
        raw_packs = config.get("enabled_packs")
        if raw_packs is None:
            enabled_packs_arg: list[str] | None = None
        elif isinstance(raw_packs, list):
            enabled_packs_arg = [str(item) for item in raw_packs]
        else:
            enabled_packs_arg = None
        resolved = resolve_rules(
            task.repo_path,
            enabled_packs=enabled_packs_arg,
            task_rules=str(config.get("task_rules", "")) if config.get("task_rules") else None,
            temporary_instruction=task.prompt,
        ).to_dict()
        self.store.insert_task_rules(task_id, task.repo_path, resolved)
        return resolved

    def _collect_search_evidence(self, task_id: str) -> list[dict[str, Any]]:
        task = self._task(task_id)
        queries = [task.prompt.splitlines()[0][:80] or "TODO", "TODO|FIXME"]
        kinds = ["text", "todo"]
        evidence = []
        for query, kind in zip(queries, kinds):
            try:
                result = search_repo(query, kind=kind, limit=20, repo_path=task.repo_path, task_id="manual")
            except Exception as exc:
                result = {"matches": [], "count": 0, "error": str(exc)}
            record = self.store.insert_search_evidence(task_id, task.repo_path, query, kind, result.get("matches", []))
            evidence.append(record)
        return evidence

    def _prepare_workspace(self, task_id: str) -> dict[str, Any]:
        task = self._task(task_id)
        branch = "current working tree"
        try:
            result = subprocess.run(["git", "branch", "--show-current"], cwd=task.repo_path, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
        except Exception:
            pass
        return self.store.insert_worktree_record(task_id, task.repo_path, task.repo_path, branch, "current")

    def _execute_non_code_stage(self, stage: Stage, input_data: dict[str, Any], model: str) -> tuple[dict[str, Any], StageStatus]:
        if stage == Stage.PLAN:
            return self._plan_output(input_data, model), StageStatus.PASSED
        if stage == Stage.DEBUG:
            return self._debug_output(input_data, model), StageStatus.PASSED
        if stage == Stage.REVIEW:
            output = self._review_output(input_data, model)
            return output, StageStatus.PASSED if output.get("approved") else StageStatus.BLOCKED
        return {"model": model, "summary": f"{stage.value} completed."}, StageStatus.PASSED

    def _plan_output(self, input_data: dict[str, Any], model: str) -> dict[str, Any]:
        prompt = str(input_data.get("prompt", "")).strip()
        rules = input_data.get("rules", {}) if isinstance(input_data.get("rules"), dict) else {}
        evidence = input_data.get("search_evidence", []) if isinstance(input_data.get("search_evidence"), list) else []
        files = sorted({
            str(match.get("path", ""))
            for item in evidence
            for match in item.get("results", [])
            if isinstance(match, dict) and match.get("path")
        })
        fallback = {
            "summary": _first_sentence(prompt) or "Plan the requested repository change.",
            "items": [
                "Inspect the most relevant files before proposing edits.",
                "Apply active project rules and denied-path constraints.",
                "Create a git checkpoint before CODE writes any preview.",
                "Generate diff previews and wait for approval before applying files.",
                "Run the enabled verification and review phases after approval.",
            ],
            "files_considered": files[:20],
            "rules_summary": rules.get("summary", []),
            "search_evidence": evidence,
            "model": model,
            "source": "local-planner",
        }
        modeled = self._try_stage_model(
            model,
            "Return JSON with summary, items, files_considered, risks, and assumptions for this planning stage.",
            {"prompt": prompt, "rules": rules, "search_evidence": evidence, "fallback": fallback},
        )
        if modeled:
            return {**fallback, **modeled, "model": model, "source": "model-planner"}
        return fallback

    def _debug_output(self, input_data: dict[str, Any], model: str) -> dict[str, Any]:
        test_result = input_data.get("test_result", {}) if isinstance(input_data.get("test_result"), dict) else {}
        errors = test_result.get("parsed_errors") or []
        command = str(test_result.get("command") or "")
        guidance = []
        for error in errors[:5]:
            message = str(error.get("message") or error.get("signature") or "Test failure") if isinstance(error, dict) else str(error)
            guidance.append(f"Investigate: {message}")
        if not guidance and test_result.get("stderr"):
            guidance.append(str(test_result["stderr"]).splitlines()[0][:200])
        fallback = {
            "summary": "Debug the failing verification result." if guidance else "No structured failure was available to debug.",
            "debug_guidance": guidance,
            "command": command,
            "parsed_errors": errors,
            "next_code_focus": guidance[:3],
            "model": model,
            "source": "local-debugger",
        }
        modeled = self._try_stage_model(
            model,
            "Return JSON with summary, debug_guidance, likely_causes, and next_code_focus for this debug stage.",
            {"test_result": test_result, "fallback": fallback},
        )
        if modeled:
            return {**fallback, **modeled, "model": model, "source": "model-debugger"}
        return fallback

    def _review_output(self, input_data: dict[str, Any], model: str) -> dict[str, Any]:
        diff = str(input_data.get("diff") or "")
        findings = _review_findings(diff)
        risk = assess_file_change("working tree", diff) if diff else {"risk_level": "Low", "approval_reason": "No diff", "patch_summary": ""}
        approved = not any(item.get("severity") == "high" for item in findings)
        fallback = {
            "approved": approved,
            "findings": findings,
            "required_changes": [item["message"] for item in findings if item.get("severity") == "high"],
            "risk_level": risk.get("risk_level", "Low"),
            "approval_reason": risk.get("approval_reason", ""),
            "patch_summary": risk.get("patch_summary", ""),
            "model": model,
            "source": "local-reviewer",
        }
        modeled = self._try_stage_model(
            model,
            "Return JSON with approved, findings, required_changes, risk_level, and patch_summary for this review stage.",
            {"diff": diff[:20000], "fallback": fallback},
        )
        if modeled:
            merged = {**fallback, **modeled, "model": model, "source": "model-reviewer"}
            merged["approved"] = bool(merged.get("approved")) and not fallback["required_changes"]
            return merged
        return fallback

    @staticmethod
    def _try_stage_model(model: str, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = request_code_json_with_usage(model, system_prompt, _json_for_model(payload))
        except (ModelNotConfigured, ModelResponseError):
            return None
        raw = response.get("json")
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _record_failure(test_result: dict[str, Any]) -> None:
        parsed_errors = test_result.get("parsed_errors") or []
        if not parsed_errors:
            return
        first = parsed_errors[0]
        try:
            record_failure_pattern(
                error_signature=first.get("signature", ""),
                exception_type=first.get("type", "test_failure"),
                error_message=first.get("message", ""),
                stack_frames=[first.get("signature", "")],
                resolution="",
                tags=["automated-test-loop"],
            )
        except Exception:
            pass


def _config_int(config: Any, key: str, default: int) -> int:
    if not isinstance(config, dict) or config.get(key) is None:
        return default
    try:
        value = int(config[key])
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _failure_signature(test_run: dict[str, Any]) -> str:
    errors = test_run.get("parsed_errors") or []
    if errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get("signature") or first.get("message") or "")
        return str(first)
    stderr = str(test_run.get("stderr") or "")
    return stderr.splitlines()[0][:200] if stderr else ""


def _extract_denied_paths(prompt: str) -> list[str]:
    defaults = [".env", ".env.local", "secrets.json"]
    marker = "Never touch these files:"
    if marker not in prompt:
        return defaults
    tail = prompt.split(marker, 1)[1].splitlines()[0]
    parsed = [item.strip() for item in tail.split(",") if item.strip()]
    return parsed or defaults


def _quote_path(path: str) -> str:
    return '"' + path.replace('"', '\\"') + '"'


def _first_sentence(text: str) -> str:
    first = text.splitlines()[0].strip() if text else ""
    return first[:180]


def _json_for_model(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, default=str)


def _review_findings(diff: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not diff.strip():
        return findings
    lowered = diff.lower()
    sensitive_markers = ("openai_api_key", "api_key=", "password=", "secret=", "token=")
    for marker in sensitive_markers:
        if marker in lowered:
            findings.append({"severity": "high", "message": f"Diff appears to introduce sensitive value marker `{marker}`."})
    if "\n+<<<<<<<" in diff or "\n+=======" in diff or "\n+>>>>>>>" in diff:
        findings.append({"severity": "high", "message": "Diff appears to include unresolved merge conflict markers."})
    removed_lines = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    if removed_lines > 250:
        findings.append({"severity": "medium", "message": f"Large deletion detected ({removed_lines} removed lines); review carefully."})
    return findings

