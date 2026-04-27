use std::borrow::Cow;
use std::env;
use std::io;
use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use regex::Regex;
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

/// When the host runs commands via `wsl bash -lc`, MSYS-style `/d/...` paths refer to a
/// Linux path under the WSL rootfs, not the Windows `D:\` drive. Rewrite to `/mnt/d/...`.
/// Git Bash (`bash` on PATH) already understands `/d/...`, so leave commands unchanged there.
fn rewrite_command_for_shell<'a>(command: &'a str, shell_program: &str) -> Cow<'a, str> {
    #[cfg(not(windows))]
    {
        let _ = shell_program;
        return Cow::Borrowed(command);
    }
    #[cfg(windows)]
    {
        if shell_program != "wsl" {
            return Cow::Borrowed(command);
        }
        static RE: OnceLock<Regex> = OnceLock::new();
        // Do not use ':' as a boundary — it would rewrite `http://d/foo` incorrectly.
        let re = RE.get_or_init(|| {
            Regex::new(r#"(?P<b>^|[\s;='"`\(\[])/(?P<l>[a-zA-Z])/"#).expect("valid regex")
        });
        let mut out = String::new();
        let mut last = 0usize;
        let mut replaced = false;
        for caps in re.captures_iter(command) {
            let m = caps.get(0).expect("regex match");
            out.push_str(&command[last..m.start()]);
            let b = caps.name("b").expect("b").as_str();
            let l = caps.name("l").expect("l").as_str();
            out.push_str(b);
            out.push_str("/mnt/");
            out.push_str(l);
            out.push('/');
            last = m.end();
            replaced = true;
        }
        if !replaced {
            return Cow::Borrowed(command);
        }
        out.push_str(&command[last..]);
        Cow::Owned(out)
    }
}

fn try_preflight_bash_command(
    command: &str,
    input: &BashCommandInput,
) -> Option<BashCommandOutput> {
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
    let token = first_shell_command_token(command)?;
    let lower = token.to_ascii_lowercase();
    if !PREFLIGHT_TOKENS.iter().any(|t| *t == lower.as_str()) {
        return None;
    }
    if !lower
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return None;
    }
    if bash_command_exists(&lower) {
        return None;
    }
    Some(BashCommandOutput {
        stdout: String::new(),
        stderr: preflight_hint(&lower),
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

fn bash_command_exists(cmd: &str) -> bool {
    Command::new("bash")
        .args(["-lc", &format!("command -v {cmd}")])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
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
        "grep" => "On Windows PowerShell use: Select-String -Path FILE -Pattern PAT",
        "find" => "On Windows PowerShell use: Get-ChildItem -Recurse",
        "powershell" => {
            "Use the dedicated PowerShell tool instead of invoking powershell from bash."
        }
        _ => "Use the PowerShell tool or fix PATH for this shell.",
    };
    format!("command '{token}' was not found in this bash environment. {suggestion}")
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
    let command = rewrite_command_for_shell(command, program);
    let mut prepared = Command::new(program);
    prepared.args(shell_args);
    prepared.arg(command.as_ref()).current_dir(cwd);
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
    let command = rewrite_command_for_shell(command, program);
    let mut prepared = TokioCommand::new(program);
    prepared.args(shell_args);
    prepared.arg(command.as_ref()).current_dir(cwd);
    prepared.kill_on_drop(true);
    if sandbox_status.filesystem_active {
        prepared.env("HOME", cwd.join(".sandbox-home"));
        prepared.env("TMPDIR", cwd.join(".sandbox-tmp"));
    }
    prepared
}

fn detect_host_shell() -> (&'static str, &'static [&'static str]) {
    #[cfg(windows)]
    {
        if command_exists("bash") {
            return ("bash", &["-lc"]);
        }
        if command_exists("wsl") {
            return ("wsl", &["bash", "-lc"]);
        }
    }

    ("sh", &["-lc"])
}

fn command_exists(command: &str) -> bool {
    #[cfg(windows)]
    {
        return Command::new("where")
            .arg(command)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
    }

    #[cfg(not(windows))]
    {
        Command::new("sh")
            .arg("-lc")
            .arg(format!("command -v {command} >/dev/null 2>&1"))
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
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
mod shell_rewrite_tests {
    use super::rewrite_command_for_shell;

    #[test]
    fn bash_backend_leaves_msys_paths_unchanged() {
        let out = rewrite_command_for_shell("cat > /d/ClawCodex/x.txt", "bash");
        assert_eq!(out.as_ref(), "cat > /d/ClawCodex/x.txt");
    }

    #[test]
    fn sh_backend_leaves_paths_unchanged() {
        let out = rewrite_command_for_shell("cat > /d/ClawCodex/x.txt", "sh");
        assert_eq!(out.as_ref(), "cat > /d/ClawCodex/x.txt");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_rewrites_msys_drive_paths() {
        let out = rewrite_command_for_shell("cat > /d/ClawCodex/x.txt", "wsl");
        assert_eq!(out.as_ref(), "cat > /mnt/d/ClawCodex/x.txt");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_rewrites_leading_msys_path() {
        let out = rewrite_command_for_shell("/d/ClawCodex/x.txt", "wsl");
        assert_eq!(out.as_ref(), "/mnt/d/ClawCodex/x.txt");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_rewrites_after_whitespace() {
        let out = rewrite_command_for_shell("ls -la /d/ClawCodex", "wsl");
        assert_eq!(out.as_ref(), "ls -la /mnt/d/ClawCodex");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_does_not_rewrite_http_urls() {
        let out = rewrite_command_for_shell("curl -s http://d/example", "wsl");
        assert_eq!(out.as_ref(), "curl -s http://d/example");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_does_not_rewrite_sed_slash_commands() {
        let out = rewrite_command_for_shell("sed 's/d/x/g'", "wsl");
        assert_eq!(out.as_ref(), "sed 's/d/x/g'");
    }

    #[cfg(windows)]
    #[test]
    fn wsl_does_not_rewrite_dot_slash_paths() {
        let out = rewrite_command_for_shell("cat ./d/readme.txt", "wsl");
        assert_eq!(out.as_ref(), "cat ./d/readme.txt");
    }
}

#[cfg(test)]
mod tests {
    use super::{execute_bash, first_shell_command_token, preflight_hint, BashCommandInput};
    use crate::sandbox::FilesystemIsolationMode;

    #[test]
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
