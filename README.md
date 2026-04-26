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

ClawCodex is a packaged distribution of the `claw` CLI agent harness with the Rust workspace in [`rust/`](./rust) and a bundled Windows binary in [`bin/windows/claw.exe`](./bin/windows/claw.exe).

This repository is published for research and experimentation only. It is not an official release channel, not a supported production product, and not affiliated with Anthropic.

This repo is set up so a new user can:

1. Run the packaged Windows binary immediately.
2. Rebuild the binary from source when needed.
3. Use `claw doctor` as the first health check before deeper troubleshooting.

## Recent updates

- **OpenRouter-first documentation and health checks** — Quick start and [`USAGE.md`](./USAGE.md) focus on OpenRouter (`OPENAI_BASE_URL` + `OPENAI_API_KEY`). `claw doctor` reports OpenRouter readiness using env vars or a repo-root `.env`. The API crate exposes `read_openai_base_url_explicit()` so diagnostics only treat an **explicit** `OPENAI_BASE_URL` as configured (see `rust/crates/api/src/providers/openai_compat.rs`).
- **Windows launch reliability** — [`run-claw.ps1`](./run-claw.ps1) changes the process working directory to the repo root before invoking `claw.exe`, so a `.env` next to `README.md` is found even when you start the script from another folder. [`run-claw.bat`](./run-claw.bat) runs `cd /d "%~dp0"` first for the same reason.
- **Command Prompt vs PowerShell** — Use one shell consistently; syntax is not interchangeable.

| Shell | Set OpenRouter env vars | Launch |
| ----- | ------------------------ | ------ |
| **Command Prompt** (`cmd.exe`) | `set OPENAI_BASE_URL=https://openrouter.ai/api/v1` then `set OPENAI_API_KEY=your_key` | From repo root: `run-claw.bat` (and pass args after it, e.g. `run-claw.bat doctor`). Use `cd /d D:\clawcodex` if you are on another drive. |
| **PowerShell** | `$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"` then `$env:OPENAI_API_KEY = "your_key"` | From repo root: `.\run-claw.ps1` |

More examples: [`USAGE.md`](./USAGE.md).

- **Bundled binary** — This repo may ship a prebuilt [`bin/windows/claw.exe`](./bin/windows/claw.exe). To match **current** Rust sources on your machine, run [`build-claw.ps1`](./build-claw.ps1) locally; source changes can be committed without re-committing that large binary every time.

## What is in this repo

- `rust/` - canonical Rust workspace and the `claw` CLI source
- `bin/windows/claw.exe` - bundled Windows build for quick local startup
- `run-claw.ps1` / `run-claw.bat` - launch helpers for Windows
- `build-claw.ps1` - rebuilds `bin/windows/claw.exe` from the Rust workspace
- `USAGE.md` - copy/paste setup, auth, and common command examples
- `PARITY.md` - parity and migration status
- `ROADMAP.md` - planned work and gaps
- `src/` and `tests/` - companion Python/reference surfaces that should stay aligned with runtime behavior

## Tool Call Surface

This distribution currently documents a 50-tool surface.

For clarity:

- `Baseline` means the core shell/file/search workflow most people expect from a coding agent.
- `Added` means the broader capabilities layered on top in this distribution: planning, structured output, web research, notebook editing, worker/task orchestration, MCP integration, cron/team tools, and runtime helpers.

The current tool surfaces come from [`rust/crates/tools/src/lib.rs`](./rust/crates/tools/src/lib.rs) plus the additional runtime/integration tools exercised by [`rust/crates/tools/src/bin/tool_audit.rs`](./rust/crates/tools/src/bin/tool_audit.rs).

### Baseline workspace tools

These are the closest match to the original/basic shell-plus-file-editing tool surface.

- `bash` - run shell commands in the workspace
- `read_file` - read file contents
- `write_file` - write file contents
- `edit_file` - replace text inside files
- `glob_search` - find files by glob pattern
- `grep_search` - search file contents by pattern

### Added shell and editing tools

- `PowerShell` - run Windows-native PowerShell commands
- `REPL` - execute code in a supported language REPL/runtime
- `NotebookEdit` - modify notebook cell contents

### Added web and discovery tools

- `WebFetch` - fetch a URL and answer a prompt about it
- `WebSearch` - search the web for current information
- `ToolSearch` - search the available tool registry

### Added planning and workflow tools

- `TodoWrite` - maintain a structured todo/task list
- `Skill` - invoke installed skills
- `Config` - inspect config state
- `Sleep` - pause for a short period during workflows
- `SendUserMessage` - send an explicit user-facing progress/update message
- `StructuredOutput` - emit structured/machine-readable output
- `EnterPlanMode` - switch into plan mode
- `ExitPlanMode` - leave plan mode
- `AskUserQuestion` - ask an explicit user question through the runtime

### Added task and agent orchestration tools

- `Agent` - create or invoke an agent workflow
- `TaskCreate` - create a tracked task
- `RunTaskPacket` - create a task from a structured task packet
- `TaskGet` - inspect one task
- `TaskList` - list tracked tasks
- `TaskStop` - stop a task
- `TaskUpdate` - update task status or metadata
- `TaskOutput` - retrieve task output

### Added worker lifecycle tools

- `WorkerCreate` - create a worker/session process
- `WorkerGet` - inspect worker state
- `WorkerObserve` - attach observation data to worker state
- `WorkerResolveTrust` - resolve workspace trust status for a worker
- `WorkerAwaitReady` - wait for a worker to become ready
- `WorkerSendPrompt` - send a prompt to a worker
- `WorkerRestart` - restart a worker
- `WorkerObserveCompletion` - record worker completion state
- `WorkerTerminate` - terminate a worker

### Added team and scheduling tools

- `TeamCreate` - create a team grouping for coordinated work
- `TeamDelete` - remove a team grouping
- `CronCreate` - create a cron/scheduled job
- `CronList` - list scheduled jobs
- `CronDelete` - delete a scheduled job

### Added integration and protocol tools

- `LSP` - interact with language-server-backed features
- `ListMcpResources` - list resources exposed by an MCP server
- `ReadMcpResource` - read a specific MCP resource
- `McpAuth` - inspect or handle MCP auth state
- `MCP` - invoke MCP-exposed tools
- `RemoteTrigger` - trigger a remote/integration action
- `TestingPermission` - exercise/testing hook for permission flows

### Which tools were added

If you compare this repo to the basic shell/file/search baseline, the baseline set is:

- `bash`
- `read_file`
- `write_file`
- `edit_file`
- `glob_search`
- `grep_search`

Everything else listed above is part of the expanded tool surface added in this distribution.

That means the added tools are:

- `PowerShell`
- `REPL`
- `NotebookEdit`
- `WebFetch`
- `WebSearch`
- `ToolSearch`
- `TodoWrite`
- `Skill`
- `Config`
- `Sleep`
- `SendUserMessage`
- `StructuredOutput`
- `EnterPlanMode`
- `ExitPlanMode`
- `AskUserQuestion`
- `Agent`
- `TaskCreate`
- `RunTaskPacket`
- `TaskGet`
- `TaskList`
- `TaskStop`
- `TaskUpdate`
- `TaskOutput`
- `WorkerCreate`
- `WorkerGet`
- `WorkerObserve`
- `WorkerResolveTrust`
- `WorkerAwaitReady`
- `WorkerSendPrompt`
- `WorkerRestart`
- `WorkerObserveCompletion`
- `WorkerTerminate`
- `TeamCreate`
- `TeamDelete`
- `CronCreate`
- `CronList`
- `CronDelete`
- `LSP`
- `ListMcpResources`
- `ReadMcpResource`
- `McpAuth`
- `MCP`
- `RemoteTrigger`
- `TestingPermission`

Not every tool is available in every environment. Some depend on configured MCP servers, worker state, cron/team state, local runtimes, or provider/network access. The main takeaway for users is that this repo is not only a shell/file editor: it also includes planning, web research, notebook editing, structured output, task and worker orchestration, and MCP-facing integration hooks.

## Quick Start

### Windows: run the bundled binary

Open PowerShell in the repo root and set **OpenRouter**:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
```

Then launch ClawCodex:

```powershell
.\run-claw.ps1
```

Useful first commands:

```powershell
.\run-claw.ps1 doctor
.\run-claw.ps1 prompt "say hello"
.\bin\windows\claw.exe --help
```

### Build from source

```powershell
cd .\rust
cargo build --workspace
.\target\debug\claw.exe doctor
.\target\debug\claw.exe prompt "say hello"
```

If you want to refresh the packaged Windows binary in `bin/windows/`:

```powershell
.\build-claw.ps1
```

## Authentication

This distribution documents **OpenRouter** as the supported path:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
```

Use an OpenRouter model id (for example `openai/gpt-4.1-mini` or another id from the OpenRouter catalog). Session resume and tooling flows are covered in [`USAGE.md`](./USAGE.md).

## First-Run Checklist

1. Install Rust from [rustup.rs](https://rustup.rs/) if you need to build locally.
2. Set OpenRouter (`OPENAI_BASE_URL` + `OPENAI_API_KEY`) in your shell or `.env`.
3. Run `claw doctor`.
4. Run a small prompt like `claw prompt "say hello"`.
5. If you are on Windows and using the packaged build, prefer `run-claw.ps1` or `run-claw.bat`.

## Troubleshooting

- If PowerShell blocks `run-claw.ps1`, use `run-claw.bat` or run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

- If `bin/windows/claw.exe` is missing or stale, run:

```powershell
.\build-claw.ps1
```

- If you get a 401, confirm `OPENAI_API_KEY` is your OpenRouter key and `OPENAI_BASE_URL` is `https://openrouter.ai/api/v1` (or copy [`.env.example`](./.env.example) to `.env` in the repo root).

- If a prompt fails and you are not sure why, run:

```powershell
.\run-claw.ps1 doctor
```

## Verification

From [`rust/`](./rust):

```powershell
cargo fmt
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

## Documentation Map

- [`USAGE.md`](./USAGE.md) - onboarding and command examples
- [`rust/README.md`](./rust/README.md) - workspace layout and crate responsibilities
- [`PARITY.md`](./PARITY.md) - current parity status
- [`rust/MOCK_PARITY_HARNESS.md`](./rust/MOCK_PARITY_HARNESS.md) - deterministic mock-service harness
- [`ROADMAP.md`](./ROADMAP.md) - planned work
- [`PHILOSOPHY.md`](./PHILOSOPHY.md) - project intent and design framing

## Upstream Context

This distribution is based on the broader Claw Code ecosystem and still references upstream command/status text in a few places. When command help mentions `ultraworkers/claw-code`, treat that as upstream source-of-truth context, not as a different binary name.

## Disclaimer

- This repository is for research and experimentation only.
- This repository does not claim ownership of the original Claude Code source material.
- This repository is not affiliated with, endorsed by, or maintained by Anthropic.
