# ClawCodex Usage

This guide is for people trying to get the engine running quickly from this repository.

If you are brand new, make `doctor` your first command after setting credentials.

## Fastest Path on Windows

From the repo root in PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
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

## Credentials

### Anthropic API key

PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
```

Bash:

```bash
export ANTHROPIC_API_KEY="YOUR_API_KEY_HERE"
```

### Anthropic bearer token

Use this only for an OAuth/proxy bearer token, not for an `sk-ant-*` API key.

```bash
export ANTHROPIC_AUTH_TOKEN="anthropic-oauth-or-proxy-bearer-token"
```

### OpenRouter

```bash
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="YOUR_API_KEY_HERE"
```

### Ollama

```bash
export OPENAI_BASE_URL="http://127.0.0.1:11434/v1"
unset OPENAI_API_KEY
```

### DashScope / Qwen

```bash
export DASHSCOPE_API_KEY="YOUR_API_KEY_HERE"
```

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

## How Provider Detection Works

1. If the model starts with `claude`, Claw uses the Anthropic provider.
2. If the model starts with `grok`, Claw uses xAI.
3. If the model starts with `openai/`, `gpt-`, `qwen/`, or `qwen-`, Claw uses the OpenAI-compatible path.
4. Otherwise Claw falls back to whichever matching credential is present.

## 401 Fixes

The most common auth mistake is putting an `sk-ant-*` API key into `ANTHROPIC_AUTH_TOKEN`.

Use:

- `ANTHROPIC_API_KEY` for Anthropic API keys
- `ANTHROPIC_AUTH_TOKEN` for bearer tokens from a proxy or OAuth flow

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
