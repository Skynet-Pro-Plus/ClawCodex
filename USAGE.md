# ClawCodex Usage

This guide is for people trying to get the engine running quickly from this repository.

## TL;DR (Windows)

1. Double-click [`START-CLAW.bat`](./START-CLAW.bat).
2. If no key is saved, or OpenRouter rejects the saved key, paste a valid OpenRouter key in that same Command Prompt window.
3. Claw saves it to local `.env`, verifies the key with OpenRouter, runs `doctor`, then launches; later runs validate the saved key before continuing.

**Credentials live in one place:** a file named `.env` in the **repo root** (same folder as `README.md`). The file is gitignored.

**`claw doctor` vs a real key:** `doctor` is a *local* report (files/env/workspace). It does **not** call OpenRouter, so it cannot tell you if the key is wrong. `START-CLAW.bat` does the live OpenRouter check before `doctor`. For a **terminal-friendly live check** (missing / placeholder / HTTP 401 / no response / OK):

- Double-click **[`CHECK-KEY.bat`](./CHECK-KEY.bat)** — the window **prints the full command** first, then runs it — or **[`OPEN-KEY-CHECK-WINDOW.bat`](./OPEN-KEY-CHECK-WINDOW.bat)** to open a **new** Command Prompt with the same flow. You can also run from the repo root:  
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-openrouter.ps1`  
- **`START-CLAW.bat`** runs this check automatically *before* `doctor`. If the key is missing, rejected, or OpenRouter gives no usable response, it prompts for a replacement key in the same terminal, saves it to `.env`, then revalidates before launching.

**Update the key from the terminal (no Notepad):** double-click **[`UPDATE-KEY.bat`](./UPDATE-KEY.bat)** or run  
`powershell -NoProfile -ExecutionPolicy Bypass -File .\set-openrouter-key.ps1`  
from the repo root. It prompts with **hidden input**, writes **`OPENAI_API_KEY`** into **`.env`**, then runs the same **live OpenRouter** check unless you pass **`-NoVerify`**.

## Fastest Path on Windows (one click)

1. Double-click **[`START-CLAW.bat`](./START-CLAW.bat)** in File Explorer (or use [`open-cmd-here.bat`](./open-cmd-here.bat) — same flow).
2. A Command Prompt opens and runs a **live authenticated OpenRouter check**. If the key is missing, invalid, or OpenRouter does not respond, the same terminal prompts for a replacement key with hidden input, saves **`.env`** next to `README.md`, and checks again.
3. After the key validates, the launcher runs **`claw doctor`** and starts Claw.
4. In that same window, run the engine anytime:
   - `run-claw.bat` — interactive REPL  
   - `run-claw.bat prompt "summarize this repository"`

If the OpenRouter model picker appears, the list is pre-filtered to Claw-compatible models (tool-calling + text-only output + large context). It excludes obvious TTS/STT/audio models that are not used by the coder, and each entry shows input/output token pricing per 1M tokens when OpenRouter provides pricing data.

If **`doctor` never asks for a key**, your `bin\windows\claw.exe` may be older than the source: from PowerShell run **`.\build-claw.ps1`**, then double-click **`START-CLAW.bat`** again.

**Manual `.env` instead:** copy [`.env.example`](./.env.example) to `.env`, edit `OPENAI_API_KEY` once, then `run-claw.bat doctor`.

**Interactive behavior details:** the save-once prompt runs for text `doctor` / REPL / text `prompt`. Set `CLAW_NO_CREDENTIAL_PROMPT=1` to disable (CI/scripts). JSON `doctor` skips the prompt.

**PowerShell:** `.\run-claw.ps1 doctor` / `.\run-claw.ps1` from the repo root — same binary, same `.env` rules.

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

`START-CLAW.bat` validates your key with a free, model-agnostic `GET /v1/auth/key` request. That proves a normal OpenRouter key works without spending tokens and without depending on any specific model allow-list. It is **not** the same as `GET /v1/credits`, which requires a **management** key and will 401 for standard keys.

**Default (recommended):** repo-root `.env` only—see [`.env.example`](./.env.example). You should not need to paste the same key into PowerShell, Bash, and docs; edit `.env` once. The Windows helper batch files temporarily clear inherited `OPENAI_API_KEY` and `OPENAI_BASE_URL` values so stale shell variables cannot shadow `.env` during validation.

**Optional (CI or advanced):** set the same variable names in the process environment instead of (or overriding) `.env`:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
```

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

Traffic goes to the host in `OPENAI_BASE_URL` (OpenRouter’s OpenAI-compatible API). Choose a model id OpenRouter exposes; namespaced ids such as `openai/...` map cleanly to the OpenAI-compatible wire path. If a request fails with auth errors, confirm both values are correct in **`.env`** (or in the environment) and that the model id exists on OpenRouter.

## 401 Fixes

- Use an OpenRouter key in `OPENAI_API_KEY` (keys often look like `sk-or-v1-...`), not a key from another vendor.
- Keep `OPENAI_BASE_URL` on `https://openrouter.ai/api/v1` unless OpenRouter documents a different base URL for your account type.

The CLI also reads `.env` beside `bin\windows\claw.exe` if you run the exe without going through the repo root; the **recommended** layout is still repo-root `.env` plus `run-claw.ps1` / `run-claw.bat`.

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
