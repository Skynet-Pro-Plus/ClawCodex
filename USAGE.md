# ClawCodex Usage

This guide is for people trying to get the engine running quickly from this repository.

If you are brand new, make `doctor` your first command after setting OpenRouter credentials.

## Fastest Path on Windows

From the repo root in PowerShell:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
.\run-claw.ps1 doctor
.\run-claw.ps1
```

For a one-shot prompt:

```powershell
.\run-claw.ps1 prompt "summarize this repository"
```

If PowerShell script execution is blocked, use:

```powershell
.\run-claw.bat prompt "summarize this repository"
```

### Optional launcher with a placeholder API key line

[`run-claw.local.ps1`](./run-claw.local.ps1) is tracked in the repo with a placeholder (`PUT_YOUR_OPENROUTER_API_KEY_HERE`). Edit that one string to your real OpenRouter key, then run it like `.\run-claw.ps1`. If you put a real key in the file, **do not commit or push** that change to a public repository.

## Build From Source

```powershell
cd .\rust
cargo build --workspace
.\target\debug\claw.exe doctor
.\target\debug\claw.exe prompt "say hello"
```

Unix-like shells:

```bash
cd rust
cargo build --workspace
./target/debug/claw doctor
./target/debug/claw prompt "say hello"
```

## Credentials (OpenRouter)

PowerShell:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
```

Bash:

```bash
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="YOUR_OPENROUTER_KEY_HERE"
```

Pick a model from the OpenRouter catalog and pass `--model <id>` when needed (for example `openai/gpt-4.1-mini`).

## Common Commands

In the examples below, replace `claw` with whichever entrypoint you are using:

- `.\run-claw.ps1` from the repo root on Windows
- `.\target\debug\claw.exe` after building on Windows
- `./target/debug/claw` after building on Unix-like shells

Interactive REPL:

```bash
claw
```

One-shot prompt:

```bash
claw prompt "explain this repository"
```

Shorthand prompt mode:

```bash
claw "explain rust/crates/runtime/src/lib.rs"
```

Health check:

```bash
claw doctor
```

Current workspace snapshot:

```bash
claw status
```

Provider and config troubleshooting:

```bash
claw doctor
claw mcp
claw skills
```

Resume the newest saved session:

```bash
claw --resume latest
```

Export the newest saved session:

```bash
claw export
```

## Model and Permission Examples

```bash
claw --model sonnet prompt "review this diff"
claw --permission-mode read-only prompt "summarize Cargo.toml"
claw --permission-mode workspace-write prompt "update README.md"
claw --allowedTools read,glob "inspect the runtime crate"
```

Permission modes:

- `read-only`
- `workspace-write`
- `danger-full-access`

Built-in model aliases:

- `opus` -> `claude-opus-4-6`
- `sonnet` -> `claude-sonnet-4-6`
- `haiku` -> `claude-haiku-4-5-20251213`

## How routing works with OpenRouter

Traffic goes to the host in `OPENAI_BASE_URL` (OpenRouter’s OpenAI-compatible API). Choose a model id OpenRouter exposes; namespaced ids such as `openai/...` map cleanly to the OpenAI-compatible wire path. If a request fails with auth errors, confirm both `OPENAI_BASE_URL` and `OPENAI_API_KEY` are set and that the model id exists on OpenRouter.

## 401 Fixes

- Use an OpenRouter key in `OPENAI_API_KEY` (`sk-or-v1-...`), not a key from another vendor.
- Keep `OPENAI_BASE_URL` on `https://openrouter.ai/api/v1` unless OpenRouter documents a different base URL for your account type.

## Portable `.env`

The CLI help notes that a `.env` beside the executable or in the working directory can provide `OPENAI_API_KEY` and `OPENAI_BASE_URL` for portable OpenRouter-style setups. A starter template is included in [`.env.example`](./.env.example).

## Session Files

REPL turns are stored under `.claw/sessions/` in the current workspace.

Useful resume-safe slash commands:

- `/help`
- `/status`
- `/doctor`
- `/skills`
- `/agents`
- `/mcp`
- `/export`

## Verification

From `rust/`:

```bash
cargo fmt
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

## Notes

- `cargo install claw-code` is not the install path for this repo.
- If the packaged Windows binary is missing or stale, run `.\build-claw.ps1`.
- Some live help text still mentions upstream `ultraworkers/claw-code`; that is upstream context, not a different project name for this distribution.
