//! First-run OpenRouter setup: prompt once, write repo-root `.env`, set process env.
//!
//! Skipped when `CLAW_NO_CREDENTIAL_PROMPT=1`, JSON doctor output, or credentials are already usable.
//! `doctor` uses [`ensure_openrouter_credentials_for_doctor`] (no model-metadata gate) so setup
//! never fails silently. REPL / `prompt` still gate on [`ensure_openrouter_credentials_if_needed`].
//!
//! `.env` is written next to the git worktree root when `git rev-parse --show-toplevel`
//! succeeds (so saving from `rust/` still lands next to `README.md`).

use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

use api::{metadata_for_model, read_openai_api_key, read_openai_base_url_explicit};

const OPENROUTER_BASE: &str = "https://openrouter.ai/api/v1";

fn looks_like_placeholder_api_key(value: &str) -> bool {
    let t = value.trim();
    t.is_empty()
        || t.eq_ignore_ascii_case("YOUR_OPENROUTER_KEY_HERE")
        || t.contains("YOUR_OPENROUTER_KEY")
        || t.contains("PASTE_YOUR_OPENROUTER")
        || t.contains("PUT_YOUR_OPENROUTER")
}

fn openrouter_credentials_usable() -> bool {
    let Some(key) = read_openai_api_key() else {
        return false;
    };
    if looks_like_placeholder_api_key(&key) {
        return false;
    }
    read_openai_base_url_explicit()
        .as_deref()
        .is_some_and(|value| value.to_lowercase().contains("openrouter"))
}

fn model_uses_openai_api_key_env(model: &str) -> bool {
    metadata_for_model(model).is_some_and(|meta| meta.auth_env == "OPENAI_API_KEY")
}

fn credential_prompt_allowed() -> bool {
    env::var("CLAW_NO_CREDENTIAL_PROMPT").ok().as_deref() != Some("1")
}

/// Prefer git worktree root so `.env` lives beside `README.md` even when cwd is `rust/`.
fn resolve_dotenv_parent_dir() -> PathBuf {
    let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    git_rev_parse_show_toplevel(&cwd).unwrap_or(cwd)
}

fn git_rev_parse_show_toplevel(start: &Path) -> Option<PathBuf> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(start)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let path = String::from_utf8(output.stdout).ok()?.trim().to_string();
    if path.is_empty() {
        return None;
    }
    let root = PathBuf::from(path);
    root.is_dir().then_some(root)
}

/// Merge `OPENAI_BASE_URL` / `OPENAI_API_KEY` into `.env` in `root`, preserving other lines.
fn write_repo_dotenv(root: &Path, api_key: &str) -> io::Result<()> {
    let path = root.join(".env");
    let mut kept: Vec<String> = Vec::new();
    if path.exists() {
        for line in fs::read_to_string(&path)?.lines() {
            let t = line.trim();
            if t.is_empty() || t.starts_with('#') {
                kept.push(line.to_string());
                continue;
            }
            if t.starts_with("OPENAI_API_KEY=") || t.starts_with("OPENAI_BASE_URL=") {
                continue;
            }
            kept.push(line.to_string());
        }
    }
    while kept.last().is_some_and(|s| s.trim().is_empty()) {
        kept.pop();
    }
    let mut out = kept.join("\n");
    if !out.is_empty() {
        out.push('\n');
    }
    out.push_str(&format!("OPENAI_BASE_URL={OPENROUTER_BASE}\n"));
    out.push_str(&format!("OPENAI_API_KEY={api_key}\n"));
    fs::write(&path, &out)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&path)?.permissions();
        perms.set_mode(0o600);
        fs::set_permissions(&path, perms)?;
    }
    Ok(())
}

fn read_api_key_interactive() -> Result<String, Box<dyn std::error::Error>> {
    // All prompts on stderr so they show reliably under cmd.exe / double-clicked .bat.
    eprintln!();
    eprintln!("------------------------------------------------------------------");
    eprintln!("  Paste your OpenRouter API key below and press Enter.");
    eprintln!("  (No pop-up window — type in this same console.)");
    eprintln!("  It will be saved to .env in the repo root.");
    eprintln!("------------------------------------------------------------------");
    eprintln!();
    eprint!("OpenRouter API key: ");
    io::stderr().flush()?;
    let mut line = String::new();
    io::stdin().read_line(&mut line)?;
    let trimmed = line.trim().to_string();
    if trimmed.is_empty() {
        return Err("no API key entered".into());
    }
    Ok(trimmed)
}

fn try_interactive_openrouter_save(
    allow_interactive: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if openrouter_credentials_usable() {
        return Ok(());
    }
    if !allow_interactive {
        return Ok(());
    }
    if !credential_prompt_allowed() {
        eprintln!("Note: OpenRouter key prompt skipped (CLAW_NO_CREDENTIAL_PROMPT=1). Unset it to be prompted.");
        return Ok(());
    }

    let root = resolve_dotenv_parent_dir();
    eprintln!();
    eprintln!("OpenRouter API key not found (no usable OPENAI_API_KEY + OpenRouter base URL).");
    eprintln!("You will type your key on the next line. It will be saved to:");
    eprintln!("  {}", root.join(".env").display());
    eprintln!("Add `.env` to `.gitignore` if this repo is public. Disable this prompt with CLAW_NO_CREDENTIAL_PROMPT=1.");
    eprintln!();
    io::stderr().flush()?;

    let key = read_api_key_interactive()?;
    let trimmed = key.trim();
    if looks_like_placeholder_api_key(trimmed) {
        return Err(
            "that value still looks like a placeholder; use your real OpenRouter key.".into(),
        );
    }

    write_repo_dotenv(&root, trimmed)?;
    env::set_var("OPENAI_API_KEY", trimmed);
    env::set_var("OPENAI_BASE_URL", OPENROUTER_BASE);
    eprintln!("Saved. Continuing…");
    eprintln!();
    Ok(())
}

/// `claw doctor` entrypoint: always offer OpenRouter setup when creds are missing (no model gate).
pub fn ensure_openrouter_credentials_for_doctor(
    allow_interactive: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    try_interactive_openrouter_save(allow_interactive)
}

/// REPL / `prompt`: only when the resolved model uses `OPENAI_API_KEY` (OpenRouter/OpenAI-compat path).
pub fn ensure_openrouter_credentials_if_needed(
    model: &str,
    allow_interactive: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if !model_uses_openai_api_key_env(model) {
        return Ok(());
    }
    try_interactive_openrouter_save(allow_interactive)
}
