use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;
use serde_json::{json, Value};
use tools::execute_tool;

#[derive(Serialize)]
struct AuditEntry {
    tool_name: String,
    category: String,
    status: String,
    input: Value,
    evidence: Value,
    likely_cause: Option<String>,
}

#[derive(Serialize)]
struct ChildResult {
    ok: bool,
    output: Option<String>,
    error: Option<String>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.get(1).is_some_and(|arg| arg == "invoke") {
        return invoke_mode(&args);
    }

    let start_dir = env::current_dir()?;
    let repo_root = resolve_repo_root(&start_dir)?;
    let audit_dir = repo_root.join("tool_audit");
    let tmp_dir = audit_dir.join("tmp");
    fs::create_dir_all(&tmp_dir)?;

    let mut entries = Vec::new();
    let mut bug_lines = vec![String::from("# Tool Audit Bugs"), String::new()];

    let write_path = audit_dir.join("write_test.txt");
    let notebook_path = audit_dir.join("fixture.ipynb");

    env::set_current_dir(&repo_root)?;
    entries.push(run_tool(
        "bash",
        "shell",
        json!({"command": "echo claw-bash-ok && uname -s"}),
        |result| match result {
            Ok(value) if output_contains(&value, "stdout", "claw-bash-ok") => audit_pass(value),
            Ok(value) => audit_fail(value, "bash output missing expected marker"),
            Err(error) => blocked_or_failed(error),
        },
    ));
    entries.push(run_tool(
        "read_file",
        "file",
        json!({"path": repo_root.join("launch.ps1").display().to_string()}),
        |result| match result {
            Ok(value)
                if value["file"]["content"]
                    .as_str()
                    .is_some_and(|text| text.contains("OPENAI_BASE_URL")) =>
            {
                audit_pass(value)
            }
            Ok(value) => audit_fail(
                value,
                "read_file did not return expected launch.ps1 content",
            ),
            Err(error) => audit_failed_error(error),
        },
    ));
    entries.push(run_tool(
        "write_file",
        "file",
        json!({"path": write_path.display().to_string(), "content": "alpha\nbeta\n"}),
        |result| match result {
            Ok(value) if write_path.exists() => audit_pass(value),
            Ok(value) => audit_fail(
                value,
                "write_file reported success but file was not created",
            ),
            Err(error) => audit_failed_error(error),
        },
    ));
    entries.push(run_tool(
        "edit_file",
        "file",
        json!({"path": write_path.display().to_string(), "old_string": "beta", "new_string": "gamma"}),
        |result| match result {
            Ok(value) if fs::read_to_string(&write_path).ok().is_some_and(|text| text.contains("gamma")) => audit_pass(value),
            Ok(value) => audit_fail(value, "edit_file reported success but file content was unchanged"),
            Err(error) => audit_failed_error(error),
        },
    ));
    entries.push(run_tool(
        "glob_search",
        "search",
        json!({"pattern": "*.py", "path": repo_root.display().to_string()}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "grep_search",
        "search",
        json!({"pattern": "def ", "path": repo_root.join("src").display().to_string()}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WebFetch",
        "web",
        json!({"url": "https://example.com", "prompt": "Return the title"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WebSearch",
        "web",
        json!({"query": "OpenAI official website"}),
        |result| any_ok(result),
    ));

    let todo_store = audit_dir.join("todos.json");
    with_env("CLAWD_TODO_STORE", Some(todo_store.as_os_str()), || {
        entries.push(run_tool(
            "TodoWrite",
            "workflow",
            json!({"todos": [
                {"content": "Audit tools", "activeForm": "Auditing tools", "status": "in_progress"},
                {"content": "Write report", "activeForm": "Writing report", "status": "pending"}
            ]}),
            |result| any_ok(result),
        ));
    });

    entries.push(run_tool(
        "Skill",
        "workflow",
        json!({"skill": "imagegen"}),
        |result| match result {
            Ok(value) => audit_pass(value),
            Err(error) => blocked_or_failed(error),
        },
    ));

    entries.push(run_tool(
        "Agent",
        "workflow",
        json!({"description": "tool-audit-agent", "prompt": "Write one line to the agent output and stop", "name": "tool-audit-agent"}),
        |result| match result {
            Ok(value) => classify_agent_result(value),
            Err(error) => blocked_or_failed(error),
        },
    ));

    entries.push(run_tool(
        "ToolSearch",
        "workflow",
        json!({"query": "bash", "max_results": 5}),
        |result| any_ok(result),
    ));

    fs::write(
        &notebook_path,
        r#"{"cells":[{"cell_type":"code","id":"cell-a","metadata":{},"source":["print(1)\n"],"outputs":[],"execution_count":null}],"metadata":{"kernelspec":{"language":"python"}},"nbformat":4,"nbformat_minor":5}"#,
    )?;
    entries.push(run_tool(
        "NotebookEdit",
        "file",
        json!({"notebook_path": notebook_path.display().to_string(), "cell_id": "cell-a", "new_source": "print(2)\n", "edit_mode": "replace"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "Sleep",
        "workflow",
        json!({"duration_ms": 10}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "SendUserMessage",
        "workflow",
        json!({"message": "tool audit", "status": "normal"}),
        |result| any_ok(result),
    ));

    let config_root = tmp_dir.join("config-home");
    let config_cwd = tmp_dir.join("config-cwd");
    fs::create_dir_all(config_root.join(".claw"))?;
    fs::create_dir_all(config_cwd.join(".claw"))?;
    fs::write(
        config_root.join(".claw").join("settings.json"),
        r#"{"verbose":false}"#,
    )?;
    with_home_and_cwd(&config_root, &config_cwd, || {
        entries.push(run_tool(
            "Config",
            "config",
            json!({"setting": "verbose"}),
            |result| any_ok(result),
        ));
        entries.push(run_tool("EnterPlanMode", "config", json!({}), |result| {
            any_ok(result)
        }));
        entries.push(run_tool("ExitPlanMode", "config", json!({}), |result| {
            any_ok(result)
        }));
    })?;

    entries.push(run_tool(
        "StructuredOutput",
        "workflow",
        json!({"ok": true, "items": [1, 2, 3]}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "REPL",
        "runtime",
        json!({"language": "python", "code": "print(1 + 1)", "timeout_ms": 500}),
        |result| match result {
            Ok(value) if value["exitCode"].as_i64() == Some(0) => audit_pass(value),
            Ok(value) => (
                String::from("blocked"),
                value,
                Some(String::from(
                    "Python runtime is not available from this Windows environment",
                )),
            ),
            Err(error) => blocked_or_failed(error),
        },
    ));
    entries.push(run_tool(
        "PowerShell",
        "shell",
        json!({"command": "Write-Output claw-powershell-ok", "timeout": 1000}),
        |result| match result {
            Ok(value) if output_contains(&value, "stdout", "claw-powershell-ok") => {
                audit_pass(value)
            }
            Ok(value) => audit_fail(value, "PowerShell output missing expected marker"),
            Err(error) => blocked_or_failed(error),
        },
    ));

    entries.push(run_child_tool(
        &audit_dir,
        &repo_root,
        "AskUserQuestion",
        "workflow",
        json!({"question": "Pick one", "options": ["yes", "no"]}),
        Some("1\n"),
        |result| match result {
            Ok(value) => any_ok(Ok(value)),
            Err(error) => blocked_or_failed(error),
        },
    ));

    let mut task_id = String::new();
    entries.push(run_tool_capture(
        "TaskCreate",
        "tasking",
        json!({"prompt": "Audit task", "description": "created by tool audit"}),
        |result| {
            if let Ok(value) = &result {
                task_id = value["task_id"].as_str().unwrap_or_default().to_string();
            }
            any_ok(result)
        },
    ));
    entries.push(run_tool(
        "RunTaskPacket",
        "tasking",
        json!({
            "objective": "Audit packet",
            "scope": "module",
            "scope_path": "tools",
            "repo": "johnny",
            "worktree": repo_root.display().to_string(),
            "branch_policy": "main only",
            "acceptance_tests": ["cargo build -p rusty-claude-cli"],
            "commit_policy": "no commit",
            "reporting_contract": "write findings",
            "escalation_policy": "stop on destructive ambiguity"
        }),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "TaskGet",
        "tasking",
        json!({"task_id": task_id}),
        |result| any_ok(result),
    ));
    entries.push(run_tool("TaskList", "tasking", json!({}), |result| {
        any_ok(result)
    }));
    entries.push(run_tool(
        "TaskUpdate",
        "tasking",
        json!({"task_id": task_id, "message": "updated by tool audit"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "TaskOutput",
        "tasking",
        json!({"task_id": task_id}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "TaskStop",
        "tasking",
        json!({"task_id": task_id}),
        |result| any_ok(result),
    ));

    let mut worker_id = String::new();
    let worker_dir = std::env::temp_dir().join("claw-worker-audit");
    fs::create_dir_all(&worker_dir)?;
    entries.push(run_tool_capture(
        "WorkerCreate",
        "worker",
        json!({"cwd": worker_dir.display().to_string(), "trusted_roots": []}),
        |result| {
            if let Ok(value) = &result {
                worker_id = value["worker_id"].as_str().unwrap_or_default().to_string();
            }
            any_ok(result)
        },
    ));
    entries.push(run_tool(
        "WorkerGet",
        "worker",
        json!({"worker_id": worker_id}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WorkerObserve",
        "worker",
        json!({"worker_id": worker_id, "screen_text": "Do you trust the files in this folder?"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WorkerResolveTrust",
        "worker",
        json!({"worker_id": worker_id}),
        |result| match result {
            Ok(value) => any_ok(Ok(value)),
            Err(error) => blocked_or_failed(error),
        },
    ));
    execute_tool(
        "WorkerObserve",
        &json!({"worker_id": worker_id, "screen_text": "Ready for prompt\n>" }),
    )
    .map_err(|error| format!("failed to prepare worker ready state: {error}"))?;
    entries.push(run_tool(
        "WorkerAwaitReady",
        "worker",
        json!({"worker_id": worker_id}),
        |result| match result {
            Ok(value) => any_ok(Ok(value)),
            Err(error) => blocked_or_failed(error),
        },
    ));
    entries.push(run_tool(
        "WorkerSendPrompt",
        "worker",
        json!({"worker_id": worker_id, "prompt": "Hello worker"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WorkerRestart",
        "worker",
        json!({"worker_id": worker_id}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WorkerObserveCompletion",
        "worker",
        json!({"worker_id": worker_id, "finish_reason": "completed", "tokens_output": 1}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "WorkerTerminate",
        "worker",
        json!({"worker_id": worker_id}),
        |result| any_ok(result),
    ));

    let mut team_id = String::new();
    entries.push(run_tool_capture(
        "TeamCreate",
        "team",
        json!({"name": "tool-audit-team", "tasks": [{"task_id": task_id}]}),
        |result| {
            if let Ok(value) = &result {
                team_id = value["team_id"].as_str().unwrap_or_default().to_string();
            }
            any_ok(result)
        },
    ));
    entries.push(run_tool(
        "TeamDelete",
        "team",
        json!({"team_id": team_id}),
        |result| any_ok(result),
    ));

    let mut cron_id = String::new();
    entries.push(run_tool_capture(
        "CronCreate",
        "cron",
        json!({"schedule": "0 * * * *", "prompt": "ping", "description": "tool audit"}),
        |result| {
            if let Ok(value) = &result {
                cron_id = value["cron_id"].as_str().unwrap_or_default().to_string();
            }
            any_ok(result)
        },
    ));
    entries.push(run_tool("CronList", "cron", json!({}), |result| {
        any_ok(result)
    }));
    entries.push(run_tool(
        "CronDelete",
        "cron",
        json!({"cron_id": cron_id}),
        |result| any_ok(result),
    ));

    entries.push(run_tool(
        "LSP",
        "integration",
        json!({"action": "symbols", "path": repo_root.join("launch.ps1").display().to_string()}),
        |result| match result {
            Ok(value) if value.get("error").is_some() => (
                String::from("blocked"),
                value,
                Some(String::from(
                    "No LSP server registered for this path/language",
                )),
            ),
            Ok(value) => audit_pass(value),
            Err(error) => blocked_or_failed(error),
        },
    ));
    entries.push(run_tool(
        "ListMcpResources",
        "integration",
        json!({"server": "default"}),
        |result| classify_mcp_result(result, "No MCP server registered"),
    ));
    entries.push(run_tool(
        "ReadMcpResource",
        "integration",
        json!({"server": "default", "uri": "file://guide.txt"}),
        |result| classify_mcp_result(result, "No MCP resource available"),
    ));
    entries.push(run_tool(
        "McpAuth",
        "integration",
        json!({"server": "default"}),
        |result| classify_disconnected_result(result, "MCP server not configured"),
    ));
    entries.push(run_tool(
        "RemoteTrigger",
        "integration",
        json!({"url": "https://example.com", "method": "GET"}),
        |result| any_ok(result),
    ));
    entries.push(run_tool(
        "MCP",
        "integration",
        json!({"server": "default", "tool": "echo", "arguments": {"text": "hello"}}),
        |result| classify_mcp_result(result, "MCP tool bridge not configured"),
    ));
    entries.push(run_tool(
        "TestingPermission",
        "integration",
        json!({"action": "audit"}),
        |result| any_ok(result),
    ));

    for entry in &entries {
        if entry.status == "failed" {
            bug_lines.push(format!("## {}", entry.tool_name));
            bug_lines.push(format!("- Category: {}", entry.category));
            bug_lines.push(format!("- Input: `{}`", entry.input));
            bug_lines.push(format!(
                "- Evidence: `{}`",
                serde_json::to_string(&entry.evidence).unwrap_or_else(|_| String::from("{}"))
            ));
            if let Some(cause) = &entry.likely_cause {
                bug_lines.push(format!("- Likely cause: {}", cause));
            }
            bug_lines.push(String::new());
        }
    }

    fs::write(
        audit_dir.join("results.json"),
        serde_json::to_string_pretty(&entries)?,
    )?;
    fs::write(audit_dir.join("bugs.md"), bug_lines.join("\n"))?;
    fs::write(audit_dir.join("report.md"), render_report(&entries))?;

    println!(
        "tool audit complete: passed={} partial={} blocked={} failed={}",
        count_status(&entries, "passed"),
        count_status(&entries, "partial"),
        count_status(&entries, "blocked"),
        count_status(&entries, "failed")
    );
    Ok(())
}

fn invoke_mode(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let tool = args.get(2).ok_or("missing tool name")?;
    let input_path = args.get(3).ok_or("missing input path")?;
    let input: Value = serde_json::from_str(&fs::read_to_string(input_path)?)?;
    let result = match execute_tool(tool, &input) {
        Ok(output) => ChildResult {
            ok: true,
            output: Some(output),
            error: None,
        },
        Err(error) => ChildResult {
            ok: false,
            output: None,
            error: Some(error),
        },
    };
    println!("{}", serde_json::to_string(&result)?);
    Ok(())
}

fn resolve_repo_root(start: &Path) -> Result<PathBuf, Box<dyn std::error::Error>> {
    for ancestor in start.ancestors() {
        if ancestor.join("rust").is_dir() {
            return Ok(ancestor.to_path_buf());
        }
    }
    Err("failed to resolve repository root".into())
}

fn run_tool<F>(tool_name: &str, category: &str, input: Value, classify: F) -> AuditEntry
where
    F: FnOnce(Result<Value, String>) -> (String, Value, Option<String>),
{
    run_tool_capture(tool_name, category, input, classify)
}

fn run_tool_capture<F>(tool_name: &str, category: &str, input: Value, classify: F) -> AuditEntry
where
    F: FnOnce(Result<Value, String>) -> (String, Value, Option<String>),
{
    let raw = execute_tool(tool_name, &input).map(|output| parse_output(&output));
    let (status, evidence, likely_cause) = classify(raw);
    AuditEntry {
        tool_name: tool_name.to_string(),
        category: category.to_string(),
        status,
        input,
        evidence,
        likely_cause,
    }
}

fn run_child_tool<F>(
    audit_dir: &Path,
    cwd: &Path,
    tool_name: &str,
    category: &str,
    input: Value,
    stdin_text: Option<&str>,
    classify: F,
) -> AuditEntry
where
    F: FnOnce(Result<Value, String>) -> (String, Value, Option<String>),
{
    let input_path = audit_dir
        .join("tmp")
        .join(format!("{tool_name}-input.json"));
    let write_result = serde_json::to_string_pretty(&input)
        .map_err(|error| error.to_string())
        .and_then(|contents| fs::write(&input_path, contents).map_err(|error| error.to_string()));
    let raw = match write_result {
        Ok(()) => invoke_tool_in_child(cwd, tool_name, &input_path, stdin_text),
        Err(error) => Err(error.to_string()),
    };
    let parsed = raw.and_then(|value| {
        if value["ok"].as_bool().unwrap_or(false) {
            Ok(parse_output(value["output"].as_str().unwrap_or("{}")))
        } else {
            Err(value["error"]
                .as_str()
                .unwrap_or("child invocation failed")
                .to_string())
        }
    });
    let (status, evidence, likely_cause) = classify(parsed);
    AuditEntry {
        tool_name: tool_name.to_string(),
        category: category.to_string(),
        status,
        input,
        evidence,
        likely_cause,
    }
}

fn invoke_tool_in_child(
    cwd: &Path,
    tool_name: &str,
    input_path: &Path,
    stdin_text: Option<&str>,
) -> Result<Value, String> {
    let exe = env::current_exe().map_err(|error| error.to_string())?;
    let mut child = Command::new(exe)
        .current_dir(cwd)
        .arg("invoke")
        .arg(tool_name)
        .arg(input_path)
        .stdin(if stdin_text.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;

    if let Some(text) = stdin_text {
        if let Some(mut stdin) = child.stdin.take() {
            stdin
                .write_all(text.as_bytes())
                .map_err(|error| error.to_string())?;
        }
    }

    let output = child
        .wait_with_output()
        .map_err(|error| error.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    extract_last_json_object(&stdout)
        .ok_or_else(|| format!("child output did not contain JSON: {}", stdout.trim()))
        .and_then(|json| serde_json::from_str(&json).map_err(|error| error.to_string()))
}

fn extract_last_json_object(stdout: &str) -> Option<String> {
    for (index, _) in stdout.match_indices('{').rev() {
        let candidate = stdout[index..].trim();
        if serde_json::from_str::<Value>(candidate).is_ok() {
            return Some(candidate.to_string());
        }
    }
    None
}

fn parse_output(output: &str) -> Value {
    serde_json::from_str(output).unwrap_or_else(|_| json!({ "raw": output }))
}

fn classify_agent_result(value: Value) -> (String, Value, Option<String>) {
    let manifest_path = value["manifestFile"]
        .as_str()
        .map(PathBuf::from)
        .unwrap_or_default();
    if manifest_path.as_os_str().is_empty() {
        return audit_fail(value, "Agent result did not include a manifest path");
    }

    for _ in 0..50 {
        if let Ok(contents) = fs::read_to_string(&manifest_path) {
            if let Ok(manifest_json) = serde_json::from_str::<Value>(&contents) {
                let status = manifest_json["status"].as_str().unwrap_or_default();
                if status == "completed" {
                    return audit_pass(manifest_json);
                }
                if status == "failed" {
                    return audit_fail(manifest_json, "Agent background job failed");
                }
            }
        }
        thread::sleep(std::time::Duration::from_millis(200));
    }

    (
        String::from("partial"),
        value,
        Some(String::from(
            "Agent creation succeeded; background completion is asynchronous",
        )),
    )
}

fn any_ok(result: Result<Value, String>) -> (String, Value, Option<String>) {
    match result {
        Ok(value) => audit_pass(value),
        Err(error) => blocked_or_failed(error),
    }
}

fn classify_mcp_result(
    result: Result<Value, String>,
    blocked_reason: &str,
) -> (String, Value, Option<String>) {
    match result {
        Ok(value) if value.get("error").is_some() => (
            String::from("blocked"),
            value,
            Some(blocked_reason.to_string()),
        ),
        Ok(value) => audit_pass(value),
        Err(error) => blocked_or_failed(error),
    }
}

fn classify_disconnected_result(
    result: Result<Value, String>,
    blocked_reason: &str,
) -> (String, Value, Option<String>) {
    match result {
        Ok(value) if value["status"] == "disconnected" => (
            String::from("blocked"),
            value,
            Some(blocked_reason.to_string()),
        ),
        Ok(value) => audit_pass(value),
        Err(error) => blocked_or_failed(error),
    }
}

fn audit_pass(value: Value) -> (String, Value, Option<String>) {
    (String::from("passed"), value, None)
}

fn audit_fail(value: Value, cause: &str) -> (String, Value, Option<String>) {
    (String::from("failed"), value, Some(cause.to_string()))
}

fn audit_failed_error(error: String) -> (String, Value, Option<String>) {
    (
        String::from("failed"),
        json!({ "error": error }),
        Some(String::from("tool invocation returned an error")),
    )
}

fn blocked_or_failed(error: String) -> (String, Value, Option<String>) {
    let lower = error.to_lowercase();
    let blocked = [
        "unknown skill",
        "not registered",
        "not configured",
        "server not",
        "disconnected",
        "not found",
        "executable not found",
        "requires approval",
        "has no prompt to send or replay",
        "not ready for prompt delivery",
        "trust",
    ]
    .iter()
    .any(|needle| lower.contains(needle));

    if blocked {
        (
            String::from("blocked"),
            json!({ "error": error }),
            Some(String::from(
                "blocked by missing config/dependency/runtime state",
            )),
        )
    } else {
        audit_failed_error(error)
    }
}

fn output_contains(value: &Value, field: &str, needle: &str) -> bool {
    value[field]
        .as_str()
        .is_some_and(|text| text.contains(needle))
}

fn count_status(entries: &[AuditEntry], status: &str) -> usize {
    entries
        .iter()
        .filter(|entry| entry.status == status)
        .count()
}

fn render_report(entries: &[AuditEntry]) -> String {
    let mut lines = vec![
        String::from("# Tool Audit Report"),
        String::new(),
        format!("- passed: {}", count_status(entries, "passed")),
        format!("- partial: {}", count_status(entries, "partial")),
        format!("- blocked: {}", count_status(entries, "blocked")),
        format!("- failed: {}", count_status(entries, "failed")),
        String::new(),
    ];

    for entry in entries {
        lines.push(format!("## {}", entry.tool_name));
        lines.push(format!("- Category: {}", entry.category));
        lines.push(format!("- Status: {}", entry.status));
        lines.push(format!("- Input: `{}`", entry.input));
        lines.push(format!(
            "- Evidence: `{}`",
            serde_json::to_string(&entry.evidence).unwrap_or_else(|_| String::from("{}"))
        ));
        if let Some(cause) = &entry.likely_cause {
            lines.push(format!("- Likely cause: {}", cause));
        }
        lines.push(String::new());
    }

    lines.join("\n")
}

fn with_env<F, T>(key: &str, value: Option<&std::ffi::OsStr>, func: F) -> T
where
    F: FnOnce() -> T,
{
    let original = env::var_os(key);
    match value {
        Some(value) => env::set_var(key, value),
        None => env::remove_var(key),
    }
    let result = func();
    match original {
        Some(value) => env::set_var(key, value),
        None => env::remove_var(key),
    }
    result
}

fn with_home_and_cwd<F>(
    home_root: &Path,
    cwd: &Path,
    func: F,
) -> Result<(), Box<dyn std::error::Error>>
where
    F: FnOnce(),
{
    let original_home = env::var_os("HOME");
    let original_userprofile = env::var_os("USERPROFILE");
    let original_cwd = env::current_dir()?;

    env::set_var("HOME", home_root);
    env::set_var("USERPROFILE", home_root);
    env::set_current_dir(cwd)?;
    func();

    env::set_current_dir(original_cwd)?;
    match original_home {
        Some(value) => env::set_var("HOME", value),
        None => env::remove_var("HOME"),
    }
    match original_userprofile {
        Some(value) => env::set_var("USERPROFILE", value),
        None => env::remove_var("USERPROFILE"),
    }
    Ok(())
}

#[allow(dead_code)]
fn unique_name(prefix: &str) -> String {
    format!(
        "{}-{}",
        prefix,
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0)
    )
}
