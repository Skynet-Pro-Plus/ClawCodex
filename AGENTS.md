# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Filesystem conventions (Claw / Windows)

- **Prefer native file tools** for any file I/O: `write_file`, `read_file`, `edit_file`, `glob`, `grep_search`. They normalize paths correctly on Windows.
- **Accepted path forms** on Windows: `D:\ClawCodex\...` (native) or `/d/ClawCodex/...` (Git Bash / MSYS). The runtime maps these to the same underlying files. Legacy `/mnt/d/...` paths are still accepted by the file tools and normalized to the Windows drive.
- **Bash vs files**: Use `bash` for builds, git, and process orchestration — not as a substitute for `write_file` when creating or editing project files.
- **No WSL**: The shell backend is Windows-native only — Git Bash when installed, otherwise Windows PowerShell. WSL is never used or probed. Pin the backend explicitly with `CLAW_SHELL=bash` or `CLAW_SHELL=powershell` if needed.

## Runtime environment

- **OS**: Windows 11 (Git Bash / MSYS2 MINGW64 shell)
- **Project root**: `D:\ClawCodex\ClawCodex` — in bash use `/d/ClawCodex/ClawCodex` (Git Bash)
- **Python**: use `python` (Python 3.13 at `C:\Python313`) — NOT `python3`; both `python` and `pip` are on PATH
- **Package install**: `pip install <pkg>` works in bash
- **PowerShell**: available for Windows-specific tasks; the runtime falls back to it automatically when Git Bash is absent and rejects Linux-only commands with a translation hint
- **Rust / cargo**: `cargo` is on PATH (1.86.0)
- Common packages already installed: `openpyxl`

### Shell notes
- Prefer **native file tools** for creating/editing files; use bash for commands that need a shell.
- In **Git Bash**, paths can use MSYS2 form: `/d/ClawCodex/ClawCodex/`.
- Native Windows paths `D:\ClawCodex\ClawCodex\` work from PowerShell and from Claw's file tools.
- Do NOT use `cd D:/ClawCodex` in Git Bash if that fails in your environment; use `cd /d/ClawCodex/ClawCodex`.
- When the PowerShell backend is active, Linux idioms (`&&`, `/dev/null`, `touch`, `which`, `head`, …) are blocked before execution with a Windows equivalent suggested in the error.
- Avoid escaping issues: write Python scripts to a `.py` file then run `python file.py` rather than `python -c "..."` with complex quoting

## Detected stack
- Languages: Rust.
- Frameworks: none detected from the supported starter markers.

## Verification
- Run Rust verification from `rust/`: `cargo fmt`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`
- `src/` and `tests/` are both present; update both surfaces together when behavior changes.

## Repository shape
- `rust/` contains the Rust workspace and active CLI/runtime implementation.
- `src/` contains source files that should stay consistent with generated guidance and tests.
- `tests/` contains validation surfaces that should be reviewed alongside code changes.

## Working agreement
- Prefer small, reviewable changes and keep generated bootstrap files aligned with actual repo workflows.
- Keep shared defaults in `.Codex.json`; reserve `.Codex/settings.local.json` for machine-local overrides.
- Do not overwrite existing `AGENTS.md` content automatically; update it intentionally when repo workflows change.
