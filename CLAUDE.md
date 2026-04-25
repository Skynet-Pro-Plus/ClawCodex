# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Filesystem conventions (Claw / Windows)

- **Prefer native file tools** for any file I/O: `write_file`, `read_file`, `edit_file`, `glob`, `grep_search`. They normalize paths correctly on Windows.
- **Accepted path forms** on Windows: `D:\Johnny\...` (native), `/d/Johnny/...` (Git Bash / MSYS), or `/mnt/d/Johnny/...` (WSL-style). The runtime maps these to the same underlying files.
- **Bash vs files**: Use `bash` for builds, git, and process orchestration — not as a substitute for `write_file` when creating or editing project files.
- **WSL caveat**: If the host runs the bash tool through WSL, `/d/...` is *not* the same as the Windows `D:\` drive unless rewritten to `/mnt/d/...`. Claw rewrites MSYS-style `/x/...` segments automatically for the WSL backend; `D:\...` and `/mnt/d/...` remain the most explicit forms.

## Runtime environment

- **OS**: Windows 11 (Git Bash / MSYS2 MINGW64 shell)
- **Project root**: `D:\Johnny\Johnny` — in bash use `/d/Johnny/Johnny` (Git Bash) or `/mnt/d/Johnny/Johnny` (WSL)
- **Python**: use `python` (Python 3.13 at `C:\Python313`) — NOT `python3`; both `python` and `pip` are on PATH
- **Package install**: `pip install <pkg>` works in bash
- **PowerShell**: available for Windows-specific tasks; use `powershell -Command "..."` from bash
- **Rust / cargo**: `cargo` is on PATH (1.86.0)
- Common packages already installed: `openpyxl`

### Shell notes
- Prefer **native file tools** for creating/editing files; use bash for commands that need a shell.
- In **Git Bash**, paths can use MSYS2 form: `/d/Johnny/Johnny/`. In **WSL**, use `/mnt/d/Johnny/Johnny/` for the same Windows tree.
- Native Windows paths `D:\Johnny\Johnny\` work from PowerShell and from Claw's file tools.
- Do NOT use `cd D:/Johnny` in Git Bash if that fails in your environment; use `cd /d/Johnny/Johnny` (or `/mnt/d/...` under WSL).
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
- Keep shared defaults in `.claude.json`; reserve `.claude/settings.local.json` for machine-local overrides.
- Do not overwrite existing `CLAUDE.md` content automatically; update it intentionally when repo workflows change.
