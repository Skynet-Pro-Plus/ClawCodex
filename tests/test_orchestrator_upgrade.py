from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.engine.attachments.store import AttachmentStore
from src.engine.orchestrator.runner import OrchestratorRunner
from src.engine.orchestrator.stages import Stage, StageStatus
from src.engine.orchestrator.store import OrchestratorStore
from src.engine.project.memory import ProjectMemoryStore
from src.engine.project.repo_map import RepoMapBuilder
from src.engine.project.scanner import ProjectScanner
from src.engine.routing.model_selector import ModelSelector
from src.engine.rules import list_packs, resolve_rules
from src.engine.rules.loader import load_rule_sources
from src.engine.safety.destructive_ops import SafetyPolicy, SafetyViolation
from src.engine.safety.diff_preview import DiffPreviewService
from src.engine.safety.git_checkpoints import GitCheckpointService
from src.engine.safety.rollback import RollbackService
from src.engine.problems import parse_diagnostics
from src.engine.settings.local_config import clear_model_key, get_model_key, model_key_status, save_model_key
from src.engine.tools.search import search_repo
from src.engine.tools.base import ToolContext
from src.engine.tools.tests import run_tests
from src.engine.coding.code_generator import (
    CodeGenerationResult,
    ProposedChange,
    _validate_result,
    generate_code_changes,
)


class OrchestratorUpgradeTests(unittest.TestCase):
    def test_diff_preview_requires_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            target = repo / "app.py"
            target.write_text("print('old')\n", encoding="utf-8")
            store = OrchestratorStore(repo / "orch.db")
            preview = DiffPreviewService(store).create_preview("task-1", str(repo), "app.py", "print('new')\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "print('old')\n")
            self.assertIn("-print('old')", preview["unified_diff"])
            DiffPreviewService(store).approve(preview["id"])
            self.assertEqual(target.read_text(encoding="utf-8"), "print('new')\n")
            store.close()

    def test_destructive_commands_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = SafetyPolicy(tmp)
            for command in ["rm -rf src", "git reset --hard HEAD", "Remove-Item src -Recurse"]:
                with self.subTest(command=command):
                    with self.assertRaises(SafetyViolation):
                        policy.check_command(command, confirmed=True)

    def test_git_checkpoint_and_rollback_restore_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            target = repo / "app.py"
            target.write_text("old\n", encoding="utf-8")
            self._git(repo, "add app.py")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            checkpoint = GitCheckpointService(store).create_checkpoint("task-1", str(repo), 0)
            target.write_text("new\n", encoding="utf-8")
            result = RollbackService(store).rollback("task-1", checkpoint["id"])
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(result["task_id"], "task-1")
            store.close()

    def test_project_scan_ignores_heavy_dependency_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "package.json").write_text('{"dependencies":{"react":"latest"}}', encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "main.ts").write_text("export const value = 1\n", encoding="utf-8")
            (repo / "node_modules" / "large").mkdir(parents=True)
            (repo / "node_modules" / "large" / "ignored.py").write_text("raise AssertionError('scanner should not recurse here')\n", encoding="utf-8")

            data = ProjectScanner().scan(str(repo), force_refresh=True)

            self.assertIn("TypeScript", data["languages"])
            self.assertIn("React", data["frameworks"])
            self.assertNotIn("Python", data["languages"])

    def test_project_scan_and_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "package.json").write_text('{"scripts":{"test":"vitest"},"dependencies":{"react":"latest"}}', encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "main.ts").write_text("export const x = 1\n", encoding="utf-8")
            data = RepoMapBuilder().build(str(repo), force_refresh=True)
            self.assertIn("TypeScript", data["languages"])
            self.assertIn("React", data["frameworks"])
            self.assertTrue(data["test_commands"])
            store = OrchestratorStore(repo / "orch.db")
            memory = ProjectMemoryStore(store).add(str(repo), "style", "Use small modules", ["scan"])
            self.assertEqual(memory["kind"], "style")
            self.assertEqual(len(ProjectMemoryStore(store).list(str(repo))), 1)
            store.close()

    def test_role_routing_uses_openrouter_presets(self) -> None:
        selector = ModelSelector()
        self.assertTrue(selector.recommend("planner").model.startswith("anthropic/"))
        self.assertTrue(selector.recommend("coder").model.startswith("openai/"))
        self.assertTrue(selector.recommend("reviewer").fallback_model.startswith("anthropic/"))

    def test_run_tests_stores_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            tests = repo / "tests"
            tests.mkdir()
            (tests / "test_fail.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.assertEqual(1, 2)\n",
                encoding="utf-8",
            )
            result = run_tests(
                command="python -m unittest discover -s tests -v",
                context=ToolContext(task_id="task-1", repo_path=str(repo), confirmed=True),
            )
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["parsed_errors"])

    def test_runner_records_plan_and_code_checkpoint_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
            self._git(repo, "add app.py")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "Build a Windows Python GUI that says hello world")
            runner = OrchestratorRunner(store)
            result = runner.start(task.id)
            self.assertEqual(result["stage"], Stage.PLAN.value)
            self.assertTrue(result["waiting_for_plan_approval"])
            self.assertFalse(store.list_checkpoints(task.id))
            code = runner.approve_plan(task.id)
            self.assertEqual(code["stage"], Stage.CODE.value)
            self.assertTrue(store.list_checkpoints(task.id))
            store.close()

    def test_runner_generates_diff_preview_for_python_gui_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "Build a Windows Python GUI that says hello world")
            runner = OrchestratorRunner(store)
            result = runner.start(task.id)
            self.assertEqual(result["stage"], Stage.PLAN.value)
            result = runner.approve_plan(task.id)
            previews = store.list_diff_previews(task.id)
            self.assertEqual(result["stage"], Stage.CODE.value)
            self.assertEqual(len(previews), 1)
            self.assertIn("hello_world_gui.py", previews[0]["file_path"])
            self.assertFalse((repo / "hello_world_gui.py").exists())
            DiffPreviewService(store).approve_all(task.id)
            self.assertTrue((repo / "hello_world_gui.py").exists())
            store.close()

    def test_runner_rejects_plan_approval_outside_plan_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "Build a Windows Python GUI that says hello world")
            with self.assertRaisesRegex(ValueError, "cannot approve PLAN"):
                OrchestratorRunner(store).approve_plan(task.id)
            store.close()

    def test_runner_uses_saved_role_model_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            store.set_model_role_config(
                "default",
                {
                    "planner": "anthropic/claude-sonnet-4",
                    "coder": "openai/gpt-4.1-mini",
                    "tester": "openai/gpt-4.1-mini",
                    "debugger": "anthropic/claude-sonnet-4",
                    "reviewer": "anthropic/claude-sonnet-4",
                    "budget_usd": None,
                    "optimize_for": "balanced",
                },
            )
            task = store.create_task(str(repo), "Build a Windows Python GUI that says hello world")
            OrchestratorRunner(store).start(task.id)
            plan_runs = [run for run in store.timeline(task.id)["stage_runs"] if run["stage"] == Stage.PLAN.value]
            self.assertEqual(plan_runs[-1]["model"], "anthropic/claude-sonnet-4")
            store.close()

    def test_runner_can_skip_test_phase_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(
                str(repo),
                "Build a Windows Python GUI that says hello world",
                model_config={"enabled_phases": ["PLAN", "CODE", "REVIEW"]},
            )
            runner = OrchestratorRunner(store)
            runner.start(task.id)
            runner.approve_plan(task.id)
            DiffPreviewService(store).approve_all(task.id)
            result = runner.after_code(task.id)
            timeline = store.timeline(task.id)
            self.assertEqual(result["stage"], Stage.REVIEW.value)
            self.assertEqual(timeline["task"]["stage"], Stage.COMPLETE.value)
            self.assertFalse(timeline["test_runs"])
            store.close()

    def test_runner_marks_verification_skipped_when_no_safe_command_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "make html")
            DiffPreviewService(store).create_preview(task.id, str(repo), "notes.txt", "hello\n", mode="create")
            store.update_task_stage(task.id, Stage.PLAN)
            store.update_task_stage(task.id, Stage.CODE)
            DiffPreviewService(store).approve_all(task.id)
            OrchestratorRunner(store).after_code(task.id)
            timeline = store.timeline(task.id)
            self.assertEqual(timeline["test_runs"][-1]["status"], "skipped")
            self.assertIn("No automated test harness", timeline["test_runs"][-1]["stderr"])
            self.assertEqual(timeline["task"]["stage"], Stage.COMPLETE.value)
            store.close()

    def test_runner_verifies_applied_html_with_safe_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            try:
                task = store.create_task(str(repo), "make html")
                DiffPreviewService(store).create_preview(task.id, str(repo), "hello.html", "<h1>Hello</h1>\n", mode="create")
                store.update_task_stage(task.id, Stage.PLAN)
                store.update_task_stage(task.id, Stage.CODE)
                DiffPreviewService(store).approve_all(task.id)
                OrchestratorRunner(store).after_code(task.id)
                timeline = store.timeline(task.id)
                self.assertEqual(timeline["test_runs"][-1]["status"], "passed")
                self.assertEqual(timeline["task"]["stage"], Stage.COMPLETE.value)
            finally:
                store.close()

    def test_run_tests_skipped_when_no_harness_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_tests(context=ToolContext(task_id="task-x", repo_path=str(Path(tmp)), confirmed=True))
            self.assertEqual(result["status"], "skipped")
            self.assertIn("No automated test harness", result["stderr"])

    def test_validate_result_maps_create_to_replace_when_target_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            target = repo / "existing.txt"
            target.write_text("old\n", encoding="utf-8")
            result = CodeGenerationResult(
                summary="test",
                changes=[ProposedChange(path=str(target), mode="create", content="new\n")],
            )
            out = _validate_result(result, str(repo), None)
            self.assertEqual(len(out.changes), 1)
            self.assertEqual(out.changes[0].mode, "replace")

    def test_generate_code_changes_local_html_replace_when_hello_html_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "hello.html").write_text("<html><body>old</body></html>", encoding="utf-8")
            out = generate_code_changes("build a hello world html", str(repo))
            self.assertEqual(out.model, "local-template")
            self.assertEqual(len(out.changes), 1)
            self.assertTrue(str(out.changes[0].path).replace("\\", "/").endswith("hello.html"))
            self.assertEqual(out.changes[0].mode, "replace")

    def test_generate_code_changes_local_html_create_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            out = generate_code_changes("build a hello world html", str(repo))
            self.assertEqual(out.model, "local-template")
            self.assertEqual(out.changes[0].mode, "create")

    def test_enter_code_passes_when_hello_html_exists_for_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            (repo / "hello.html").write_text("<html><body>legacy</body></html>", encoding="utf-8")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "build a hello world html")
            store.update_task_stage(task.id, Stage.PLAN)
            store.update_task_stage(task.id, Stage.CODE)
            result = OrchestratorRunner(store).enter_code(task.id)
            self.assertEqual(result["status"], StageStatus.PASSED.value)
            previews = store.list_diff_previews(task.id)
            self.assertEqual(len(previews), 1)
            self.assertEqual(previews[0]["status"], "pending")
            store.close()

    def test_delete_task_removes_task_scoped_timeline_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "cleanup stale mission")
            store.create_stage_run(task.id, Stage.PLAN, "test-model")
            store.record_tool_call(task.id, "tool", "passed", {}, {})
            store.insert_checkpoint(
                {
                    "task_id": task.id,
                    "repo_path": str(repo),
                    "head_sha": "abc",
                    "checkpoint_ref": "refs/claw/checkpoints/test",
                    "dirty_patch_path": None,
                }
            )
            preview = DiffPreviewService(store).create_preview(task.id, str(repo), "hello.txt", "hello\n", mode="create")
            store.insert_test_run({"task_id": task.id, "command": "", "status": "skipped", "exit_code": None, "stdout": "", "stderr": "", "parsed_errors": [], "duration_ms": 0})
            store.insert_task_rules(task.id, str(repo), {"sources": [], "summary": ["rule"], "merged_content": ""})
            store.record_rule_decision(task.id, "decision", [])
            store.insert_search_evidence(task.id, str(repo), "query", "text", [])
            store.insert_diagnostic(task.id, {"file": "hello.txt", "severity": "warning", "source": "test", "message": "demo"})
            store.insert_worktree_record(task.id, str(repo), str(repo), "main", "current")
            self.assertTrue(store.get_task(task.id))
            self.assertTrue(store.list_diff_hunks(preview_id=preview["id"]))
            self.assertTrue(store.delete_task(task.id))
            self.assertIsNone(store.get_task(task.id))
            self.assertFalse(store.delete_task(task.id))
            conn = store._connection()
            for table in (
                "stage_runs",
                "tool_calls",
                "git_checkpoints",
                "diff_previews",
                "diff_hunks",
                "test_runs",
                "task_rules",
                "rule_decisions",
                "search_evidence",
                "diagnostics",
                "worktree_records",
            ):
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE task_id = ?", (task.id,)).fetchone()
                self.assertEqual(row["count"], 0, table)
            store.close()

    def test_enter_code_finishes_failed_when_generation_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "Build a minimal hello world HTML page")
            store.update_task_stage(task.id, Stage.PLAN)
            store.update_task_stage(task.id, Stage.CODE)
            with patch("src.engine.orchestrator.runner.generate_code_changes", side_effect=RuntimeError("simulated boom")):
                result = OrchestratorRunner(store).enter_code(task.id)
            self.assertEqual(result["status"], StageStatus.FAILED.value)
            self.assertEqual(result["output"].get("error_type"), "RuntimeError")
            timeline = store.timeline(task.id)
            code_runs = [r for r in timeline["stage_runs"] if r["stage"] == Stage.CODE.value]
            self.assertTrue(code_runs)
            self.assertEqual(code_runs[-1]["status"], StageStatus.FAILED.value)
            store.close()

    def test_runner_retries_blocked_code_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "Build a Windows Python GUI that says hello world")
            store.update_task_stage(task.id, Stage.PLAN)
            store.update_task_stage(task.id, Stage.CODE)
            run = store.create_stage_run(task.id, Stage.CODE, "openrouter/test-model")
            store.finish_stage_run(run.id, StageStatus.BLOCKED, {"blocked_reason": "OpenRouter authentication failed"})
            result = OrchestratorRunner(store).retry_code(task.id)
            previews = store.list_diff_previews(task.id)
            self.assertEqual(result["stage"], Stage.CODE.value)
            self.assertEqual(result["status"], StageStatus.PASSED.value)
            self.assertEqual(len(previews), 1)
            store.close()

    def test_rules_search_risk_hunks_and_diagnostics_are_timeline_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "CLAWRULES.md").write_text("Always run tests before completion.\n", encoding="utf-8")
            (repo / "app.py").write_text("print('old')\n# TODO: improve\n", encoding="utf-8")
            self._git(repo, "add app.py CLAWRULES.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            try:
                task = store.create_task(str(repo), "Update app")
                resolved = resolve_rules(str(repo)).to_dict()
                store.insert_task_rules(task.id, str(repo), resolved)
                result = search_repo("TODO", "todo", 10, repo_path=str(repo), task_id="manual")
                store.insert_search_evidence(task.id, str(repo), "TODO", "todo", result["matches"])
                preview = DiffPreviewService(store).create_preview(task.id, str(repo), "auth.py", "SECRET = 'demo'\n", mode="create")
                diagnostics = parse_diagnostics("app.ts:1:1 - error TS1000: bad\n")
                for diagnostic in diagnostics:
                    store.insert_diagnostic(task.id, diagnostic)
                timeline = store.timeline(task.id)
                self.assertTrue(timeline["rules"]["summary"])
                self.assertTrue(timeline["search_evidence"][0]["results"])
                self.assertEqual(preview["risk_level"], "High")
                self.assertTrue(timeline["diff_hunks"])
                self.assertEqual(timeline["diagnostics"][0]["source"], "typescript")
            finally:
                store.close()

    def test_pack_rules_none_includes_all_pack_dirs_empty_list_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack_root = repo / "clawcodex-packs" / "demo-pack"
            pack_root.mkdir(parents=True)
            (pack_root / "rules.md").write_text("# Demo pack\n", encoding="utf-8")
            none_filter = load_rule_sources(str(repo), enabled_packs=None)
            self.assertTrue(any(getattr(s, "scope", "") == "pack" for s in none_filter))
            empty_filter = load_rule_sources(str(repo), enabled_packs=[])
            self.assertFalse(any(getattr(s, "scope", "") == "pack" for s in empty_filter))

    def test_pack_catalog_finds_starter_packs(self) -> None:
        packs = list_packs(str(Path(__file__).resolve().parents[1]))
        ids = {pack["id"] for pack in packs}
        self.assertIn("python-testing", ids)
        self.assertIn("industrial-controls", ids)

    def test_attachment_store_links_files_to_task_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = OrchestratorStore(repo / "orch.db")
            task = store.create_task(str(repo), "analyze screenshot")
            attachment_store = AttachmentStore(store, root=repo / ".claw" / "attachments")
            source = repo / "note.txt"
            source.write_text("make the UI safer", encoding="utf-8")
            with source.open("rb") as handle:
                attachment = attachment_store.save(handle, "note.txt", "text/plain")
            linked = attachment_store.link_to_task(task.id, attachment.id)
            timeline = store.timeline(task.id)
            self.assertEqual(linked.task_id, task.id)
            self.assertEqual(timeline["attachments"][0]["filename"], "note.txt")
            self.assertEqual(timeline["attachments"][0]["analysis"]["kind"], "text")
            store.close()

    def test_model_key_status_save_and_clear_without_exposing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old_dir = os.environ.get("CLAWCODEX_CONFIG_DIR")
            old_openrouter = os.environ.pop("OPENROUTER_API_KEY", None)
            old_openai = os.environ.pop("OPENAI_API_KEY", None)
            os.environ["CLAWCODEX_CONFIG_DIR"] = tmp
            try:
                self.assertEqual(model_key_status()["source"], "none")
                saved = save_model_key("sk-or-test-value")
                self.assertTrue(saved["configured"])
                self.assertEqual(saved["source"], "local_config")
                self.assertNotIn("sk-or-test-value", str(saved))
                self.assertEqual(get_model_key(), "sk-or-test-value")
                cleared = clear_model_key()
                self.assertFalse(cleared["configured"])
            finally:
                if old_dir is None:
                    os.environ.pop("CLAWCODEX_CONFIG_DIR", None)
                else:
                    os.environ["CLAWCODEX_CONFIG_DIR"] = old_dir
                if old_openrouter is not None:
                    os.environ["OPENROUTER_API_KEY"] = old_openrouter
                if old_openai is not None:
                    os.environ["OPENAI_API_KEY"] = old_openai

    def test_saved_openrouter_key_takes_precedence_over_openai_compat_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old_dir = os.environ.get("CLAWCODEX_CONFIG_DIR")
            old_openrouter = os.environ.pop("OPENROUTER_API_KEY", None)
            old_openai = os.environ.get("OPENAI_API_KEY")
            os.environ["CLAWCODEX_CONFIG_DIR"] = tmp
            os.environ["OPENAI_API_KEY"] = "stale-openai-compatible-key"
            try:
                save_model_key("sk-or-user-saved-key")
                self.assertEqual(model_key_status()["source"], "local_config")
                self.assertEqual(get_model_key(), "sk-or-user-saved-key")
            finally:
                if old_dir is None:
                    os.environ.pop("CLAWCODEX_CONFIG_DIR", None)
                else:
                    os.environ["CLAWCODEX_CONFIG_DIR"] = old_dir
                if old_openrouter is not None:
                    os.environ["OPENROUTER_API_KEY"] = old_openrouter
                if old_openai is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old_openai

    def test_validate_openrouter_key_rejects_empty_before_save(self) -> None:
        from src.engine.coding.openrouter_client import ModelNotConfigured, validate_openrouter_key

        with self.assertRaises(ModelNotConfigured):
            validate_openrouter_key("")

    def test_review_loop_fails_after_max_review_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config user.email test@example.com")
            self._git(repo, "config user.name Test")
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            self._git(repo, "add README.md")
            self._git(repo, "commit -m init")
            store = OrchestratorStore(repo / "orch.db")
            try:
                task = store.create_task(str(repo), "change with findings")
                store.update_task_stage(task.id, Stage.PLAN)
                store.update_task_stage(task.id, Stage.CODE)
                store.update_task_stage(task.id, Stage.REVIEW)
                runner = OrchestratorRunner(store)
                rejected_diff = "+password=hunter2\n"
                with patch("src.engine.orchestrator.runner.git_diff", return_value=rejected_diff):
                    first = runner.review(task.id)
                    self.assertNotIn("halt_reason", first)
                    self.assertEqual(store.get_task(task.id).stage, Stage.CODE.value)
                    store.update_task_stage(task.id, Stage.REVIEW)
                    second = runner.review(task.id)
                self.assertEqual(second.get("halt_reason"), "review_attempts_exhausted")
                self.assertEqual(store.get_task(task.id).stage, Stage.FAILED.value)
            finally:
                store.close()

    def test_stage_run_budget_halts_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = OrchestratorStore(repo / "orch.db")
            try:
                task = store.create_task(str(repo), "tiny budget", model_config={"max_stage_runs": 1})
                store.update_task_stage(task.id, Stage.PLAN)
                store.update_task_stage(task.id, Stage.CODE)
                run = store.create_stage_run(task.id, Stage.PLAN, "test-model")
                store.finish_stage_run(run.id, StageStatus.PASSED, {})
                result = OrchestratorRunner(store).enter_code(task.id)
                self.assertEqual(result["output"]["halt_reason"], "stage_run_budget_exhausted")
                self.assertEqual(result["status"], StageStatus.BLOCKED.value)
                self.assertEqual(store.get_task(task.id).stage, Stage.FAILED.value)
                self.assertFalse(store.list_checkpoints(task.id))
            finally:
                store.close()

    def test_repeat_failure_detection_compares_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = OrchestratorStore(repo / "orch.db")
            try:
                task = store.create_task(str(repo), "loop guard")
                runner = OrchestratorRunner(store)
                base = {"task_id": task.id, "command": "pytest", "exit_code": 1, "stdout": "", "stderr": "", "duration_ms": 1}
                store.insert_test_run({**base, "status": "failed", "parsed_errors": [{"signature": "AssertionError: 1 != 2"}]})
                self.assertFalse(runner._is_repeat_failure(task.id))
                store.insert_test_run({**base, "status": "failed", "parsed_errors": [{"signature": "AssertionError: 1 != 2"}]})
                self.assertTrue(runner._is_repeat_failure(task.id))
                store.insert_test_run({**base, "status": "failed", "parsed_errors": [{"signature": "TypeError: bad call"}]})
                self.assertFalse(runner._is_repeat_failure(task.id))
            finally:
                store.close()

    def test_run_tests_blocked_when_runner_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.engine.tools.tests.shutil.which", return_value=None):
                result = run_tests(
                    command="python -m pytest -q",
                    context=ToolContext(task_id="task-y", repo_path=str(Path(tmp)), confirmed=True),
                )
            self.assertEqual(result["status"], "blocked")
            self.assertIn("not installed", result["stderr"])

    @staticmethod
    def _git(repo: Path, command: str) -> None:
        result = subprocess.run(["git", *command.split()], cwd=repo, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stderr)


if __name__ == "__main__":
    unittest.main()
