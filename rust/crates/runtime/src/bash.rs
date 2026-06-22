use std::env;
use std::io;
use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tokio::process::Command as TokioCommand;
use tokio::runtime::Builder;
use tokio::time::timeout;

use crate::sandbox::{
    build_linux_sandbox_command, resolve_sandbox_status_for_request, FilesystemIsolationMode,
    SandboxConfig, SandboxStatus,
};
use crate::ConfigLoader;

const MIN_SHELL_TIMEOUT_MS: u64 = 5_000;
const BACKGROUND_LAUNCH_GRACE_MS: u64 = 750;
const BACKGROUND_LAUNCH_POLL_MS: u64 = 25;

static BACKGROUND_PIDS: OnceLock<Mutex<Vec<u32>>> = OnceLock::new();

fn background_pids() -> &'static Mutex<Vec<u32>> {
    BACKGROUND_PIDS.get_or_init(|| Mutex::new(Vec::new()))
}

/// Kill all background processes spawned by claw and clear the registry.
/// Called during shutdown so closing the window leaves no orphaned processes.
pub fn kill_background_processes() {
    let Ok(mut pids) = background_pids().lock() else {
        return;
    };
    let to_kill: Vec<u32> = pids.drain(..).collect();
    drop(pids);
    for pid in to_kill {
        kill_pid(pid);
    }
}

fn kill_pid(pid: u32) {
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

/// Input schema for the built-in bash execution tool.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BashCommandInput {
    pub command: String,
    pub timeout: Option<u64>,
    pub description: Option<String>,
    #[serde(rename = "run_in_background")]
    pub run_in_background: Option<bool>,
    #[serde(rename = "dangerouslyDisableSandbox")]
    pub dangerously_disable_sandbox: Option<bool>,
    #[serde(rename = "namespaceRestrictions")]
    pub namespace_restrictions: Option<bool>,
    #[serde(rename = "isolateNetwork")]
    pub isolate_network: Option<bool>,
    #[serde(rename = "filesystemMode")]
    pub filesystem_mode: Option<FilesystemIsolationMode>,
    #[serde(rename = "allowedMounts")]
    pub allowed_mounts: Option<Vec<String>>,
    /// When set, the shell runs with this working directory instead of the process CWD.
    #[serde(default)]
    pub cwd: Option<PathBuf>,
}

/// Output returned from a bash tool invocation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BashCommandOutput {
    pub stdout: String,
    pub stderr: String,
    #[serde(rename = "rawOutputPath")]
    pub raw_output_path: Option<String>,
    pub interrupted: bool,
    #[serde(rename = "isImage")]
    pub is_image: Option<bool>,
    #[serde(rename = "backgroundTaskId")]
    pub background_task_id: Option<String>,
    #[serde(rename = "backgroundedByUser")]
    pub backgrounded_by_user: Option<bool>,
    #[serde(rename = "assistantAutoBackgrounded")]
    pub assistant_auto_backgrounded: Option<bool>,
    #[serde(rename = "dangerouslyDisableSandbox")]
    pub dangerously_disable_sandbox: Option<bool>,
    #[serde(rename = "returnCodeInterpretation")]
    pub return_code_interpretation: Option<String>,
    #[serde(rename = "noOutputExpected")]
    pub no_output_expected: Option<bool>,
    #[serde(rename = "structuredContent")]
    pub structured_content: Option<Vec<serde_json::Value>>,
    #[serde(rename = "persistedOutputPath")]
    pub persisted_output_path: Option<String>,
    #[serde(rename = "persistedOutputSize")]
    pub persisted_output_size: Option<u64>,
    #[serde(rename = "sandboxStatus")]
    pub sandbox_status: Option<SandboxStatus>,
}

/// Executes a shell command with the requested sandbox settings.
pub fn execute_bash(input: BashCommandInput) -> io::Result<BashCommandOutput> {
    let cwd = input
        .cwd
        .clone()
        .or_else(|| env::current_dir().ok())
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NotFound,
                "could not resolve working directory",
            )
        })?;
    let sandbox_status = sandbox_status_for_input(&input, &cwd);

    if let Some(preflight) = try_preflight_bash_command(&input.command, &input) {
        return Ok(preflight);
    }

    if input.run_in_background.unwrap_or(false) {
        let mut child = prepare_command(&input.command, &cwd, &sandbox_status, false);
        child
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = child.spawn()?;

        if let Some(output) = verify_background_launch(&mut child)? {
            let stdout = truncate_output(&String::from_utf8_lossy(&output.stdout));
            let stderr = background_launch_failure_message(
                &String::from_utf8_lossy(&output.stderr),
                output.status.code(),
            );
            let no_output_expected = Some(stdout.trim().is_empty() && stderr.trim().is_empty());

            return Ok(BashCommandOutput {
                stdout,
                stderr,
                raw_output_path: None,
                interrupted: false,
                is_image: None,
                background_task_id: None,
                backgrounded_by_user: None,
                assistant_auto_backgrounded: None,
                dangerously_disable_sandbox: input.dangerously_disable_sandbox,
                return_code_interpretation: output
                    .status
                    .code()
                    .map(|code| format!("exit_code:{code}")),
                no_output_expected,
                structured_content: Some(vec![serde_json::json!({
                    "event": "background.launch_failed",
                    "gracePeriodMs": BACKGROUND_LAUNCH_GRACE_MS
                })]),
                persisted_output_path: None,
                persisted_output_size: None,
                sandbox_status: Some(sandbox_status),
            });
        }

        let pid = child.id();
        if let Ok(mut pids) = background_pids().lock() {
            pids.push(pid);
        }

        return Ok(BashCommandOutput {
            stdout: String::new(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: Some(pid.to_string()),
            backgrounded_by_user: Some(false),
            assistant_auto_backgrounded: Some(false),
            dangerously_disable_sandbox: input.dangerously_disable_sandbox,
            return_code_interpretation: None,
            no_output_expected: Some(true),
            structured_content: Some(vec![serde_json::json!({
                "event": "background.launch_verified",
                "gracePeriodMs": BACKGROUND_LAUNCH_GRACE_MS
            })]),
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: Some(sandbox_status),
        });
    }

    let runtime = Builder::new_current_thread().enable_all().build()?;
    runtime.block_on(execute_bash_async(input, sandbox_status, cwd))
}

async fn execute_bash_async(
    input: BashCommandInput,
    sandbox_status: SandboxStatus,
    cwd: std::path::PathBuf,
) -> io::Result<BashCommandOutput> {
    let mut command = prepare_tokio_command(&input.command, &cwd, &sandbox_status, true);
    let effective_timeout_ms = input.timeout.map(normalize_shell_timeout_ms);

    let output_result = if let Some(timeout_ms) = effective_timeout_ms {
        match timeout(Duration::from_millis(timeout_ms), command.output()).await {
            Ok(result) => (result?, false),
            Err(_) => {
                return Ok(BashCommandOutput {
                    stdout: String::new(),
                    stderr: format!("Command exceeded timeout of {timeout_ms} ms"),
                    raw_output_path: None,
                    interrupted: true,
                    is_image: None,
                    background_task_id: None,
                    backgrounded_by_user: None,
                    assistant_auto_backgrounded: None,
                    dangerously_disable_sandbox: input.dangerously_disable_sandbox,
                    return_code_interpretation: Some(String::from("timeout")),
                    no_output_expected: Some(true),
                    structured_content: None,
                    persisted_output_path: None,
                    persisted_output_size: None,
                    sandbox_status: Some(sandbox_status),
                });
            }
        }
    } else {
        (command.output().await?, false)
    };

    let (output, interrupted) = output_result;
    let stdout = truncate_output(&String::from_utf8_lossy(&output.stdout));
    let stderr = truncate_output(&String::from_utf8_lossy(&output.stderr));
    let no_output_expected = Some(stdout.trim().is_empty() && stderr.trim().is_empty());
    let return_code_interpretation = output.status.code().and_then(|code| {
        if code == 0 {
            None
        } else {
            Some(format!("exit_code:{code}"))
        }
    });

    Ok(BashCommandOutput {
        stdout,
        stderr,
        raw_output_path: None,
        interrupted,
        is_image: None,
        background_task_id: None,
        backgrounded_by_user: None,
        assistant_auto_backgrounded: None,
        dangerously_disable_sandbox: input.dangerously_disable_sandbox,
        return_code_interpretation,
        no_output_expected,
        structured_content: None,
        persisted_output_path: None,
        persisted_output_size: None,
        sandbox_status: Some(sandbox_status),
    })
}

/// Tokens that commonly fail in a Git Bash environment on Windows; checked
/// against the live shell before spawning so the caller gets a corrective
/// hint instead of a confusing late failure.
const PREFLIGHT_TOKENS: &[&str] = &[
    "pip",
    "pip3",
    "python",
    "python3",
    "head",
    "grep",
    "find",
    "sed",
    "awk",
    "powershell",
];

/// Commands that do not exist in Windows `PowerShell` 5.1 (no cmdlet, alias, or
/// stock executable). Checked without spawning a process so the hint is instant.
const POWERSHELL_MISSING_TOKENS: &[&str] = &[
    "grep", "sed", "awk", "head", "tail", "touch", "which", "wc", "ln", "chmod", "chown", "sudo",
    "apt", "apt-get", "yum", "dnf", "pacman", "xargs", "uniq", "cut", "tr", "man", "export",
    "source", "pkill", "killall",
];

fn try_preflight_bash_command(
    command: &str,
    input: &BashCommandInput,
) -> Option<BashCommandOutput> {
    let token = first_shell_command_token(command)?;
    let lower = token.to_ascii_lowercase();
    if !lower
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
    {
        return None;
    }
    let (shell_program, _) = detect_host_shell();
    let hint = if shell_program == "powershell" || shell_program == "pwsh" {
        preflight_for_powershell(command, &lower)?
    } else {
        preflight_for_bash(command, &lower)?
    };
    Some(BashCommandOutput {
        stdout: String::new(),
        stderr: hint,
        raw_output_path: None,
        interrupted: false,
        is_image: None,
        background_task_id: None,
        backgrounded_by_user: None,
        assistant_auto_backgrounded: None,
        dangerously_disable_sandbox: input.dangerously_disable_sandbox,
        return_code_interpretation: Some("exit_code:127".to_string()),
        no_output_expected: Some(false),
        structured_content: None,
        persisted_output_path: None,
        persisted_output_size: None,
        sandbox_status: None,
    })
}

fn preflight_for_bash(command: &str, lower: &str) -> Option<String> {
    if let Some(tag) = unterminated_heredoc_tag(command) {
        return Some(format!(
            "here-document is missing its terminator line `{tag}` — the command was not run \
             because it would write a truncated file. Use the write_file tool for file content \
             instead of `cat <<` heredocs; tool-call payloads are not size-limited by shell quoting."
        ));
    }
    if !PREFLIGHT_TOKENS.contains(&lower) {
        return None;
    }
    if bash_command_exists(lower) {
        return None;
    }
    Some(preflight_hint(lower))
}

/// Detect a heredoc (`<< TAG`, `<<-TAG`, `<< 'TAG'`) whose terminator line
/// never appears in the command. Models emitting large files through heredocs
/// routinely truncate mid-payload; bash then consumes the rest of the script
/// as document body and writes a corrupt partial file. Returns the missing
/// tag so the error can name it. `<<<` here-strings are ignored.
fn unterminated_heredoc_tag(command: &str) -> Option<String> {
    let bytes = command.as_bytes();
    let mut i = 0;
    while let Some(offset) = command[i..].find("<<") {
        let start = i + offset;
        let mut cursor = start + 2;
        // Skip `<<<` here-strings and `<<=`-style operators inside quotes.
        if bytes.get(cursor) == Some(&b'<') {
            i = cursor + 1;
            continue;
        }
        if bytes.get(cursor) == Some(&b'-') {
            cursor += 1;
        }
        while bytes.get(cursor) == Some(&b' ') {
            cursor += 1;
        }
        let quote = match bytes.get(cursor) {
            Some(&q @ (b'\'' | b'"')) => {
                cursor += 1;
                Some(q)
            }
            _ => None,
        };
        let tag_start = cursor;
        while let Some(&c) = bytes.get(cursor) {
            if c.is_ascii_alphanumeric() || c == b'_' {
                cursor += 1;
            } else {
                break;
            }
        }
        if cursor == tag_start {
            i = start + 2;
            continue;
        }
        if let Some(q) = quote {
            if bytes.get(cursor) != Some(&q) {
                i = start + 2;
                continue;
            }
        }
        let tag = &command[tag_start..cursor];
        let terminated = command[cursor..]
            .lines()
            .skip(1)
            .any(|line| line.trim_end() == tag);
        if !terminated {
            return Some(tag.to_string());
        }
        i = cursor;
    }
    None
}

/// `PowerShell` backend preflight: reject bash-only syntax and Linux-only
/// commands with a translation hint before anything is spawned, then verify
/// the first token resolves to a real cmdlet, alias, function, or executable.
fn preflight_for_powershell(command: &str, lower: &str) -> Option<String> {
    let bashisms = detect_bash_isms(command);
    if !bashisms.is_empty() {
        return Some(format!(
            "This command uses bash syntax that Windows PowerShell 5.1 cannot run. {}",
            bashisms.join(" ")
        ));
    }
    if POWERSHELL_MISSING_TOKENS.contains(&lower) {
        return Some(preflight_hint(lower));
    }
    if powershell_command_exists(lower) {
        return None;
    }
    Some(preflight_hint(lower))
}

/// Detect bash-only constructs that are parse errors or behave differently in
/// Windows `PowerShell` 5.1, returning one translation hint per construct.
fn detect_bash_isms(command: &str) -> Vec<&'static str> {
    let mut hints = Vec::new();
    if command.contains("&&") {
        hints.push("Replace `a && b` with `a; if ($?) { b }` (PowerShell 5.1 has no `&&`).");
    }
    if command.contains("||") {
        hints.push("Replace `a || b` with `a; if (-not $?) { b }` (PowerShell 5.1 has no `||`).");
    }
    if command.contains("/dev/null") {
        hints.push("Replace `/dev/null` with `$null` (e.g. `2>$null`).");
    }
    if command.contains("<<") {
        hints.push("Replace heredocs (`<<EOF`) with a PowerShell here-string: @'...'@.");
    }
    hints
}

fn bash_command_exists(cmd: &str) -> bool {
    // Probe through the resolved backend, never a bare `bash` lookup that
    // could hit the WSL launcher on PATH.
    let (program, _) = detect_host_shell();
    Command::new(program)
        .args(["-lc", &format!("command -v {cmd}")])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

/// True when `cmd` resolves to a cmdlet, alias, function, or executable in
/// Windows `PowerShell`. The token is validated to be alphanumeric/`-`/`_`/`.`
/// by the caller, so it cannot smuggle script into the probe.
fn powershell_command_exists(cmd: &str) -> bool {
    Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            &format!("if (Get-Command {cmd} -ErrorAction SilentlyContinue) {{ exit 0 }} exit 1"),
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

pub(crate) fn first_shell_command_token(command: &str) -> Option<String> {
    let mut s = command.trim();
    while let Some(rest) = strip_leading_env_assignment(s) {
        s = rest.trim_start();
    }
    let token = s.split_whitespace().next()?.to_string();
    (!token.is_empty()).then_some(token)
}

fn strip_leading_env_assignment(s: &str) -> Option<&str> {
    let trimmed = s.trim_start();
    let pos = trimmed.find('=')?;
    let name = trimmed[..pos].trim();
    if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
        return None;
    }
    let after_eq = trimmed[pos + 1..].trim_start();
    // Require a single-token value (`VAR=val cmd`) so values like `1` do not consume the command word.
    let value_end = after_eq.find(char::is_whitespace).filter(|&idx| idx > 0)?;
    Some(after_eq[value_end..].trim_start())
}

pub(crate) fn preflight_hint(token: &str) -> String {
    let suggestion = match token {
        "pip" | "pip3" => "Try: python -m pip install … (or use the PowerShell tool on Windows).",
        "python" | "python3" => {
            "Try: py -3 … or use the PowerShell tool with an explicit Python path."
        }
        "head" => "On Windows PowerShell use: Get-Content -Path FILE -TotalCount N",
        "tail" => "On Windows PowerShell use: Get-Content -Path FILE -Tail N",
        "grep" => "On Windows PowerShell use: Select-String -Path FILE -Pattern PAT",
        "find" => "On Windows PowerShell use: Get-ChildItem -Recurse",
        "touch" => "On Windows PowerShell use: New-Item -ItemType File -Path FILE",
        "which" => "On Windows PowerShell use: Get-Command NAME",
        "wc" => "On Windows PowerShell use: (Get-Content FILE | Measure-Object -Line).Lines",
        "ln" => "On Windows PowerShell use: New-Item -ItemType SymbolicLink -Path LINK -Target TARGET",
        "sed" => "On Windows PowerShell use the -replace operator: (Get-Content FILE) -replace 'PAT','NEW'",
        "awk" => "On Windows PowerShell use ForEach-Object with -split for field extraction.",
        "cut" => "On Windows PowerShell use ForEach-Object { ($_ -split 'DELIM')[N] }",
        "tr" | "uniq" | "xargs" => {
            "Linux-only text tool; use PowerShell pipeline cmdlets (ForEach-Object, Sort-Object -Unique) instead."
        }
        "chmod" | "chown" => "Not applicable on Windows; use icacls only if ACL changes are required.",
        "export" => "On Windows PowerShell set environment variables with: $env:NAME = 'value'",
        "source" => "On Windows PowerShell dot-source instead: . .\\script.ps1",
        "sudo" | "apt" | "apt-get" | "yum" | "dnf" | "pacman" => {
            "Linux package management is not available on Windows; use winget or download installers directly."
        }
        "pkill" | "killall" => "On Windows PowerShell use: Stop-Process -Name NAME -Force",
        "man" => "On Windows PowerShell use: Get-Help NAME",
        "powershell" => {
            "Use the dedicated PowerShell tool instead of invoking powershell from bash."
        }
        _ => "Use the PowerShell tool or fix PATH for this shell.",
    };
    format!("command '{token}' is not available in this Windows shell environment. {suggestion}")
}

fn sandbox_status_for_input(input: &BashCommandInput, cwd: &std::path::Path) -> SandboxStatus {
    let config = ConfigLoader::default_for(cwd).load().map_or_else(
        |_| SandboxConfig::default(),
        |runtime_config| runtime_config.sandbox().clone(),
    );
    let request = config.resolve_request(
        input.dangerously_disable_sandbox.map(|disabled| !disabled),
        input.namespace_restrictions,
        input.isolate_network,
        input.filesystem_mode,
        input.allowed_mounts.clone(),
    );
    resolve_sandbox_status_for_request(&request, cwd)
}

fn prepare_command(
    command: &str,
    cwd: &std::path::Path,
    sandbox_status: &SandboxStatus,
    create_dirs: bool,
) -> Command {
    if create_dirs {
        prepare_sandbox_dirs(cwd);
    }

    if let Some(launcher) = build_linux_sandbox_command(command, cwd, sandbox_status) {
        let mut prepared = Command::new(launcher.program);
        prepared.args(launcher.args);
        prepared.current_dir(cwd);
        prepared.envs(launcher.env);
        return prepared;
    }

    let (program, shell_args) = detect_host_shell();
    let mut prepared = Command::new(program);
    prepared.args(shell_args);
    prepared.arg(command).current_dir(cwd);
    if sandbox_status.filesystem_active {
        prepared.env("HOME", cwd.join(".sandbox-home"));
        prepared.env("TMPDIR", cwd.join(".sandbox-tmp"));
    }
    prepared
}

fn prepare_tokio_command(
    command: &str,
    cwd: &std::path::Path,
    sandbox_status: &SandboxStatus,
    create_dirs: bool,
) -> TokioCommand {
    if create_dirs {
        prepare_sandbox_dirs(cwd);
    }

    if let Some(launcher) = build_linux_sandbox_command(command, cwd, sandbox_status) {
        let mut prepared = TokioCommand::new(launcher.program);
        prepared.args(launcher.args);
        prepared.current_dir(cwd);
        prepared.envs(launcher.env);
        return prepared;
    }

    let (program, shell_args) = detect_host_shell();
    let mut prepared = TokioCommand::new(program);
    prepared.args(shell_args);
    prepared.arg(command).current_dir(cwd);
    prepared.kill_on_drop(true);
    if sandbox_status.filesystem_active {
        prepared.env("HOME", cwd.join(".sandbox-home"));
        prepared.env("TMPDIR", cwd.join(".sandbox-tmp"));
    }
    prepared
}

/// Resolve the shell backend used for the bash tool.
///
/// On Windows the order is: explicit `CLAW_SHELL` override (`bash`/`gitbash`
/// or `powershell`/`pwsh`), then Git Bash when installed, then Windows
/// `PowerShell`. WSL is never used: commands always run against the native
/// Windows filesystem so `D:\...` and `/d/...` paths mean the same files.
/// Git Bash is resolved by explicit path — `bash` on PATH is NOT trusted,
/// because `System32\bash.exe` and `WindowsApps\bash.exe` launch WSL.
fn detect_host_shell() -> (&'static str, &'static [&'static str]) {
    #[cfg(windows)]
    {
        const POWERSHELL: (&str, &[&str]) = (
            "powershell",
            &["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"],
        );
        const PWSH: (&str, &[&str]) = (
            "pwsh",
            &["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"],
        );
        let requested = env::var("CLAW_SHELL")
            .unwrap_or_default()
            .to_ascii_lowercase();
        match requested.as_str() {
            "bash" | "gitbash" | "git-bash" => {
                if let Some(bash) = git_bash_program() {
                    return (bash, &["-lc"]);
                }
            }
            "pwsh" if command_exists("pwsh") => return PWSH,
            "powershell" | "pwsh" => return POWERSHELL,
            _ => {}
        }
        if let Some(bash) = git_bash_program() {
            return (bash, &["-lc"]);
        }
        POWERSHELL
    }

    #[cfg(not(windows))]
    {
        ("sh", &["-lc"])
    }
}

/// Label and program of the active shell backend, for prompts and doctor
/// output. Labels: `git-bash`, `powershell`, or `sh`.
#[must_use]
pub fn active_shell_backend() -> (&'static str, &'static str) {
    let (program, _) = detect_host_shell();
    let label = if program == "powershell" || program == "pwsh" {
        "powershell"
    } else if program == "sh" {
        "sh"
    } else {
        "git-bash"
    };
    (label, program)
}

#[cfg(windows)]
static GIT_BASH_PROGRAM: OnceLock<Option<&'static str>> = OnceLock::new();

/// Resolved Git Bash executable path, cached for the process lifetime.
#[cfg(windows)]
fn git_bash_program() -> Option<&'static str> {
    *GIT_BASH_PROGRAM.get_or_init(|| find_git_bash().map(|p| &*Box::leak(p.into_boxed_str())))
}

/// Locate Git for Windows bash explicitly. PATH hits under `System32` or
/// `WindowsApps` are WSL launchers (`uname` reports Linux, `/mnt/<drive>`
/// paths) and are rejected; Git Bash is a native Windows MSYS shell.
#[cfg(windows)]
fn find_git_bash() -> Option<String> {
    if let Ok(output) = Command::new("where").arg("bash").output() {
        if output.status.success() {
            for line in String::from_utf8_lossy(&output.stdout).lines() {
                let candidate = line.trim();
                let lower = candidate.to_ascii_lowercase();
                if candidate.is_empty()
                    || lower.contains("\\windowsapps\\")
                    || lower.contains("\\system32\\")
                {
                    continue;
                }
                return Some(candidate.to_string());
            }
        }
    }

    let mut candidates: Vec<PathBuf> = Vec::new();
    for var in ["ProgramFiles", "ProgramFiles(x86)"] {
        if let Some(root) = env::var_os(var) {
            candidates.push(PathBuf::from(root).join("Git").join("bin").join("bash.exe"));
        }
    }
    if let Some(local) = env::var_os("LOCALAPPDATA") {
        candidates.push(
            PathBuf::from(local)
                .join("Programs")
                .join("Git")
                .join("bin")
                .join("bash.exe"),
        );
    }
    // Derive from git.exe: Git for Windows puts Git\cmd on PATH, so
    // Git\cmd\git.exe implies Git\bin\bash.exe one level up.
    if let Ok(output) = Command::new("where").arg("git").output() {
        if output.status.success() {
            for line in String::from_utf8_lossy(&output.stdout).lines() {
                let git_path = PathBuf::from(line.trim());
                if let Some(install_root) = git_path.parent().and_then(std::path::Path::parent) {
                    candidates.push(install_root.join("bin").join("bash.exe"));
                }
            }
        }
    }
    candidates
        .into_iter()
        .find(|path| path.is_file())
        .map(|path| path.display().to_string())
}

fn command_exists(command: &str) -> bool {
    #[cfg(windows)]
    {
        Command::new("where")
            .arg(command)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
    }

    #[cfg(not(windows))]
    {
        Command::new("sh")
            .arg("-lc")
            .arg(format!("command -v {command} >/dev/null 2>&1"))
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
    }
}

fn normalize_shell_timeout_ms(timeout_ms: u64) -> u64 {
    timeout_ms.max(MIN_SHELL_TIMEOUT_MS)
}

fn verify_background_launch(
    child: &mut std::process::Child,
) -> io::Result<Option<std::process::Output>> {
    let deadline = Instant::now() + Duration::from_millis(BACKGROUND_LAUNCH_GRACE_MS);
    loop {
        if child.try_wait()?.is_some() {
            let mut stdout = Vec::new();
            if let Some(mut pipe) = child.stdout.take() {
                let _ = pipe.read_to_end(&mut stdout);
            }
            let mut stderr = Vec::new();
            if let Some(mut pipe) = child.stderr.take() {
                let _ = pipe.read_to_end(&mut stderr);
            }
            let status = child.wait()?;
            return Ok(Some(std::process::Output {
                status,
                stdout,
                stderr,
            }));
        }
        if Instant::now() >= deadline {
            return Ok(None);
        }
        std::thread::sleep(Duration::from_millis(BACKGROUND_LAUNCH_POLL_MS));
    }
}

fn background_launch_failure_message(stderr: &str, exit_code: Option<i32>) -> String {
    let summary = match exit_code {
        Some(code) => format!(
            "Background command exited before launch verification completed (exit code {code})."
        ),
        None => String::from("Background command exited before launch verification completed."),
    };
    if stderr.trim().is_empty() {
        summary
    } else {
        format!("{summary}\n{}", stderr.trim_end())
    }
}

fn prepare_sandbox_dirs(cwd: &std::path::Path) {
    let _ = std::fs::create_dir_all(cwd.join(".sandbox-home"));
    let _ = std::fs::create_dir_all(cwd.join(".sandbox-tmp"));
}

#[cfg(test)]
mod shell_backend_tests {
    use super::{detect_bash_isms, detect_host_shell, preflight_hint, POWERSHELL_MISSING_TOKENS};

    #[test]
    fn backend_is_never_wsl_or_bare_sh_on_windows() {
        let (program, _) = detect_host_shell();
        assert_ne!(program, "wsl");
        #[cfg(windows)]
        {
            assert_ne!(program, "sh");
            // A bare `bash` would resolve through PATH, where System32 and
            // WindowsApps bash.exe launch WSL. Only explicit paths or
            // PowerShell are acceptable.
            assert_ne!(program, "bash");
            let lower = program.to_ascii_lowercase();
            assert!(
                !lower.contains("\\windowsapps\\") && !lower.contains("\\system32\\"),
                "backend resolved to a WSL launcher: {program}"
            );
        }
    }

    #[test]
    fn detects_and_chain_bashism() {
        let hints = detect_bash_isms("cargo build && cargo test");
        assert_eq!(hints.len(), 1);
        assert!(hints[0].contains("if ($?)"));
    }

    #[test]
    fn detects_dev_null_bashism() {
        let hints = detect_bash_isms("where git 2>/dev/null");
        assert_eq!(hints.len(), 1);
        assert!(hints[0].contains("$null"));
    }

    #[test]
    fn plain_command_has_no_bashisms() {
        assert!(detect_bash_isms("git status").is_empty());
    }

    #[test]
    fn every_powershell_missing_token_has_specific_hint() {
        for token in POWERSHELL_MISSING_TOKENS {
            let hint = preflight_hint(token);
            assert!(
                !hint.contains("fix PATH"),
                "token '{token}' fell through to the generic hint"
            );
        }
    }

    #[test]
    fn unterminated_heredoc_is_detected() {
        use super::unterminated_heredoc_tag;
        // Truncated payload: terminator never arrives (the qwen failure mode).
        let cmd = "cat > x.html << 'HTMLEOF'\n<!DOCTYPE html>\n<html>";
        assert_eq!(unterminated_heredoc_tag(cmd).as_deref(), Some("HTMLEOF"));

        // Properly terminated heredoc passes.
        let ok = "cat > x.txt << 'EOF'\nhello\nEOF\n";
        assert_eq!(unterminated_heredoc_tag(ok), None);

        // Unquoted and <<- forms.
        let ok2 = "cat <<-EOT\nbody\nEOT";
        assert_eq!(unterminated_heredoc_tag(ok2), None);
        let bad2 = "cat <<EOT\nbody only";
        assert_eq!(unterminated_heredoc_tag(bad2).as_deref(), Some("EOT"));

        // Here-strings and plain commands are not flagged.
        assert_eq!(unterminated_heredoc_tag("grep x <<< \"input\""), None);
        assert_eq!(unterminated_heredoc_tag("git log --oneline"), None);
    }

    #[test]
    fn linux_only_hints_translate_to_powershell() {
        assert!(preflight_hint("touch").contains("New-Item"));
        assert!(preflight_hint("which").contains("Get-Command"));
        assert!(preflight_hint("tail").contains("-Tail"));
        assert!(preflight_hint("export").contains("$env:"));
        assert!(preflight_hint("sudo").contains("winget"));
    }
}

#[cfg(test)]
mod tests {
    use super::{execute_bash, first_shell_command_token, preflight_hint, BashCommandInput};
    use crate::sandbox::FilesystemIsolationMode;

    #[test]
    #[cfg_attr(windows, ignore = "requires POSIX-compatible shell")]
    fn executes_simple_command() {
        let output = execute_bash(BashCommandInput {
            command: String::from("printf 'hello'"),
            timeout: Some(1_000),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(false),
            namespace_restrictions: Some(false),
            isolate_network: Some(false),
            filesystem_mode: Some(FilesystemIsolationMode::WorkspaceOnly),
            allowed_mounts: None,
            cwd: None,
        })
        .expect("bash command should execute");

        assert_eq!(output.stdout, "hello");
        assert!(!output.interrupted);
        assert!(output.sandbox_status.is_some());
    }

    #[test]
    fn disables_sandbox_when_requested() {
        let output = execute_bash(BashCommandInput {
            command: String::from("printf 'hello'"),
            timeout: Some(1_000),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
            cwd: None,
        })
        .expect("bash command should execute");

        assert!(!output.sandbox_status.expect("sandbox status").enabled);
    }

    #[test]
    #[cfg_attr(windows, ignore = "requires POSIX-compatible sleep semantics")]
    fn clamps_tiny_timeout_to_sane_minimum() {
        let output = execute_bash(BashCommandInput {
            command: String::from("sleep 1"),
            timeout: Some(10),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
            cwd: None,
        })
        .expect("bash command should execute");

        assert!(!output.interrupted, "timeout should be clamped above 10 ms");
    }

    #[test]
    fn first_shell_command_token_strips_env_prefix() {
        assert_eq!(
            first_shell_command_token("FOO=1 pip install x").as_deref(),
            Some("pip")
        );
    }

    #[test]
    fn preflight_hint_for_pip_mentions_python_m_pip() {
        let h = preflight_hint("pip");
        assert!(h.contains("pip"));
        assert!(h.contains("python -m pip"));
    }

    #[test]
    fn preflight_hint_for_head_mentions_get_content() {
        assert!(preflight_hint("head").contains("Get-Content"));
    }

    #[test]
    #[cfg_attr(windows, ignore = "requires POSIX-compatible shell")]
    fn background_command_that_exits_immediately_reports_failure() {
        let output = execute_bash(BashCommandInput {
            command: String::from("exit 9"),
            timeout: Some(1_000),
            description: None,
            run_in_background: Some(true),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
            cwd: None,
        })
        .expect("background command should return structured output");

        assert!(output.background_task_id.is_none());
        assert_eq!(
            output.return_code_interpretation.as_deref(),
            Some("exit_code:9")
        );
        assert!(output
            .stderr
            .contains("Background command exited before launch verification completed"));
    }
}

/// Maximum output bytes before truncation (16 KiB, matching upstream).
const MAX_OUTPUT_BYTES: usize = 16_384;

/// Truncate output to `MAX_OUTPUT_BYTES`, appending a marker when trimmed.
fn truncate_output(s: &str) -> String {
    if s.len() <= MAX_OUTPUT_BYTES {
        return s.to_string();
    }
    // Find the last valid UTF-8 boundary at or before MAX_OUTPUT_BYTES
    let mut end = MAX_OUTPUT_BYTES;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    let mut truncated = s[..end].to_string();
    truncated.push_str("\n\n[output truncated — exceeded 16384 bytes]");
    truncated
}

#[cfg(test)]
mod truncation_tests {
    use super::*;

    #[test]
    fn short_output_unchanged() {
        let s = "hello world";
        assert_eq!(truncate_output(s), s);
    }

    #[test]
    fn long_output_truncated() {
        let s = "x".repeat(20_000);
        let result = truncate_output(&s);
        assert!(result.len() < 20_000);
        assert!(result.ends_with("[output truncated — exceeded 16384 bytes]"));
    }

    #[test]
    fn exact_boundary_unchanged() {
        let s = "a".repeat(MAX_OUTPUT_BYTES);
        assert_eq!(truncate_output(&s), s);
    }

    #[test]
    fn one_over_boundary_truncated() {
        let s = "a".repeat(MAX_OUTPUT_BYTES + 1);
        let result = truncate_output(&s);
        assert!(result.contains("[output truncated"));
    }
}
