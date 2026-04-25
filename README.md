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
  <img src="assets/claw-hero.jpeg" alt="ClawCodex hero image" width="300" />
</p>

ClawCodex is a packaged distribution of the `claw` CLI agent harness with the Rust workspace in [`rust/`](./rust) and a bundled Windows binary in [`bin/windows/claw.exe`](./bin/windows/claw.exe).

This repo is set up so a new user can:

1. Run the packaged Windows binary immediately.
2. Rebuild the binary from source when needed.
3. Use `claw doctor` as the first health check before deeper troubleshooting.

## What is in this repo

- `rust/` - canonical Rust workspace and the `claw` CLI source
- `bin/windows/claw.exe` - bundled Windows build for quick local startup
- `run-claw.ps1` / `run-claw.bat` - launch helpers for Windows
- `build-claw.ps1` - rebuilds `bin/windows/claw.exe` from the Rust workspace
- `USAGE.md` - copy/paste setup, auth, and common command examples
- `PARITY.md` - parity and migration status
- `ROADMAP.md` - planned work and gaps
- `src/` and `tests/` - companion Python/reference surfaces that should stay aligned with runtime behavior

## Quick Start

### Windows: run the bundled binary

Open PowerShell in the repo root and set a provider credential:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
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

Anthropic direct API:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
```

OpenRouter:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_API_KEY_HERE"
```

Ollama:

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:11434/v1"
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
```

See [`USAGE.md`](./USAGE.md) for OpenAI-compatible, xAI, DashScope, proxy, and session-resume flows.

## First-Run Checklist

1. Install Rust from [rustup.rs](https://rustup.rs/) if you need to build locally.
2. Set one provider credential in your shell.
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

- If you get a 401, double-check that you placed the credential in the correct env var. `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are not interchangeable.

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

- This repository does not claim ownership of the original Claude Code source material.
- This repository is not affiliated with, endorsed by, or maintained by Anthropic.
