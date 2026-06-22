# Repository tree and purpose

This file is a **map of the repository layout** and **what each major area is for**. It complements [`README.md`](README.md), [`USAGE.md`](USAGE.md), and [`rust/README.md`](rust/README.md), which stay the task-oriented entry points.

**Canonical tracked paths** (280 files as of generation) are listed verbatim in [Appendix A](#appendix-a-all-git-tracked-paths-sorted). Anything that exists on disk but **not** in that list is **local or untracked**; see [Appendix B](#appendix-b-notable-paths-on-disk-but-not-in-git).

---

## At-a-glance layout

```text
ClawCodex/
+-- .github/              CI, releases, doc checks
+-- .claude/              IDE/agent session JSON (tracked in this clone)
+-- assets/               README / marketing images
+-- docs/                 Extra guides (container, model compatibility)
+-- rust/                 Canonical Rust workspace; builds `claw` binary
+-- src/                  Companion Python / reference + parity audit helpers
+-- tests/                Python tests for porting workspace
+-- README.md, USAGE.md, PARITY.md, ROADMAP.md, PHILOSOPHY.md, CLAUDE.md
+-- Containerfile, install.sh, prd.json, progress.txt
+-- (local) launch.bat, launch.ps1, SPEC.md, Demos/, tool_audit/, ...
```

---

## Root files (tracked)

| Path | Role |
|------|------|
| `README.md` | Project overview, quick start, links to usage and Rust workspace. |
| `USAGE.md` | End-user workflows: build, auth, CLI, sessions, parity harness. |
| `PARITY.md` | Repo-root parity / migration checkpoint narrative vs legacy surface. |
| `rust/PARITY.md` | Rust-specific parity notes (may overlap with root). |
| `ROADMAP.md` | Roadmap and backlog. |
| `PHILOSOPHY.md` | Design intent and framing. |
| `CLAUDE.md` | Guidance for Claude / agent context when working in-repo. |
| `Containerfile` | OCI image build for container-first workflows; see `docs/container.md`. |
| `install.sh` | Shell installer helper for supported environments. |
| `prd.json` | Product requirements / metadata artifact. |
| `progress.txt` | Progress log / scratch status (lightweight). |
| `.gitignore` | Git ignore rules. |
| `.claude.json` | Claude Code / agent configuration for this workspace. |

---

## `.github/`

| Path | Role |
|------|------|
| `workflows/rust-ci.yml` | Rust workspace CI (build, test, lint as configured). |
| `workflows/release.yml` | Release automation. |
| `scripts/check_doc_source_of_truth.py` | Validates docs against expected sources of truth. |
| `FUNDING.yml` | GitHub Sponsors / funding metadata. |

---

## `docs/`

| Path | Role |
|------|------|
| `container.md` | How to build and run using the container workflow. |
| `MODEL_COMPATIBILITY.md` | Model/provider compatibility notes. |

---

## `assets/`

Static images for README, social proof, and documentation (hero image, screenshots, star history, etc.). Not runtime code.

---

## `rust/` - canonical implementation

The **primary product** is the Rust workspace under `rust/`. It builds the **`claw`** binary from the `rusty-claude-cli` crate (`[[bin]] name = "claw"`).

| Path / area | Role |
|-------------|------|
| `Cargo.toml` / `Cargo.lock` | Workspace manifest and lockfile; members = `crates/*`. |
| `README.md`, `USAGE.md` | Rust-centric quick start and usage (mirrors/overlaps root docs). |
| `MOCK_PARITY_HARNESS.md`, `mock_parity_scenarios.json` | Mock parity harness documentation and scenario manifest. |
| `scripts/run_mock_parity_harness.sh` | Wrapper to run deterministic mock parity checks. |
| `scripts/run_mock_parity_diff.py` | Scenario checklist and PARITY mapping runner. |
| `PARITY.md` | Rust workspace parity status. |
| `TUI-ENHANCEMENT-PLAN.md` | Planning notes for TUI work. |
| `.gitignore` | Rust subtree ignore rules. |
| `.claude/`, `.claw/sessions/` | Agent/CLI session persistence checked into this clone (normally machine-local). |
| `.clawd-todos.json` | Todo state artifact used by the agent/CLI surfaces. |
| `.omc/plans/` | Local planning markdown. |
| `.sandbox-home/` | Sandboxed home settings used in dev/test (e.g. rustup settings). |

### Rust crates (`rust/crates/*`)

| Crate | Purpose |
|-------|---------|
| **`rusty-claude-cli`** | CLI entrypoint; binary **`claw`**. Argument parsing, REPL, rendering, subcommands. |
| **`runtime`** | Core agent runtime: session, conversation, tools orchestration, MCP, permissions, sandbox, config, git context, hooks integration, etc. |
| **`api`** | HTTP/SSE clients and provider glue (Anthropic, OpenAI-compatible/OpenRouter-style paths), types, errors, prompt cache. |
| **`tools`** | Tool implementations and helpers wired into the runtime (e.g. lane completion, PDF extract). |
| **`commands`** | Shared command definitions / helpers consumed by the CLI. |
| **`plugins`** | Plugin model, bundled sample plugins, hook wiring, test isolation. |
| **`telemetry`** | Telemetry hooks/types used by the product surface. |
| **`compat-harness`** | Compatibility / contract testing harness shared with CLI tests. |
| **`mock-anthropic-service`** | Deterministic mock Anthropic-compatible HTTP service for tests and parity runs. |

Tests and benches live beside crates (`tests/`, `benches/` under `api`, integration tests under `runtime`, CLI tests under `rusty-claude-cli/tests`).

---

## `src/` - Python companion

Per [`README.md`](README.md), this tree is a **companion / reference / audit** workspace, **not** the primary `claw` runtime.

| Area | Role |
|------|------|
| `main.py`, `runtime.py`, `replLauncher.py`, `commands.py`, `tools.py`, ... | Historical or parallel Python implementation and helpers for porting and behavior comparison. |
| `parity_audit.py`, `port_manifest.py` | Auditing and manifest machinery for parity with the Rust port. |
| `reference_data/` | JSON snapshots of commands, tools, subsystems, and archive surfaces used by audits and tests. |
| Package subdirs (`assistant/`, `bootstrap/`, `bridge/`, ...) | Subsystem-oriented modules; many are package markers plus focused logic. |
| `setup.py` | Legacy packaging entry for the Python tree where still applicable. |

Treat this as **supporting material** unless you are explicitly working on Python-side audits or migration tooling.

---

## `tests/`

| Path | Role |
|------|------|
| `test_porting_workspace.py` | Tests for the porting / workspace invariants on the Python side. |

---

## `.claude/` (repo root)

Tracked session JSON files under `.claude/sessions/` in this clone. These are **IDE/agent session exports or state**; they are not application source. Prefer not to hand-edit; safe to ignore for product behavior.

---

## Appendix A: all git-tracked paths (sorted)

The list below is the complete output of `git ls-files` sorted lexicographically (280 paths). Regenerate locally with:

`git ls-files | Sort-Object`

```text
ï»¿.claude.json
.claude/sessions/session-1774998936453.json
.claude/sessions/session-1774998994373.json
.claude/sessions/session-1775007533836.json
.claude/sessions/session-1775007622154.json
.claude/sessions/session-1775007632904.json
.claude/sessions/session-1775007846522.json
.claude/sessions/session-1775009126105.json
.claude/sessions/session-1775009583240.json
.claude/sessions/session-1775009651284.json
.claude/sessions/session-1775010002596.json
.claude/sessions/session-1775010229294.json
.claude/sessions/session-1775010237519.json
.github/FUNDING.yml
.github/scripts/check_doc_source_of_truth.py
.github/workflows/release.yml
.github/workflows/rust-ci.yml
.gitignore
assets/claw-hero.jpeg
assets/omx/omx-readme-review-1.png
assets/omx/omx-readme-review-2.png
assets/sigrid-photo.png
assets/star-history.png
assets/tweet-screenshot.png
assets/wsj-feature.png
CLAUDE.md
Containerfile
docs/container.md
docs/MODEL_COMPATIBILITY.md
install.sh
PARITY.md
PHILOSOPHY.md
prd.json
progress.txt
README.md
ROADMAP.md
rust/.claude/sessions/session-1775007453382.json
rust/.claude/sessions/session-1775007484031.json
rust/.claude/sessions/session-1775007490104.json
rust/.claude/sessions/session-1775007981374.json
rust/.claude/sessions/session-1775008007069.json
rust/.claude/sessions/session-1775008071886.json
rust/.claude/sessions/session-1775008137143.json
rust/.claude/sessions/session-1775008161929.json
rust/.claude/sessions/session-1775008308936.json
rust/.claude/sessions/session-1775008427969.json
rust/.claude/sessions/session-1775008464519.json
rust/.claude/sessions/session-1775008997307.json
rust/.claude/sessions/session-1775009119214.json
rust/.claude/sessions/session-1775009126336.json
rust/.claude/sessions/session-1775009145469.json
rust/.claude/sessions/session-1775009431231.json
rust/.claude/sessions/session-1775009769569.json
rust/.claude/sessions/session-1775009841982.json
rust/.claude/sessions/session-1775009869734.json
rust/.claude/sessions/session-1775010047738.json
rust/.claude/sessions/session-1775010333630.json
rust/.claude/sessions/session-1775010384918.json
rust/.claude/sessions/session-1775010909274.json
rust/.claude/sessions/session-1775011146355.json
rust/.claude/sessions/session-1775011562247.json
rust/.claude/sessions/session-1775012674485.json
rust/.claude/sessions/session-1775012687059.json
rust/.claude/sessions/session-1775013221875.json
rust/.claw/sessions/session-1775386832313-0.jsonl
rust/.claw/sessions/session-1775386842352-0.jsonl
rust/.claw/sessions/session-1775386852257-0.jsonl
rust/.claw/sessions/session-1775386853666-0.jsonl
rust/.clawd-todos.json
rust/.gitignore
rust/.omc/plans/tui-enhancement-plan.md
rust/.sandbox-home/.rustup/settings.toml
rust/Cargo.lock
rust/Cargo.toml
rust/crates/api/benches/request_building.rs
rust/crates/api/Cargo.toml
rust/crates/api/src/client.rs
rust/crates/api/src/error.rs
rust/crates/api/src/http_client.rs
rust/crates/api/src/lib.rs
rust/crates/api/src/prompt_cache.rs
rust/crates/api/src/providers/anthropic.rs
rust/crates/api/src/providers/mod.rs
rust/crates/api/src/providers/openai_compat.rs
rust/crates/api/src/sse.rs
rust/crates/api/src/types.rs
rust/crates/api/tests/client_integration.rs
rust/crates/api/tests/openai_compat_integration.rs
rust/crates/api/tests/provider_client_integration.rs
rust/crates/api/tests/proxy_integration.rs
rust/crates/commands/Cargo.toml
rust/crates/commands/src/lib.rs
rust/crates/compat-harness/Cargo.toml
rust/crates/compat-harness/src/lib.rs
rust/crates/mock-anthropic-service/Cargo.toml
rust/crates/mock-anthropic-service/src/lib.rs
rust/crates/mock-anthropic-service/src/main.rs
rust/crates/plugins/bundled/example-bundled/.claude-plugin/plugin.json
rust/crates/plugins/bundled/example-bundled/hooks/post.sh
rust/crates/plugins/bundled/example-bundled/hooks/pre.sh
rust/crates/plugins/bundled/sample-hooks/.claude-plugin/plugin.json
rust/crates/plugins/bundled/sample-hooks/hooks/post.sh
rust/crates/plugins/bundled/sample-hooks/hooks/pre.sh
rust/crates/plugins/Cargo.toml
rust/crates/plugins/src/hooks.rs
rust/crates/plugins/src/lib.rs
rust/crates/plugins/src/test_isolation.rs
rust/crates/runtime/Cargo.toml
rust/crates/runtime/src/bash.rs
rust/crates/runtime/src/bash_validation.rs
rust/crates/runtime/src/bootstrap.rs
rust/crates/runtime/src/branch_lock.rs
rust/crates/runtime/src/compact.rs
rust/crates/runtime/src/config.rs
rust/crates/runtime/src/config_validate.rs
rust/crates/runtime/src/conversation.rs
rust/crates/runtime/src/file_ops.rs
rust/crates/runtime/src/git_context.rs
rust/crates/runtime/src/green_contract.rs
rust/crates/runtime/src/hooks.rs
rust/crates/runtime/src/json.rs
rust/crates/runtime/src/lane_events.rs
rust/crates/runtime/src/lib.rs
rust/crates/runtime/src/lsp_client.rs
rust/crates/runtime/src/mcp.rs
rust/crates/runtime/src/mcp_client.rs
rust/crates/runtime/src/mcp_lifecycle_hardened.rs
rust/crates/runtime/src/mcp_server.rs
rust/crates/runtime/src/mcp_stdio.rs
rust/crates/runtime/src/mcp_tool_bridge.rs
rust/crates/runtime/src/oauth.rs
rust/crates/runtime/src/permission_enforcer.rs
rust/crates/runtime/src/permissions.rs
rust/crates/runtime/src/plugin_lifecycle.rs
rust/crates/runtime/src/policy_engine.rs
rust/crates/runtime/src/prompt.rs
rust/crates/runtime/src/recovery_recipes.rs
rust/crates/runtime/src/remote.rs
rust/crates/runtime/src/sandbox.rs
rust/crates/runtime/src/session.rs
rust/crates/runtime/src/session_control.rs
rust/crates/runtime/src/sse.rs
rust/crates/runtime/src/stale_base.rs
rust/crates/runtime/src/stale_branch.rs
rust/crates/runtime/src/summary_compression.rs
rust/crates/runtime/src/task_packet.rs
rust/crates/runtime/src/task_registry.rs
rust/crates/runtime/src/team_cron_registry.rs
rust/crates/runtime/src/trust_resolver.rs
rust/crates/runtime/src/usage.rs
rust/crates/runtime/src/worker_boot.rs
rust/crates/runtime/tests/integration_tests.rs
rust/crates/rusty-claude-cli/.claw/sessions/session-newer.jsonl
rust/crates/rusty-claude-cli/build.rs
rust/crates/rusty-claude-cli/Cargo.toml
rust/crates/rusty-claude-cli/src/init.rs
rust/crates/rusty-claude-cli/src/input.rs
rust/crates/rusty-claude-cli/src/main.rs
rust/crates/rusty-claude-cli/src/render.rs
rust/crates/rusty-claude-cli/tests/cli_flags_and_config_defaults.rs
rust/crates/rusty-claude-cli/tests/compact_output.rs
rust/crates/rusty-claude-cli/tests/mock_parity_harness.rs
rust/crates/rusty-claude-cli/tests/output_format_contract.rs
rust/crates/rusty-claude-cli/tests/resume_slash_commands.rs
rust/crates/telemetry/Cargo.toml
rust/crates/telemetry/src/lib.rs
rust/crates/tools/.gitignore
rust/crates/tools/Cargo.toml
rust/crates/tools/src/lane_completion.rs
rust/crates/tools/src/lib.rs
rust/crates/tools/src/pdf_extract.rs
rust/MOCK_PARITY_HARNESS.md
rust/mock_parity_scenarios.json
rust/PARITY.md
rust/README.md
rust/scripts/run_mock_parity_diff.py
rust/scripts/run_mock_parity_harness.sh
rust/TUI-ENHANCEMENT-PLAN.md
rust/USAGE.md
src/__init__.py
src/_archive_helper.py
src/assistant/__init__.py
src/bootstrap/__init__.py
src/bootstrap_graph.py
src/bridge/__init__.py
src/buddy/__init__.py
src/cli/__init__.py
src/command_graph.py
src/commands.py
src/components/__init__.py
src/constants/__init__.py
src/context.py
src/coordinator/__init__.py
src/cost_tracker.py
src/costHook.py
src/deferred_init.py
src/dialogLaunchers.py
src/direct_modes.py
src/entrypoints/__init__.py
src/execution_registry.py
src/history.py
src/hooks/__init__.py
src/ink.py
src/interactiveHelpers.py
src/keybindings/__init__.py
src/main.py
src/memdir/__init__.py
src/migrations/__init__.py
src/models.py
src/moreright/__init__.py
src/native_ts/__init__.py
src/outputStyles/__init__.py
src/parity_audit.py
src/permissions.py
src/plugins/__init__.py
src/port_manifest.py
src/prefetch.py
src/projectOnboardingState.py
src/query.py
src/query_engine.py
src/QueryEngine.py
src/reference_data/__init__.py
src/reference_data/archive_surface_snapshot.json
src/reference_data/commands_snapshot.json
src/reference_data/subsystems/assistant.json
src/reference_data/subsystems/bootstrap.json
src/reference_data/subsystems/bridge.json
src/reference_data/subsystems/buddy.json
src/reference_data/subsystems/cli.json
src/reference_data/subsystems/components.json
src/reference_data/subsystems/constants.json
src/reference_data/subsystems/coordinator.json
src/reference_data/subsystems/entrypoints.json
src/reference_data/subsystems/hooks.json
src/reference_data/subsystems/keybindings.json
src/reference_data/subsystems/memdir.json
src/reference_data/subsystems/migrations.json
src/reference_data/subsystems/moreright.json
src/reference_data/subsystems/native_ts.json
src/reference_data/subsystems/outputStyles.json
src/reference_data/subsystems/plugins.json
src/reference_data/subsystems/remote.json
src/reference_data/subsystems/schemas.json
src/reference_data/subsystems/screens.json
src/reference_data/subsystems/server.json
src/reference_data/subsystems/services.json
src/reference_data/subsystems/skills.json
src/reference_data/subsystems/state.json
src/reference_data/subsystems/types.json
src/reference_data/subsystems/upstreamproxy.json
src/reference_data/subsystems/utils.json
src/reference_data/subsystems/vim.json
src/reference_data/subsystems/voice.json
src/reference_data/tools_snapshot.json
src/remote/__init__.py
src/remote_runtime.py
src/replLauncher.py
src/runtime.py
src/schemas/__init__.py
src/screens/__init__.py
src/server/__init__.py
src/services/__init__.py
src/session_store.py
src/setup.py
src/skills/__init__.py
src/state/__init__.py
src/system_init.py
src/task.py
src/tasks.py
src/Tool.py
src/tool_pool.py
src/tools.py
src/transcript.py
src/types/__init__.py
src/upstreamproxy/__init__.py
src/utils/__init__.py
src/vim/__init__.py
src/voice/__init__.py
tests/test_porting_workspace.py
USAGE.md
```

---

## Appendix B: notable paths on disk but not in git

These appeared under `D:\ClawCodex\ClawCodex` alongside the clone but are **not** in `git ls-files`. They may be personal, Windows-specific, or generated.

| Path | Typical role |
|------|----------------|
| `launch.bat`, `launch.ps1` | Local one-click build/run wrappers for Windows. |
| `run-vault.bat`, `run-vault.ps1` | Local vault-related helpers (not part of upstream repo). |
| `SPEC.md` | Local specification / notes file. |
| `Demos/` | Demo projects or sandboxes. |
| `tool_audit/` | Local audit output or scripts. |
| `.git/` | Git object database (never committed). |
| `.claw/`, `.clawd-agents/`, `.clawd-todos1.json` | Additional local agent/todo state outside tracked paths. |
| `.sandbox-home/`, `.sandbox-tmp/` (repo root) | Local sandbox dirs for experiments. |

If you add new first-party documentation that overlaps this file (for example a dedicated `FILE_MAP.md`), consider trimming Appendix A from here and linking to the single source of truth instead.
