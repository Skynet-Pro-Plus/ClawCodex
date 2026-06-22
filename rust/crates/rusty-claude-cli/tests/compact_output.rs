use std::fs;
use std::io::Read as _;
use std::path::PathBuf;
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use mock_anthropic_service::{MockAnthropicService, SCENARIO_PREFIX};

static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Upper bound on a single `claw` invocation. A healthy compact run finishes in
/// well under a second; this only fires when the child wedges (e.g. a failed
/// mock connection), so it converts a hang into a clean failure instead of an
/// orphaned process that stalls the whole `cargo test --workspace` run.
const CLAW_TIMEOUT: Duration = Duration::from_secs(60);
/// Grace period to drain the child's pipes once it has exited.
const DRAIN_GRACE: Duration = Duration::from_secs(5);

#[test]
fn compact_flag_prints_only_final_assistant_text_without_tool_call_details() {
    // given a workspace pointed at the mock Anthropic service and a fixture file
    // that the read_file_roundtrip scenario will fetch through a tool call
    let runtime = tokio::runtime::Runtime::new().expect("tokio runtime should build");
    let server = runtime
        .block_on(MockAnthropicService::spawn())
        .expect("mock service should start");
    let base_url = server.base_url();

    let workspace = unique_temp_dir("compact-read-file");
    let config_home = workspace.join("config-home");
    let home = workspace.join("home");
    fs::create_dir_all(&workspace).expect("workspace should exist");
    fs::create_dir_all(&config_home).expect("config home should exist");
    fs::create_dir_all(&home).expect("home should exist");
    fs::write(workspace.join("fixture.txt"), "alpha parity line\n").expect("fixture should write");

    // when we run claw in compact text mode against a tool-using scenario
    let prompt = format!("{SCENARIO_PREFIX}read_file_roundtrip");
    let output = run_claw(
        &workspace,
        &config_home,
        &home,
        &base_url,
        &[
            "--model",
            "sonnet",
            "--permission-mode",
            "read-only",
            "--allowedTools",
            "read_file",
            "--compact",
            &prompt,
        ],
    );

    // then the command exits successfully and stdout contains exactly the final
    // assistant text with no tool call IDs, JSON envelopes, or spinner output
    assert!(
        output.status.success(),
        "compact run should succeed\nstdout:\n{}\n\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr),
    );
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf8");
    let trimmed = stdout.trim_end_matches('\n');
    assert_eq!(
        trimmed, "read_file roundtrip complete: alpha parity line",
        "compact stdout should contain only the final assistant text"
    );
    assert!(
        !stdout.contains("toolu_"),
        "compact stdout must not leak tool_use_id ({stdout:?})"
    );
    assert!(
        !stdout.contains("\"tool_uses\""),
        "compact stdout must not leak json envelopes ({stdout:?})"
    );
    assert!(
        !stdout.contains("Thinking"),
        "compact stdout must not include the spinner banner ({stdout:?})"
    );

    fs::remove_dir_all(&workspace).expect("workspace cleanup should succeed");
}

#[test]
fn compact_flag_streaming_text_only_emits_final_message_text() {
    // given a workspace pointed at the mock Anthropic service running the
    // streaming_text scenario which only emits a single assistant text block
    let runtime = tokio::runtime::Runtime::new().expect("tokio runtime should build");
    let server = runtime
        .block_on(MockAnthropicService::spawn())
        .expect("mock service should start");
    let base_url = server.base_url();

    let workspace = unique_temp_dir("compact-streaming-text");
    let config_home = workspace.join("config-home");
    let home = workspace.join("home");
    fs::create_dir_all(&workspace).expect("workspace should exist");
    fs::create_dir_all(&config_home).expect("config home should exist");
    fs::create_dir_all(&home).expect("home should exist");

    // when we invoke claw with --compact for the streaming text scenario
    let prompt = format!("{SCENARIO_PREFIX}streaming_text");
    let output = run_claw(
        &workspace,
        &config_home,
        &home,
        &base_url,
        &[
            "--model",
            "sonnet",
            "--permission-mode",
            "read-only",
            "--compact",
            &prompt,
        ],
    );

    // then stdout should be exactly the assistant text followed by a newline
    assert!(
        output.status.success(),
        "compact streaming run should succeed\nstdout:\n{}\n\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr),
    );
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf8");
    assert_eq!(
        stdout, "Mock streaming says hello from the parity harness.\n",
        "compact streaming stdout should contain only the final assistant text"
    );

    fs::remove_dir_all(&workspace).expect("workspace cleanup should succeed");
}

fn run_claw(
    cwd: &std::path::Path,
    config_home: &std::path::Path,
    home: &std::path::Path,
    base_url: &str,
    args: &[&str],
) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_claw"));
    command
        .current_dir(cwd)
        .env_clear()
        .env("ANTHROPIC_API_KEY", "test-compact-key")
        .env("ANTHROPIC_BASE_URL", base_url)
        .env("CLAW_CONFIG_HOME", config_home)
        .env("HOME", home)
        .env("NO_COLOR", "1")
        .env("PATH", inherited_path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    forward_windows_runtime_env(&mut command);
    command.args(args);
    run_with_timeout(command, CLAW_TIMEOUT)
}

/// On Windows the child needs a usable `PATH` to resolve `git`/`sh.exe`; a
/// hard-coded Unix `PATH` leaves it unable to find those tools. Inherit the
/// harness `PATH` instead, falling back to the POSIX default elsewhere.
fn inherited_path() -> String {
    std::env::var("PATH").unwrap_or_else(|_| "/usr/bin:/bin".to_string())
}

/// Forward the Windows variables that core runtime initialisation depends on.
///
/// `.env_clear()` strips `SystemRoot`/`SystemDrive`, but Windows needs
/// `SystemRoot` to locate system DLLs; without it the child aborts during
/// crypto/socket initialisation (`getrandom` -> `abort`,
/// `STATUS_ILLEGAL_INSTRUCTION`) before it can emit a single byte. Outside
/// Windows these variables are absent and this is a no-op.
fn forward_windows_runtime_env(command: &mut Command) {
    for name in ["SystemRoot", "SystemDrive"] {
        if let Ok(value) = std::env::var(name) {
            command.env(name, value);
        }
    }
}

/// Spawn `command`, draining stdout/stderr on background threads and waiting at
/// most `timeout` for exit. On timeout the whole child process tree is killed
/// so a wedged `claw` (or a grandchild holding the stdout pipe) can never be
/// orphaned or stall the test binary.
fn run_with_timeout(mut command: Command, timeout: Duration) -> Output {
    let child = command.spawn().expect("claw should launch");
    let mut guard = KillOnDrop(child);

    let mut stdout_pipe = guard.0.stdout.take().expect("stdout pipe");
    let mut stderr_pipe = guard.0.stderr.take().expect("stderr pipe");
    let (stdout_tx, stdout_rx) = mpsc::channel();
    let (stderr_tx, stderr_rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = stdout_pipe.read_to_end(&mut buffer);
        let _ = stdout_tx.send(buffer);
    });
    std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = stderr_pipe.read_to_end(&mut buffer);
        let _ = stderr_tx.send(buffer);
    });

    let deadline = Instant::now() + timeout;
    let status = loop {
        if let Some(status) = guard.0.try_wait().expect("failed polling claw process") {
            break status;
        }
        if Instant::now() >= deadline {
            let pid = guard.0.id();
            kill_process_tree(pid);
            drop(guard);
            panic!(
                "claw did not exit within {timeout:?}; killed process tree (pid {pid}) \
                 to avoid orphaning it.\nstdout so far:\n{}\nstderr so far:\n{}",
                String::from_utf8_lossy(&drain(&stdout_rx)),
                String::from_utf8_lossy(&drain(&stderr_rx)),
            );
        }
        std::thread::sleep(Duration::from_millis(20));
    };

    // The child has exited; its pipe write ends should close promptly. Bound the
    // drain so a lingering grandchild handle cannot reintroduce a hang.
    let stdout = stdout_rx.recv_timeout(DRAIN_GRACE).unwrap_or_default();
    let stderr = stderr_rx.recv_timeout(DRAIN_GRACE).unwrap_or_default();
    Output {
        status,
        stdout,
        stderr,
    }
}

fn drain(receiver: &mpsc::Receiver<Vec<u8>>) -> Vec<u8> {
    receiver
        .recv_timeout(Duration::from_secs(1))
        .unwrap_or_default()
}

/// Best-effort kill of a process and all of its descendants. `Child::kill`
/// alone does not reap grandchildren on Windows.
fn kill_process_tree(pid: u32) {
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("pkill")
            .args(["-9", "-P", &pid.to_string()])
            .status();
    }
}

struct KillOnDrop(std::process::Child);

impl Drop for KillOnDrop {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn unique_temp_dir(label: &str) -> PathBuf {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock should be after epoch")
        .as_millis();
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!(
        "claw-compact-{label}-{}-{millis}-{counter}",
        std::process::id()
    ))
}
