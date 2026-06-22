# ClawCodex

<p align="center">
  <a href="./USAGE.md">Usage</a>
  ·
  <a href="./rust/README.md">Rust workspace</a>
  ·
  <a href="./PARITY.md">Parity</a>
  ·
  <a href="./ROADMAP.md">Roadmap</a>
  ·
  <a href="./PHILOSOPHY.md">Philosophy</a>
</p>

<p align="center">
  <img src="clawcodex.png" alt="ClawCodex hero image" width="300" />
</p>

ClawCodex is a packaged distribution of the `claw` CLI agent harness. The active implementation lives in the Rust workspace under [`rust/`](./rust), with a Windows launcher and optional bundled binary under [`bin/windows/claw.exe`](./bin/windows/claw.exe).

This repository is for research and experimentation. It is not an official release channel, not a supported production product, and not affiliated with Anthropic.

## Quick Start On Windows

The current recommended path is:

1. Clone or open this repository, commonly at `C:\clawcodex`.
2. Double-click [`START-CLAW.bat`](./START-CLAW.bat).
3. Choose **OpenRouter**, **Cerebras**, **Z.ai**, **DeepSeek**, or **Kimi** when prompted.
4. If your key is missing or invalid, paste it in the same Command Prompt window (input is hidden). The launcher saves credentials to repo-root `.env` and validates them live.
5. The launcher runs `claw doctor`, then starts Claw:
   - **OpenRouter:** validates the key, shows a model picker filtered to tool-capable models, then opens the REPL.
   - **Cerebras:** live key validation, then a model picker from `GET /v1/models`, then the REPL with your chosen model (saved as `CLAW_CEREBRAS_MODEL` in `.env`).
   - **Z.ai:** live key validation, then a GLM model picker from `GET /models` filtered to `glm-4*` / `glm-5*`, defaulting to `glm-5.2`, then the REPL with your chosen model (saved as `CLAW_ZAI_MODEL` in `.env`).
   - **DeepSeek:** live key validation, then a model picker from `GET /models` with `deepseek-v4-flash` default preference (and `deepseek-v4-pro` fallback), then the REPL with your chosen model (saved as `CLAW_DEEPSEEK_MODEL` in `.env`).
   - **Kimi:** live key validation, then a model picker from `GET /v1/models` defaulting to `kimi-k2.7-code`, then the REPL with your chosen model (saved as `CLAW_KIMI_MODEL` in `.env`).

If you do not have the repo yet:

```powershell
git clone https://github.com/Skynet-Pro-Plus/ClawCodex C:\clawcodex
cd C:\clawcodex
```

Useful commands from the repo root:

```bat
START-CLAW.bat
run-claw.bat
run-claw.bat doctor
run-claw.bat status
run-claw.bat prompt "say hello"
CHECK-KEY.bat
UPDATE-KEY.bat
```

Use [`CHECK-KEY.bat`](./CHECK-KEY.bat) to verify the saved OpenRouter key without launching Claw. Use [`UPDATE-KEY.bat`](./UPDATE-KEY.bat) to replace the OpenRouter key from the terminal without opening an editor.

To verify or update a Cerebras key from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-cerebras.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-cerebras-key.ps1
```

## Choose OpenRouter, Cerebras, Z.ai, DeepSeek, Or Kimi At Launch

[`START-CLAW.bat`](./START-CLAW.bat) runs [`launch-claw.ps1`](./launch-claw.ps1), which handles first-run setup before the `claw` REPL starts:

1. **Provider menu** — pick OpenRouter, Cerebras, Z.ai, DeepSeek, or Kimi (defaults to your last choice from `.env`).
2. **Key check** — reads the matching key from repo-root `.env`; prompts with hidden input if missing or rejected (up to 3 attempts).
3. **Launch**
   - **OpenRouter:** live key validation, then `claw doctor`, then the built-in tool-capable model picker, then the REPL.
   - **Cerebras:** live key validation (`GET /v1/models`), then an interactive model picker (same API list), then the REPL with `--model <your choice>`.
   - **Z.ai:** live key validation (`GET /models`), then an interactive GLM picker filtered to `glm-4*` / `glm-5*`, then the REPL with `--model <your choice>` (default `glm-5.2`).
   - **DeepSeek:** live key validation (`GET /models`), then an interactive model picker preferring non-deprecated `deepseek-*` models, then the REPL with `--model <your choice>` (default `deepseek-v4-flash`).
   - **Kimi:** live key validation (`GET /v1/models`), then an interactive picker preferring current `kimi-*` models, then the REPL with `--model <your choice>` (default `kimi-k2.7-code`).

Later runs in the same shell can skip the menu and use the saved provider:

```bat
run-claw.bat
```

Or run the launcher directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch-claw.ps1
```

## Current Authentication Path

Credentials live in one place: a repo-root `.env` file next to `README.md`. Copy [`.env.example`](./.env.example) for manual setup:

```dotenv
CLAW_PROVIDER=openrouter
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=YOUR_OPENROUTER_KEY_HERE
CEREBRAS_API_KEY=YOUR_CEREBRAS_KEY_HERE
CLAW_CEREBRAS_MODEL=gpt-oss-120b
ZAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZAI_API_KEY=YOUR_ZAI_KEY_HERE
CLAW_ZAI_MODEL=glm-5.2
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY_HERE
CLAW_DEEPSEEK_MODEL=deepseek-v4-flash
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_API_KEY=YOUR_KIMI_KEY_HERE
MOONSHOT_API_KEY=YOUR_MOONSHOT_KEY_HERE
CLAW_KIMI_MODEL=kimi-k2.7-code
```

**OpenRouter** uses `OPENAI_BASE_URL=https://openrouter.ai/api/v1` and `OPENAI_API_KEY`. The Windows helpers validate the key with OpenRouter's model-agnostic `GET /v1/auth/key` endpoint before launching. This does not spend tokens and does not depend on a specific model.

**Cerebras** uses `CEREBRAS_API_KEY` and the Cerebras OpenAI-compatible base URL (`https://api.cerebras.ai/v1`). When Cerebras is selected, the launcher also mirrors the key into `OPENAI_*` so the packaged `claw` CLI can connect. Validation uses `GET /v1/models`.

**Z.ai** uses `ZAI_API_KEY` and `ZAI_BASE_URL` (default `https://open.bigmodel.cn/api/paas/v4`). When Z.ai is selected, the launcher mirrors Z.ai auth into `OPENAI_*` for the existing OpenAI-compatible runtime path. Validation uses `GET /models`.

**DeepSeek** uses `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL` (default `https://api.deepseek.com`). When DeepSeek is selected, the launcher mirrors DeepSeek auth into `OPENAI_*` for the existing OpenAI-compatible runtime path. Validation uses `GET /models`.
The picker prefers current `deepseek-v4-*` models and treats `deepseek-chat` / `deepseek-reasoner` as deprecated compatibility options.

**Kimi** uses `KIMI_API_KEY` (or `MOONSHOT_API_KEY`) and `KIMI_BASE_URL` (default `https://api.moonshot.ai/v1`). When Kimi is selected, the launcher mirrors Kimi auth into `OPENAI_*` for the existing OpenAI-compatible runtime path. Validation uses `GET /v1/models`.

Important details:

- `claw doctor` is mostly a local health report. The Windows launcher runs the live provider key check before `doctor`.
- `CLAW_PROVIDER` in `.env` records your last choice (`openrouter`, `cerebras`, `zai`, `deepseek`, or `kimi`). `run-claw.bat` / `run-claw.ps1` apply it on later runs without re-prompting.
- `CLAW_NO_CREDENTIAL_PROMPT=1` disables the interactive key prompt and is intended for CI or scripted runs.
- Repo-root `.env` is the authoritative local credential source. When both `.env` and process `OPENAI_API_KEY` / `OPENAI_BASE_URL` are set, Claw and the key checker prefer the repo `.env`.
- `START-CLAW.bat` clears inherited `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CEREBRAS_API_KEY`, `ZAI_API_KEY`, `DEEPSEEK_API_KEY`, `KIMI_API_KEY`, and `MOONSHOT_API_KEY` for its interactive path; direct `run-claw.*` entry points still prefer `.env` through the runtime resolver.
- `UPDATE-KEY.bat`, `set-cerebras-key.ps1`, and the Rust first-run prompt hide pasted key input when the terminal supports masked entry.
- All provider flows support model picking. OpenRouter filters toward Claw-compatible models: text output, tool-calling support, and useful context windows. Cerebras lists models returned by the live Cerebras `GET /v1/models` endpoint. Z.ai lists models from `GET /models`, then filters to `glm-4*` / `glm-5*` because the endpoint does not expose a tool-capability boolean. DeepSeek lists live models from `GET /models`, prefers non-deprecated `deepseek-*` models, and defaults to `deepseek-v4-flash` when available. Kimi lists live models from `GET /v1/models`, prefers current `kimi-*` entries, and defaults to `kimi-k2.7-code`.
- If a release binary exists at `%LOCALAPPDATA%\ClawCodex\cargo-target\release\claw.exe`, the launch scripts prefer it over `bin\windows\claw.exe`; this helps local repairs take effect even when the packaged binary is locked by a running session.

More setup detail is in [`USAGE.md`](./USAGE.md).

## What Is In This Repo

- [`rust/`](./rust) - canonical Rust workspace and CLI/runtime implementation.
- [`bin/windows/claw.exe`](./bin/windows/claw.exe) - optional packaged Windows binary for quick startup.
- [`START-CLAW.bat`](./START-CLAW.bat) - one-click Windows launcher: choose OpenRouter, Cerebras, Z.ai, DeepSeek, or Kimi, validate key, run `doctor` (OpenRouter only), start Claw.
- [`launch-claw.ps1`](./launch-claw.ps1) - interactive provider menu, key prompts, and REPL launch logic used by `START-CLAW.bat`.
- [`validate-openrouter.ps1`](./validate-openrouter.ps1) / [`validate-cerebras.ps1`](./validate-cerebras.ps1) / [`validate-zai.ps1`](./validate-zai.ps1) / [`validate-deepseek.ps1`](./validate-deepseek.ps1) / [`validate-kimi.ps1`](./validate-kimi.ps1) - live API key checks from the terminal.
- [`pick-cerebras-model.ps1`](./pick-cerebras-model.ps1) / [`pick-zai-model.ps1`](./pick-zai-model.ps1) / [`pick-deepseek-model.ps1`](./pick-deepseek-model.ps1) / [`pick-kimi-model.ps1`](./pick-kimi-model.ps1) - interactive provider model list before launch.
- [`set-openrouter-key.ps1`](./set-openrouter-key.ps1) / [`set-cerebras-key.ps1`](./set-cerebras-key.ps1) / [`set-zai-key.ps1`](./set-zai-key.ps1) / [`set-deepseek-key.ps1`](./set-deepseek-key.ps1) / [`set-kimi-key.ps1`](./set-kimi-key.ps1) - save provider keys to `.env` with hidden input.
- [`run-claw.bat`](./run-claw.bat) / [`run-claw.ps1`](./run-claw.ps1) - run the packaged CLI from the repo root (uses `CLAW_PROVIDER` from `.env`).
- [`build-claw.ps1`](./build-claw.ps1) - rebuilds `bin/windows/claw.exe` from source when the packaged binary is not locked; local release builds under `%LOCALAPPDATA%\ClawCodex\cargo-target` are also picked up by the launch scripts.
- [`src/server/`](./src/server) - FastAPI control plane for the local dashboard and task lifecycle APIs.
- [`frontend/`](./frontend) - React dashboard for mission control, plan review, diffs, rules, and repository history.
- [`src/engine/orchestrator/`](./src/engine/orchestrator) - task runner, SQLite store, and staged mission workflow.
- [`src/engine/coding/`](./src/engine/coding) - code generation, local templates, and proposal validation.
- [`.env.example`](./.env.example) - template for OpenRouter, Cerebras, Z.ai, DeepSeek, and Kimi credentials in `.env`.
- [`USAGE.md`](./USAGE.md) - onboarding, auth, common commands, and troubleshooting.
- [`PARITY.md`](./PARITY.md), [`ROADMAP.md`](./ROADMAP.md), [`PHILOSOPHY.md`](./PHILOSOPHY.md) - project context and direction.

## Local Dashboard And Orchestrator

The Python/FastAPI control plane and React dashboard provide a local mission workflow on top of the engine. A mission moves through `PLAN`, `CODE`, `TEST`, `DEBUG`, `REVIEW`, and `COMPLETE` stages, with explicit approval gates before code is generated or written.

Run the dashboard-backed API from the repo root:

```powershell
$env:PYTHONPATH = "$PWD"
python -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000
```

Build the dashboard assets served by the API:

```powershell
cd frontend
npm install
npm run build
```

Then open `http://127.0.0.1:8000`. During development you can also run `npm run dev` in `frontend/`.

Dashboard workflow highlights:

- Mission Control creates tasks, shows live stage progress, and displays pending diff approvals.
- New missions pause after `PLAN`; the banner shows the actual plan summary/items and requires **Approve Plan and Code** before `CODE` runs.
- The Missions page lists recent tasks and supports open, stop, and delete actions.
- The Repositories page lists recently used repo paths from mission history.
- Templates lists rule packs under `clawcodex-packs/`.
- Integrations shows OpenRouter key status and links to model settings.
- The Rules panel shows active rule summaries and lets you enable/disable packs for the next mission. Built-in system safety rules always apply.
- High-confidence extension typos in prompts, such as `xlxs` to `xlsx`, are corrected before mission creation with a visible note; uncertain corrections prompt first.
- HTML-only or other repos without an automated test harness report tests as skipped instead of blocked, with static HTML verification when applicable.

Useful local APIs include:

- `GET /health`
- `GET /api/tasks`
- `POST /api/tasks`
- `POST /api/tasks/{task_id}/start`
- `POST /api/tasks/{task_id}/approve-plan`
- `DELETE /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/timeline`
- `POST /api/tasks/{task_id}/diffs/approve-all`
- `POST /api/tasks/{task_id}/diffs/reject-all`
- `GET /api/repos/recent`

## Common Commands

Use `run-claw.bat` from Command Prompt or `.\run-claw.ps1` from PowerShell when running the packaged binary.

```bat
run-claw.bat
run-claw.bat prompt "explain this repository"
run-claw.bat doctor
run-claw.bat status
run-claw.bat --resume latest
```

Useful slash commands inside an interactive session:

```text
/help
/status
/doctor
/skills
/agents
/mcp
/order
/export
```

Use `/order`, then finish with a line containing only `/end`, for dependable multiline prompts on Windows terminals where pasted multiline input may otherwise submit early.

Common flags:

```bat
run-claw.bat --model minimax/minimax-m2.7
run-claw.bat --permission-mode read-only prompt "summarize this repo"
run-claw.bat --permission-mode workspace-write prompt "update docs"
run-claw.bat --permission-mode danger-full-access prompt "run the requested workflow"
```

## Build From Source

Install Rust from [rustup.rs](https://rustup.rs/) if you want to build locally.

From the repo root on Windows:

```powershell
.\build-claw.ps1
```

That runs a release build for `rusty-claude-cli` and refreshes the packaged binary when it is not locked:

```text
bin\windows\claw.exe
```

For local repair builds that should stay outside the repository, use:

```powershell
cd .\rust
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\ClawCodex\cargo-target"
cargo build -p rusty-claude-cli --release
```

`START-CLAW.bat`, `launch-claw.ps1`, and `run-claw.ps1` prefer `%LOCALAPPDATA%\ClawCodex\cargo-target\release\claw.exe` when present.

To build directly from the Rust workspace:

```powershell
cd .\rust
cargo build --workspace
.\target\debug\claw.exe doctor
.\target\debug\claw.exe prompt "say hello"
```

On Unix-like shells:

```bash
cd rust
cargo build --workspace
./target/debug/claw doctor
./target/debug/claw prompt "say hello"
```

## Verification

GitHub Actions runs these checks on Ubuntu:

```bash
cd rust
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Local Windows development can still expose platform-specific test differences, especially tests that depend on Unix-only permissions, path rendering, or shell stubs. When a Windows-only local failure appears, compare it with the CI target before treating it as a Linux CI regression.

The CI clippy job intentionally matches the stricter local command so warnings and test-target lints are caught before merge.

## Troubleshooting

If the packaged binary is missing or stale:

```powershell
.\build-claw.ps1
```

If the script writes `claw.exe.new`, close any running `claw.exe` process and run the build again, or replace `bin\windows\claw.exe` with the generated `claw.exe.new`.

If OpenRouter auth fails:

```bat
CHECK-KEY.bat
UPDATE-KEY.bat
```

Confirm `.env` contains:

```dotenv
CLAW_PROVIDER=openrouter
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-v1-...
```

If Cerebras auth fails:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-cerebras.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-cerebras-key.ps1
```

Confirm `.env` contains:

```dotenv
CLAW_PROVIDER=cerebras
CEREBRAS_API_KEY=your-cerebras-key
CLAW_CEREBRAS_MODEL=gpt-oss-120b
```

If Z.ai auth fails:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-zai.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-zai-key.ps1
```

Confirm `.env` contains:

```dotenv
CLAW_PROVIDER=zai
ZAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZAI_API_KEY=your-zai-key
CLAW_ZAI_MODEL=glm-5.2
```

If DeepSeek auth fails:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-deepseek.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-deepseek-key.ps1
```

Confirm `.env` contains:

```dotenv
CLAW_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your-deepseek-key
CLAW_DEEPSEEK_MODEL=deepseek-v4-flash
```

If Kimi auth fails:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-kimi.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-kimi-key.ps1
```

Confirm `.env` contains:

```dotenv
CLAW_PROVIDER=kimi
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_API_KEY=your-kimi-key
MOONSHOT_API_KEY=your-kimi-key
CLAW_KIMI_MODEL=kimi-k2.7-code
```

If `doctor` says the key prompt was skipped, unset `CLAW_NO_CREDENTIAL_PROMPT` or use `START-CLAW.bat` for the interactive setup flow.

If PowerShell blocks scripts, use the `.bat` launchers or update your user execution policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Tool Surface

ClawCodex is more than a shell/file-editing wrapper. The upgraded engine exposes the original workspace tools plus a broader tool-call surface for planning, research, notebook editing, structured output, agent orchestration, workers, teams, cron jobs, and MCP integrations.

The source of truth is [`rust/crates/tools/src/lib.rs`](./rust/crates/tools/src/lib.rs), with runtime and audit coverage in [`rust/crates/tools/src/bin/tool_audit.rs`](./rust/crates/tools/src/bin/tool_audit.rs).

### Original workspace tools

These are the baseline tools most people expect from a coding agent and are kept immediately available:

- `bash` - run shell commands in the workspace.
- `read_file` - read file contents.
- `write_file` - write file contents.
- `edit_file` - replace text inside files.
- `glob_search` - find files by glob pattern.
- `grep_search` - search file contents by pattern.

### Added shell and editing tools

- `PowerShell` - run Windows-native PowerShell commands.
- `REPL` - execute code in a supported language runtime.
- `NotebookEdit` - modify Jupyter notebook cell contents.

### Added research and discovery tools

- `WebFetch` - fetch a URL and answer a prompt about it.
- `WebSearch` - search the web for current information.
- `ToolSearch` - search the available tool registry.

Large or specialized tool schemas may be deferred behind `ToolSearch` so the initial model request stays small. If the model needs a specialized tool such as repository impact analysis, test selection, worktree helpers, or task-ledger tools, it should discover the exact tool name with `ToolSearch`.

### Added planning and workflow tools

- `TodoWrite` - maintain a structured todo/task list.
- `Skill` - invoke installed skills.
- `Config` - inspect config state.
- `Sleep` - pause briefly during workflows.
- `SendUserMessage` - send an explicit user-facing progress/update message.
- `StructuredOutput` - emit structured or machine-readable output.
- `EnterPlanMode` - switch into plan mode.
- `ExitPlanMode` - leave plan mode.
- `AskUserQuestion` - ask a structured question through the runtime.

### Added task and agent orchestration tools

- `Agent` - create or invoke an agent workflow.
- `TaskCreate` - create a tracked task.
- `RunTaskPacket` - create a task from a structured task packet.
- `TaskGet` - inspect one task.
- `TaskList` - list tracked tasks.
- `TaskStop` - stop a task.
- `TaskUpdate` - update task status or metadata.
- `TaskOutput` - retrieve task output.

### Added worker lifecycle tools

- `WorkerCreate` - create a worker/session process.
- `WorkerGet` - inspect worker state.
- `WorkerObserve` - attach observation data to worker state.
- `WorkerResolveTrust` - resolve workspace trust status for a worker.
- `WorkerAwaitReady` - wait for a worker to become ready.
- `WorkerSendPrompt` - send a prompt to a worker.
- `WorkerRestart` - restart a worker.
- `WorkerObserveCompletion` - record worker completion state.
- `WorkerTerminate` - terminate a worker.

### Added team and scheduling tools

- `TeamCreate` - create a team grouping for coordinated work.
- `TeamDelete` - remove a team grouping.
- `CronCreate` - create a cron/scheduled job.
- `CronList` - list scheduled jobs.
- `CronDelete` - delete a scheduled job.

### Added integration and protocol tools

- `LSP` - interact with language-server-backed features.
- `ListMcpResources` - list resources exposed by an MCP server.
- `ReadMcpResource` - read a specific MCP resource.
- `McpAuth` - inspect or handle MCP auth state.
- `MCP` - invoke MCP-exposed tools.
- `RemoteTrigger` - trigger a remote/integration action.
- `TestingPermission` - exercise/testing hook for permission flows.

Not every tool is available in every environment. Some depend on configured MCP servers, worker state, cron/team state, local runtimes, provider/network access, or permission mode. The main point is that the upgraded engine can handle more than direct file edits: it can plan, research, coordinate workers, manage tasks, inspect runtime state, and integrate with external tool protocols.

### Custom and future tools

ClawCodex can load custom tools through two supported extension surfaces:

- **Plugin tools** - plugin manifests can define a tool name, description, JSON input schema, command, arguments, and required permission. The runtime registers enabled plugin tools at startup.
- **MCP tools** - configured MCP servers can expose tools and resources, which ClawCodex discovers and routes through the runtime.

ClawCodex does not currently have a first-class in-chat `ToolCreate` command that permanently registers a brand-new tool during the same conversation. The supported path is to add a plugin tool or configure an MCP server, then let the runtime discover it.

## Security Boundaries

Hooks are an intentional local command execution surface. Treat hook configuration from a project or shared repository as trusted code: hooks run through the host shell, can see tool payloads, and may influence permission decisions.

Sandbox strength is platform-dependent. Full namespace/network isolation is Linux-specific when user namespaces are available; Windows and macOS runs should be treated as host-shell execution with weaker environment scoping rather than strong isolation.

## Documentation Map

- [`USAGE.md`](./USAGE.md) - setup, auth, launch commands, and common workflows.
- [`rust/README.md`](./rust/README.md) - workspace layout and crate responsibilities.
- [`PARITY.md`](./PARITY.md) - parity and migration status.
- [`rust/MOCK_PARITY_HARNESS.md`](./rust/MOCK_PARITY_HARNESS.md) - deterministic mock-service harness.
- [`ROADMAP.md`](./ROADMAP.md) - planned work and known gaps.
- [`PHILOSOPHY.md`](./PHILOSOPHY.md) - project intent, framing, and credits.

## Credits

**Johnny Export** - This repository explicitly credits Johnny Export for his work and philosophy: treating autonomous agent coordination, not only files on disk, as the product lesson, and centering the idea that humans set direction while claws perform the labor. See [`PHILOSOPHY.md`](./PHILOSOPHY.md) for the full framing and acknowledgment.

## Upstream Context

This distribution is based on the broader Claw Code ecosystem and may still reference upstream command/status text in a few places. When command help mentions `ultraworkers/claw-code`, treat that as upstream source-of-truth context, not as a different binary name.

## Disclaimer

- This repository is for research and experimentation only.
- This repository does not claim ownership of the original Claude Code source material.
- This repository is not affiliated with, endorsed by, or maintained by Anthropic.
