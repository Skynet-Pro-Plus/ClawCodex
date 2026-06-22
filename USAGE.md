# ClawCodex Usage

This guide is for people trying to get the engine running quickly from this repository.

## TL;DR (Windows)

1. Double-click [`START-CLAW.bat`](./START-CLAW.bat).
2. Choose **OpenRouter**, **Cerebras**, **Z.ai**, **DeepSeek**, or **Kimi**.
3. If no key is saved, or the selected provider rejects the saved key, paste a valid key in that same Command Prompt window.
4. Claw saves it to local `.env`, verifies the key live, then launches (OpenRouter runs `doctor`; Cerebras/Z.ai/DeepSeek/Kimi launch directly with the selected model).

**Credentials live in one place:** a file named `.env` in the **repo root** (same folder as `README.md`). The file is gitignored.

**`claw doctor` vs a real key:** `doctor` is a *local* report (files/env/workspace). It does **not** call provider model endpoints, so it cannot tell you if the key is wrong. `START-CLAW.bat` does a live provider check first. For a **terminal-friendly live OpenRouter check** (missing / placeholder / HTTP 401 / no response / OK):

- Double-click **[`CHECK-KEY.bat`](./CHECK-KEY.bat)** — the window **prints the full command** first, then runs it — or **[`OPEN-KEY-CHECK-WINDOW.bat`](./OPEN-KEY-CHECK-WINDOW.bat)** to open a **new** Command Prompt with the same flow. You can also run from the repo root:  
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-openrouter.ps1`  
- **`START-CLAW.bat`** runs provider validation automatically. If the selected provider key is missing or rejected, it prompts for a replacement key in the same terminal, saves it to `.env`, then revalidates before launching.

**Update the key from the terminal (no Notepad):** double-click **[`UPDATE-KEY.bat`](./UPDATE-KEY.bat)** or run  
`powershell -NoProfile -ExecutionPolicy Bypass -File .\set-openrouter-key.ps1`  
from the repo root. It prompts with **hidden input**, writes **`OPENAI_API_KEY`** into **`.env`**, then runs the same **live OpenRouter** check unless you pass **`-NoVerify`**.

## Fastest Path on Windows (one click)

1. Double-click **[`START-CLAW.bat`](./START-CLAW.bat)** in File Explorer (or use [`open-cmd-here.bat`](./open-cmd-here.bat) — same flow).
2. A Command Prompt opens with a provider menu (OpenRouter/Cerebras/Z.ai/DeepSeek/Kimi), then runs a **live authenticated provider check**. If the key is missing or invalid, the same terminal prompts for a replacement key with hidden input, saves **`.env`** next to `README.md`, and checks again.
3. After the key validates, the launcher starts Claw. OpenRouter runs **`claw doctor`** first; Cerebras, Z.ai, DeepSeek, and Kimi launch directly with `--model`.
4. In that same window, run the engine anytime:
   - `run-claw.bat` — interactive REPL  
   - `run-claw.bat prompt "summarize this repository"`

If the OpenRouter model picker appears, the list is pre-filtered to Claw-compatible models (tool-calling + text-only output + large context). It excludes obvious TTS/STT/audio models that are not used by the coder, and each entry shows input/output token pricing per 1M tokens when OpenRouter provides pricing data.

If Z.ai is selected, the picker loads `GET https://open.bigmodel.cn/api/paas/v4/models`, filters to IDs starting with `glm-4` or `glm-5` (the endpoint does not expose a `supports_tools` boolean), defaults to `glm-5.2` when available, and lets you override by number or exact model ID.

If DeepSeek is selected, the picker loads `GET https://api.deepseek.com/models`, prefers non-deprecated `deepseek-*` models, defaults to `deepseek-v4-flash` when available (otherwise `deepseek-v4-pro`), and still allows override by number or exact model ID.

If Kimi is selected, the picker loads `GET https://api.moonshot.ai/v1/models`, prefers current `kimi-*` models, defaults to `kimi-k2.7-code` when available, and still allows override by number or exact model ID.

If **`doctor` never asks for a key**, your `bin\windows\claw.exe` may be older than the source: from PowerShell run **`.\build-claw.ps1`**, then double-click **`START-CLAW.bat`** again.

**Manual `.env` instead:** copy [`.env.example`](./.env.example) to `.env`, edit `OPENAI_API_KEY` once, then `run-claw.bat doctor`.

**Interactive behavior details:** the save-once prompt runs for text `doctor` / REPL / text `prompt`. Set `CLAW_NO_CREDENTIAL_PROMPT=1` to disable (CI/scripts). JSON `doctor` skips the prompt.

**PowerShell:** `.\run-claw.ps1 doctor` / `.\run-claw.ps1` from the repo root — same binary, same `.env` rules.

## Local Dashboard Workflow

The dashboard is a local FastAPI + React interface for running staged coding missions with approval gates.

From the repo root, build the frontend once:

```powershell
cd .\frontend
npm install
npm run build
cd ..
```

Start the backend/API server:

```powershell
$env:PYTHONPATH = "$PWD"
python -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The server returns `/health` for smoke checks and serves the built dashboard from `frontend/dist`.

Mission flow:

1. Enter a repo path and prompt in Mission Control.
2. ClawCodex creates a task and runs `PLAN`.
3. The mission pauses at `PLAN`; review the visible plan preview and the Latest Plan card.
4. Click **Approve Plan and Code** to run `CODE`, or cancel/stop the mission.
5. Review generated diffs before they are written.
6. After approval, tests and review phases run when enabled.

Navigation pages:

- **Missions** lists recent tasks and supports open, stop, and delete.
- **Repositories** lists recently used repo paths and can reuse one in the composer.
- **Templates** shows rule packs found under `clawcodex-packs/`.
- **Integrations** shows OpenRouter key status and model settings.

Rules and prompt handling:

- Built-in safety rules always apply.
- Workspace rules and enabled rule packs are summarized on each mission timeline.
- Pack toggles in the Rules panel are saved into the next task's model config.
- Common extension typos in prompts are corrected before task creation when confidence is high, for example `loan.xlxs` to `loan.xlsx`; uncertain corrections ask first.

Test status behavior:

- If no automated test harness is detected, the mission records tests as **skipped**, not blocked.
- Static HTML files proposed by a mission can still be checked for parse-level validity.

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

## Credentials (Providers)

`START-CLAW.bat` validates your key with a free, model-agnostic `GET /v1/auth/key` request. That proves a normal OpenRouter key works without spending tokens and without depending on any specific model allow-list. It is **not** the same as `GET /v1/credits`, which requires a **management** key and will 401 for standard keys.

For Cerebras, Z.ai, and DeepSeek, launcher validation uses live `GET /models` checks on each provider's OpenAI-compatible base URL. Kimi validation uses `GET /v1/models` at `https://api.moonshot.ai/v1`.

**Default (recommended):** repo-root `.env` only—see [`.env.example`](./.env.example). You should not need to paste the same key into PowerShell, Bash, and docs; edit `.env` once. When both repo `.env` and process `OPENAI_API_KEY` / `OPENAI_BASE_URL` are present, Claw prefers the repo `.env`.

**Optional (CI or advanced):** set the same variable names in the process environment when no repo `.env` is present:

```powershell
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENAI_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
```

```bash
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_API_KEY="YOUR_OPENROUTER_KEY_HERE"
```

Pick a model from the OpenRouter catalog and pass `--model <id>` when needed (for example `openai/gpt-4.1-mini`).

Z.ai defaults:

- `CLAW_PROVIDER=zai`
- `ZAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4`
- `ZAI_API_KEY=<your key>`
- `CLAW_ZAI_MODEL=glm-5.2`

Useful Z.ai commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-zai.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-zai-key.ps1
```

DeepSeek defaults:

- `CLAW_PROVIDER=deepseek`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_API_KEY=<your key>`
- `CLAW_DEEPSEEK_MODEL=deepseek-v4-flash`

The DeepSeek docs identify `deepseek-chat` and `deepseek-reasoner` as compatibility models being deprecated, so the launcher picker treats them as fallback options.

Useful DeepSeek commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-deepseek.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-deepseek-key.ps1
```

Kimi defaults:

- `CLAW_PROVIDER=kimi`
- `KIMI_BASE_URL=https://api.moonshot.ai/v1`
- `KIMI_API_KEY=<your key>`
- `MOONSHOT_API_KEY=<same key (compatibility alias)>`
- `CLAW_KIMI_MODEL=kimi-k2.7-code`

Kimi K2.7 Code is a thinking-first coding model. If multi-step tool calling errors mention missing `reasoning_content`, keep assistant reasoning fields intact in the conversation transcript during tool loops.

Useful Kimi commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\validate-kimi.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\set-kimi-key.ps1
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

## Security Boundaries

Hooks are local automation, not passive configuration. Only enable hook configs you trust, because hook commands run through the host shell with the same user privileges as Claw and can inspect tool input/output.

Sandboxing is strongest on Linux hosts where user namespaces are available. On Windows and macOS, permission mode still controls Claw's policy decisions, but it should not be treated as a strong OS-level sandbox.

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
