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

## Install And Run (Windows)

ClawCodex is ready to run from this repo on Windows. The upgraded launcher handles the OpenRouter setup for you.

If you do not have the repo yet:

```powershell
git clone https://github.com/Skynet-Pro-Plus/ClawCodex C:\clawcodex
cd C:\clawcodex
```

1. Open the repo folder, for example `C:\clawcodex`.
2. Double-click [`START-CLAW.bat`](./START-CLAW.bat).
3. If no OpenRouter key is saved, paste your key in that same Command Prompt window. Input is hidden.
4. The launcher saves the key to repo-root `.env`, validates it with OpenRouter using `GET /v1/auth/key`, runs `claw doctor`, and starts Claw.
5. Future launches re-check the saved key before starting, so bad or stale keys are caught before the engine opens.

Useful follow-up commands from the repo root:

```bat
run-claw.bat
run-claw.bat prompt "say hello"
CHECK-KEY.bat
UPDATE-KEY.bat
```

Use [`CHECK-KEY.bat`](./CHECK-KEY.bat) to verify the saved key without launching Claw. Use [`UPDATE-KEY.bat`](./UPDATE-KEY.bat) to replace the key from the terminal without opening Notepad.

This repo is set up so a new user can:

1. **Windows:** double-click [`START-CLAW.bat`](./START-CLAW.bat) — Command Prompt opens, validates the saved OpenRouter key with a live authenticated request, prompts in the same terminal if the key is missing/invalid/no-response, saves a valid key to repo-root `.env`, then runs `claw doctor` and launches automatically.
2. Run the packaged Windows binary from `run-claw.bat` / `run-claw.ps1` anytime.
3. Rebuild the binary from source when needed ([`build-claw.ps1`](./build-claw.ps1)).

## Recent updates

- **OpenRouter-first documentation and health checks** — Put credentials **once** in a repo-root `.env` (copy from [`.env.example`](./.env.example)); `claw` reads it from the working directory. [`USAGE.md`](./USAGE.md) and Quick Start below follow that path so users are not asked to paste the same key in many places. `START-CLAW.bat` performs a free, model-agnostic `GET /v1/auth/key` OpenRouter key check before `claw doctor`; `doctor` remains a local-only health report. The API crate exposes `read_openai_base_url_explicit()` so diagnostics only treat an **explicit** `OPENAI_BASE_URL` as configured (see `rust/crates/api/src/providers/openai_compat.rs`).
- **One-click Windows setup** — Double-click [`START-CLAW.bat`](./START-CLAW.bat) (same as [`open-cmd-here.bat`](./open-cmd-here.bat)): Command Prompt at repo root, live OpenRouter key validation first, same-window hidden key prompt if needed, `doctor` after validation, then automatic launch into Claw. [`run-claw.bat`](./run-claw.bat) invokes `claw.exe` directly (no PowerShell).
- **First-run prompt behavior** — The prompt is in the same terminal window, not a pop-up. If `.env` already contains a usable OpenRouter key, the prompt is skipped and Claw starts immediately. `START-CLAW.bat` clears inherited `CLAW_NO_CREDENTIAL_PROMPT`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` for the one-click interactive path so stale shell settings cannot mute setup or shadow `.env`; scripted callers can still use `CLAW_NO_CREDENTIAL_PROMPT=1` with `run-claw.bat`.
- **Windows-friendly OpenRouter model picker** — The initial model list now filters to Claw-compatible entries (tool-calling + text-only output + large context windows), excludes obvious TTS/STT/audio models that are not useful for coding, and shows token pricing next to each model (`in/out` cost per 1M tokens) when OpenRouter returns pricing metadata.
- **Command Prompt vs PowerShell** — Use one shell consistently; syntax is not interchangeable.

| Shell | Easiest setup | Launch (repo root) |
| ----- | -------------- | ------------------ |
| **Command Prompt** | Double-click **`START-CLAW.bat`**, paste/update key if asked, then Claw starts after live validation. | `run-claw.bat …` |
| **Manual / PowerShell** | Copy [`.env.example`](./.env.example) → `.env`, or `.\run-claw.ps1 …` | `.\run-claw.ps1 …` |

More detail: [`USAGE.md`](./USAGE.md).

- **Bundled binary** — This repo may ship a prebuilt [`bin/windows/claw.exe`](./bin/windows/claw.exe). To match **current** Rust sources on your machine, run [`build-claw.ps1`](./build-claw.ps1) locally; source changes can be committed without re-committing that large binary every time.

## What is in this repo

- `rust/` - canonical Rust workspace and the `claw` CLI source
- `bin/windows/claw.exe` - bundled Windows build for quick local startup
- `START-CLAW.bat` / `open-cmd-here.bat` - one-click Command Prompt onboarding, live OpenRouter key validation, `doctor`, and automatic Claw launch
- `run-claw.bat` / `run-claw.ps1` - launch `claw.exe` from the repo root
- `.env.example` - template for a **single** repo-root `.env` (gitignored) holding OpenRouter credentials
- `build-claw.ps1` - rebuilds `bin/windows/claw.exe` from the Rust workspace
- `USAGE.md` - setup, auth, and common command examples
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

**Easiest:** double-click [`START-CLAW.bat`](./START-CLAW.bat). Command Prompt opens at the repo root, performs a live OpenRouter key check, asks for a key if `.env` is missing/empty/rejected, saves and revalidates it, then runs `claw doctor` and launches Claw automatically.

When the OpenRouter model picker appears, it shows only Claw-compatible text/tool models with large context windows. Obvious TTS/STT/audio models are filtered out, and input/output pricing per 1M tokens is shown when OpenRouter provides pricing metadata.

**Manual:** copy [`.env.example`](./.env.example) to `.env`, set `OPENAI_API_KEY`, then run [`CHECK-KEY.bat`](./CHECK-KEY.bat) to validate it. After the key is accepted, launch with [`run-claw.bat`](./run-claw.bat) or [`run-claw.ps1`](./run-claw.ps1).

From PowerShell in the repo root (optional):

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

This distribution documents **OpenRouter** as the supported path. Configure it **once** in repo-root `.env` (see [`.env.example`](./.env.example)), or let [`START-CLAW.bat`](./START-CLAW.bat) / [`UPDATE-KEY.bat`](./UPDATE-KEY.bat) write it for you. The validator uses OpenRouter's free, model-agnostic `GET /v1/auth/key` endpoint, so validation does not spend tokens and does not depend on a specific model allow-list.

Use an OpenRouter model id (for example `openai/gpt-4.1-mini` or another id from the OpenRouter catalog). Session resume and tooling flows are covered in [`USAGE.md`](./USAGE.md).

## First-Run Checklist

1. **Windows:** double-click [`START-CLAW.bat`](./START-CLAW.bat) (or copy `.env.example` to `.env` by hand).
2. Install Rust from [rustup.rs](https://rustup.rs/) if you need to build locally or refresh `bin\windows\claw.exe` via [`build-claw.ps1`](./build-claw.ps1).
3. Run [`CHECK-KEY.bat`](./CHECK-KEY.bat) if you manually edited `.env` and want to verify the key before launching.
4. Run `claw doctor` if you did not use `START-CLAW.bat` (it runs doctor for you).
5. If Claw did not already launch from `START-CLAW.bat`, run a small prompt like `run-claw.bat prompt "say hello"` or `.\run-claw.ps1 prompt "say hello"`.
6. Prefer `START-CLAW.bat` for one-click Command Prompt startup, `run-claw.bat` for existing Command Prompt windows, or `.\run-claw.ps1` in PowerShell.

## Troubleshooting

- If PowerShell blocks `run-claw.ps1`, use `run-claw.bat` or run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

- If `bin/windows/claw.exe` is missing or stale, run:

```powershell
.\build-claw.ps1
```

If the script reports **`claw.exe.new`** instead of updating `claw.exe`, another program has the old binary open—close it, then replace `bin\windows\claw.exe` with `claw.exe.new` (or run `build-claw.ps1` again).

- If `doctor` says `OpenRouter credentials are configured`, the first-run prompt already completed. The saved values live in repo-root `.env`; `START-CLAW.bat` will revalidate them before future launches.

- If `doctor` says `OpenRouter key prompt skipped (CLAW_NO_CREDENTIAL_PROMPT=1)`, use [`START-CLAW.bat`](./START-CLAW.bat) for the interactive setup flow or unset that variable before running `run-claw.bat doctor`. `CLAW_NO_CREDENTIAL_PROMPT=1` is intended for CI/scripts.

- If you get a 401, run [`CHECK-KEY.bat`](./CHECK-KEY.bat) and confirm the printed key fingerprint matches the OpenRouter key saved in `.env`. Also confirm `OPENAI_BASE_URL` is `https://openrouter.ai/api/v1` (or copy [`.env.example`](./.env.example) to `.env` in the repo root).

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

## Credits

**Johnny Export** — This repository explicitly credits Johnny Export for his work and philosophy: treating autonomous agent coordination (not only the files on disk) as the product lesson, and centering the idea that **humans set direction while claws perform the labor**. See [`PHILOSOPHY.md`](./PHILOSOPHY.md) for the full framing and acknowledgment.

## Upstream Context

This distribution is based on the broader Claw Code ecosystem and still references upstream command/status text in a few places. When command help mentions `ultraworkers/claw-code`, treat that as upstream source-of-truth context, not as a different binary name.

## Disclaimer

- This repository is for research and experimentation only.
- This repository does not claim ownership of the original Claude Code source material.
- This repository is not affiliated with, endorsed by, or maintained by Anthropic.
