# ClawCodex Rust Workspace

This directory contains the Rust implementation of the `claw` CLI and its supporting crates.

For the quickest onboarding path, use [`../USAGE.md`](../USAGE.md). That guide is the copy/paste setup surface for first-time users.

## Quick Start

```bash
cd rust
cargo build --workspace
./target/debug/claw doctor
./target/debug/claw prompt "say hello"
```

On Windows PowerShell:

```powershell
cd .\rust
cargo build --workspace
.\target\debug\claw.exe doctor
.\target\debug\claw.exe prompt "say hello"
```

## What This Workspace Contains

- `api` - provider clients, request types, streaming, and auth helpers
- `commands` - slash-command registry and help rendering
- `compat-harness` - upstream manifest extraction and compatibility surfaces
- `mock-anthropic-service` - deterministic local Anthropic-compatible test service
- `plugins` - plugin metadata and install/enable/disable flows
- `runtime` - session runtime, permissions, config loading, MCP lifecycle, prompts
- `rusty-claude-cli` - the `claw` binary crate
- `telemetry` - usage and session telemetry types
- `tools` - built-in tool definitions and execution layer

## Representative Commands

```bash
cargo run -p rusty-claude-cli -- --help
cargo run -p rusty-claude-cli -- doctor
cargo run -p rusty-claude-cli -- prompt "explain this codebase"
cargo run -p rusty-claude-cli -- --output-format json prompt "summarize src/main.rs"
```

## Authentication

Anthropic direct API:

```bash
export ANTHROPIC_API_KEY="YOUR_API_KEY_HERE"
```

Anthropic bearer token:

```bash
export ANTHROPIC_AUTH_TOKEN="anthropic-oauth-or-proxy-bearer-token"
```

OpenAI-compatible or OpenRouter:

```bash
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="YOUR_API_KEY_HERE"
```

## Mock Parity Harness

```bash
cd rust
./scripts/run_mock_parity_harness.sh
```

Manual mock service startup:

```bash
cargo run -p mock-anthropic-service -- --bind 127.0.0.1:0
```

## Verification

```bash
cargo fmt
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

## Current Notes

- The live CLI help still mentions upstream `ultraworkers/claw-code` in a few places.
- `claw doctor` is the best first stop for setup issues.
- The packaged Windows binary in the repo root is rebuilt by `../build-claw.ps1`.
