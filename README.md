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
3. If prompted, paste a valid OpenRouter API key in the same Command Prompt window. Input is hidden.
4. The launcher saves credentials to repo-root `.env`, validates the key with OpenRouter, runs `claw doctor`, then starts Claw.

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

Use [`CHECK-KEY.bat`](./CHECK-KEY.bat) to verify the saved OpenRouter key without launching Claw. Use [`UPDATE-KEY.bat`](./UPDATE-KEY.bat) to replace the key from the terminal without opening an editor.

## Current Authentication Path

ClawCodex currently documents OpenRouter as the practical first-run provider path. Credentials live in one place: a repo-root `.env` file next to `README.md`.

Copy [`.env.example`](./.env.example) to `.env` for manual setup:

```dotenv
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=YOUR_OPENROUTER_KEY_HERE
```

The Windows helpers validate the key with OpenRouter's model-agnostic `GET /v1/auth/key` endpoint before launching. This does not spend tokens and does not depend on a specific model.

Important details:

- `claw doctor` is mostly a local health report. The Windows launcher runs the live OpenRouter key check before `doctor`.
- `CLAW_NO_CREDENTIAL_PROMPT=1` disables the interactive key prompt and is intended for CI or scripted runs.
- `START-CLAW.bat` clears inherited `OPENAI_API_KEY` and `OPENAI_BASE_URL` for its interactive path so stale shell variables do not shadow `.env`.
- If the model picker appears, it filters toward Claw-compatible OpenRouter models: text output, tool-calling support, and useful context windows.

More setup detail is in [`USAGE.md`](./USAGE.md).

## What Is In This Repo

- [`rust/`](./rust) - canonical Rust workspace and CLI/runtime implementation.
- [`bin/windows/claw.exe`](./bin/windows/claw.exe) - optional packaged Windows binary for quick startup.
- [`START-CLAW.bat`](./START-CLAW.bat) - one-click Windows setup, key validation, `doctor`, and launch.
- [`run-claw.bat`](./run-claw.bat) / [`run-claw.ps1`](./run-claw.ps1) - run the packaged CLI from the repo root.
- [`build-claw.ps1`](./build-claw.ps1) - rebuilds `bin/windows/claw.exe` from source.
- [`.env.example`](./.env.example) - template for the local OpenRouter `.env` file.
- [`USAGE.md`](./USAGE.md) - onboarding, auth, common commands, and troubleshooting.
- [`PARITY.md`](./PARITY.md), [`ROADMAP.md`](./ROADMAP.md), [`PHILOSOPHY.md`](./PHILOSOPHY.md) - project context and direction.

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
/export
```

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

That runs a release build for `rusty-claude-cli` and refreshes:

```text
bin\windows\claw.exe
```

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
cargo clippy --workspace
cargo test --workspace
```

Local Windows development can still expose platform-specific test differences, especially tests that depend on Unix-only permissions, path rendering, or shell stubs. When a Windows-only local failure appears, compare it with the CI target before treating it as a Linux CI regression.

For stricter local cleanup, you can also run:

```bash
cargo clippy --workspace --all-targets -- -D warnings
```

That is useful, but it is stricter than the current GitHub CI clippy job.

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
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-v1-...
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

These are the baseline tools most people expect from a coding agent:

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
