use std::collections::BTreeMap;
use std::fmt::{Display, Formatter, Write};
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};
use telemetry::SessionTracer;

use crate::bash::{execute_bash, BashCommandInput, BashCommandOutput};
use crate::compact::{
    compact_session, estimate_api_request_tokens, estimate_session_tokens, CompactionConfig,
    CompactionResult,
};
use crate::config::{CompletionVerifyConfig, RuntimeFeatureConfig};
use crate::hooks::{HookAbortSignal, HookProgressReporter, HookRunResult, HookRunner};
use crate::permissions::{
    PermissionContext, PermissionOutcome, PermissionPolicy, PermissionPrompter,
};
use crate::sandbox::FilesystemIsolationMode;
use crate::session::{ContentBlock, ConversationMessage, Session, SessionTaskLedgerUpdate};
use crate::tool_output::{tool_result_truncation_limit, truncate_tool_output};
use crate::usage::{TokenUsage, UsageTracker};

const DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD: u32 = 100_000;
const AUTO_COMPACTION_THRESHOLD_ENV_VAR: &str = "CLAUDE_CODE_AUTO_COMPACT_INPUT_TOKENS";
/// Identical consecutive tool failures before corrective feedback is injected.
const IDENTICAL_TOOL_FAILURE_NUDGE: u32 = 3;
/// Identical consecutive tool failures before the turn is aborted outright.
const IDENTICAL_TOOL_FAILURE_ABORT: u32 = 6;

/// Fully assembled request payload sent to the upstream model client.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApiRequest {
    pub system_prompt: Vec<String>,
    pub messages: Vec<ConversationMessage>,
}

/// Streamed events emitted while processing a single assistant turn.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AssistantEvent {
    TextDelta(String),
    ToolUse {
        id: String,
        name: String,
        input: String,
    },
    Usage(TokenUsage),
    PromptCache(PromptCacheEvent),
    MessageStop,
}

/// Prompt-cache telemetry captured from the provider response stream.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromptCacheEvent {
    pub unexpected: bool,
    pub reason: String,
    pub previous_cache_read_input_tokens: u32,
    pub current_cache_read_input_tokens: u32,
    pub token_drop: u32,
}

/// Minimal streaming API contract required by [`ConversationRuntime`].
pub trait ApiClient {
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError>;
}

/// Trait implemented by tool dispatchers that execute model-requested tools.
pub trait ToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError>;
}

/// Error returned when a tool invocation fails locally.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ToolError {
    message: String,
}

impl ToolError {
    #[must_use]
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for ToolError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for ToolError {}

/// Error returned when a conversation turn cannot be completed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeError {
    message: String,
}

impl RuntimeError {
    #[must_use]
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for RuntimeError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for RuntimeError {}

/// Summary of one completed runtime turn, including tool results and usage.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TurnSummary {
    pub assistant_messages: Vec<ConversationMessage>,
    pub tool_results: Vec<ConversationMessage>,
    pub prompt_cache_events: Vec<PromptCacheEvent>,
    pub iterations: usize,
    pub usage: TokenUsage,
    pub auto_compaction: Option<AutoCompactionEvent>,
}

/// Details about automatic session compaction applied during a turn.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AutoCompactionEvent {
    pub removed_message_count: usize,
}

/// Coordinates the model loop, tool execution, hooks, and session updates.
pub struct ConversationRuntime<C, T> {
    session: Session,
    api_client: C,
    tool_executor: T,
    permission_policy: PermissionPolicy,
    system_prompt: Vec<String>,
    max_iterations: usize,
    usage_tracker: UsageTracker,
    hook_runner: HookRunner,
    auto_compaction_input_tokens_threshold: u32,
    hook_abort_signal: HookAbortSignal,
    hook_progress_reporter: Option<Box<dyn HookProgressReporter>>,
    session_tracer: Option<SessionTracer>,
    completion_verify: CompletionVerifyConfig,
    /// Provider context window for the active model (tokens), when known (e.g. from `--model-context-window`).
    model_context_window: Option<u32>,
}

impl<C, T> ConversationRuntime<C, T>
where
    C: ApiClient,
    T: ToolExecutor,
{
    #[must_use]
    pub fn new(
        session: Session,
        api_client: C,
        tool_executor: T,
        permission_policy: PermissionPolicy,
        system_prompt: Vec<String>,
    ) -> Self {
        Self::new_with_features(
            session,
            api_client,
            tool_executor,
            permission_policy,
            system_prompt,
            &RuntimeFeatureConfig::default(),
        )
    }

    #[must_use]
    #[allow(clippy::needless_pass_by_value)]
    pub fn new_with_features(
        session: Session,
        api_client: C,
        tool_executor: T,
        permission_policy: PermissionPolicy,
        system_prompt: Vec<String>,
        feature_config: &RuntimeFeatureConfig,
    ) -> Self {
        let usage_tracker = UsageTracker::from_session(&session);
        Self {
            session,
            api_client,
            tool_executor,
            permission_policy,
            system_prompt,
            max_iterations: usize::MAX,
            usage_tracker,
            hook_runner: HookRunner::from_feature_config(feature_config),
            auto_compaction_input_tokens_threshold: auto_compaction_threshold_from_env(),
            hook_abort_signal: HookAbortSignal::default(),
            hook_progress_reporter: None,
            session_tracer: None,
            completion_verify: feature_config.completion_verify().clone(),
            model_context_window: None,
        }
    }

    #[must_use]
    pub fn with_model_context_window(mut self, context_window_tokens: Option<u32>) -> Self {
        self.model_context_window = context_window_tokens;
        self
    }

    #[must_use]
    pub fn with_max_iterations(mut self, max_iterations: usize) -> Self {
        self.max_iterations = max_iterations;
        self
    }

    #[must_use]
    pub fn with_auto_compaction_input_tokens_threshold(mut self, threshold: u32) -> Self {
        self.auto_compaction_input_tokens_threshold = threshold;
        self
    }

    #[must_use]
    pub fn with_hook_abort_signal(mut self, hook_abort_signal: HookAbortSignal) -> Self {
        self.hook_abort_signal = hook_abort_signal;
        self
    }

    #[must_use]
    pub fn with_hook_progress_reporter(
        mut self,
        hook_progress_reporter: Box<dyn HookProgressReporter>,
    ) -> Self {
        self.hook_progress_reporter = Some(hook_progress_reporter);
        self
    }

    #[must_use]
    pub fn with_session_tracer(mut self, session_tracer: SessionTracer) -> Self {
        self.session_tracer = Some(session_tracer);
        self
    }

    fn run_pre_tool_use_hook(&mut self, tool_name: &str, input: &str) -> HookRunResult {
        if let Some(reporter) = self.hook_progress_reporter.as_mut() {
            self.hook_runner.run_pre_tool_use_with_context(
                tool_name,
                input,
                Some(&self.hook_abort_signal),
                Some(reporter.as_mut()),
            )
        } else {
            self.hook_runner.run_pre_tool_use_with_context(
                tool_name,
                input,
                Some(&self.hook_abort_signal),
                None,
            )
        }
    }

    fn run_post_tool_use_hook(
        &mut self,
        tool_name: &str,
        input: &str,
        output: &str,
        is_error: bool,
    ) -> HookRunResult {
        if let Some(reporter) = self.hook_progress_reporter.as_mut() {
            self.hook_runner.run_post_tool_use_with_context(
                tool_name,
                input,
                output,
                is_error,
                Some(&self.hook_abort_signal),
                Some(reporter.as_mut()),
            )
        } else {
            self.hook_runner.run_post_tool_use_with_context(
                tool_name,
                input,
                output,
                is_error,
                Some(&self.hook_abort_signal),
                None,
            )
        }
    }

    fn run_post_tool_use_failure_hook(
        &mut self,
        tool_name: &str,
        input: &str,
        output: &str,
    ) -> HookRunResult {
        if let Some(reporter) = self.hook_progress_reporter.as_mut() {
            self.hook_runner.run_post_tool_use_failure_with_context(
                tool_name,
                input,
                output,
                Some(&self.hook_abort_signal),
                Some(reporter.as_mut()),
            )
        } else {
            self.hook_runner.run_post_tool_use_failure_with_context(
                tool_name,
                input,
                output,
                Some(&self.hook_abort_signal),
                None,
            )
        }
    }

    /// Run a session health probe to verify the runtime is functional after compaction.
    /// Returns Ok(()) if healthy, Err if the session appears broken.
    fn run_session_health_probe(&mut self) -> Result<(), String> {
        // Check if we have basic session integrity
        if self.session.messages.is_empty() && self.session.compaction.is_some() {
            // Freshly compacted with no messages - this is normal
            return Ok(());
        }

        // Verify tool executor is responsive with a non-destructive probe
        // Using glob_search with a pattern that won't match anything
        let probe_input = r#"{"pattern": "*.health-check-probe-"}"#;
        match self.tool_executor.execute("glob_search", probe_input) {
            Ok(_) => Ok(()),
            Err(e) => Err(format!("Tool executor probe failed: {e}")),
        }
    }

    fn completion_verify_workspace(&self) -> PathBuf {
        self.session
            .workspace_root()
            .map(PathBuf::from)
            .or_else(|| std::env::current_dir().ok())
            .unwrap_or_else(|| PathBuf::from("."))
    }

    fn resolved_completion_verify_command(&self) -> Option<String> {
        let cfg = &self.completion_verify;
        let trimmed = cfg.command.trim();
        if !trimmed.is_empty() {
            return Some(cfg.command.clone());
        }
        detect_completion_verify_command(&self.completion_verify_workspace())
    }

    fn completion_verify_should_run(&self, had_tool_results: bool) -> bool {
        let cfg = &self.completion_verify;
        if !cfg.enabled {
            return false;
        }
        if self.resolved_completion_verify_command().is_none() {
            return false;
        }
        !cfg.skip_if_no_tools || had_tool_results
    }

    fn maybe_log_completion_verify_skipped(&self) {
        let cfg = &self.completion_verify;
        if !cfg.enabled || !cfg.command.trim().is_empty() {
            return;
        }
        if detect_completion_verify_command(&self.completion_verify_workspace()).is_some() {
            return;
        }
        let ws = self.completion_verify_workspace();
        eprintln!(
            "verify.skipped: no project markers detected in {}",
            ws.display()
        );
    }

    fn run_completion_verify(&self) -> Result<(), String> {
        let cfg = &self.completion_verify;
        let Some(command) = self.resolved_completion_verify_command() else {
            return Ok(());
        };
        let command_label = command.clone();
        let cwd = self.completion_verify_workspace();
        let output = execute_bash(BashCommandInput {
            command,
            timeout: Some(cfg.timeout_ms),
            description: Some("Claw completion verification".to_string()),
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: Some(false),
            isolate_network: Some(false),
            filesystem_mode: Some(FilesystemIsolationMode::Off),
            allowed_mounts: None,
            cwd: Some(cwd),
        })
        .map_err(|e| {
            format!(
                "[Engine completion verification failed — could not run the verify command.]\n\n{e}"
            )
        })?;
        if completion_verify_output_ok(&output) {
            Ok(())
        } else {
            Err(format_completion_verify_feedback(&command_label, &output))
        }
    }

    fn effective_auto_compaction_input_tokens_threshold(&self) -> u32 {
        let configured = self.auto_compaction_input_tokens_threshold;
        let Some(ctx) = self.model_context_window else {
            return configured;
        };
        let raw = ((u64::from(ctx)).saturating_mul(60).saturating_div(100)).max(10_000);
        let cap = u32::try_from(raw).unwrap_or(u32::MAX);
        configured.min(cap)
    }

    fn ensure_prompt_within_model_context_window(&mut self) -> Result<(), RuntimeError> {
        let Some(ctx) = self.model_context_window else {
            return Ok(());
        };
        let soft_limit = (usize::try_from(ctx).unwrap_or(usize::MAX))
            .saturating_mul(90)
            .saturating_div(100)
            .max(1024);
        let mut estimate = estimate_api_request_tokens(&self.system_prompt, &self.session.messages);
        if estimate <= soft_limit {
            return Ok(());
        }
        let result = compact_session(
            &self.session,
            CompactionConfig {
                max_estimated_tokens: 0,
                ..CompactionConfig::default()
            },
        );
        if result.removed_message_count > 0 {
            self.session = result.compacted_session;
        }
        estimate = estimate_api_request_tokens(&self.system_prompt, &self.session.messages);
        if estimate > soft_limit {
            return Err(RuntimeError::new(
                "prompt too large for model context — auto-compact insufficient; use /compact or /clear",
            ));
        }
        Ok(())
    }

    #[allow(clippy::too_many_lines)]
    pub fn run_turn(
        &mut self,
        user_input: impl Into<String>,
        mut prompter: Option<&mut dyn PermissionPrompter>,
    ) -> Result<TurnSummary, RuntimeError> {
        let user_input = user_input.into();

        // ROADMAP #38: Session-health canary - probe if context was compacted
        if self.session.compaction.is_some() {
            if let Err(error) = self.run_session_health_probe() {
                return Err(RuntimeError::new(format!(
                    "Session health probe failed after compaction: {error}. \
                     The session may be in an inconsistent state. \
                     Consider starting a fresh session with /session new."
                )));
            }
        }

        self.record_turn_started(&user_input);
        let mutation_requested = user_requests_filesystem_execution(&user_input)
            || session_has_pending_filesystem_execution(&self.session);
        self.session
            .push_user_text(user_input)
            .map_err(|error| RuntimeError::new(error.to_string()))?;

        let mut assistant_messages = Vec::new();
        let mut tool_results = Vec::new();
        let mut prompt_cache_events = Vec::new();
        let mut iterations = 0;
        let mut evidence_nudges = 0_u8;
        // Circuit breaker for repeated identical tool failures: weaker models
        // retry the same malformed call indefinitely. Nudge with corrective
        // feedback after IDENTICAL_TOOL_FAILURE_NUDGE, abort the turn after
        // IDENTICAL_TOOL_FAILURE_ABORT instead of grinding to max_iterations.
        let mut failure_streak: Option<(String, String, u32)> = None;

        loop {
            iterations += 1;
            if iterations > self.max_iterations {
                let error = RuntimeError::new(
                    "conversation loop exceeded the maximum number of iterations",
                );
                self.record_turn_failed(iterations, &error);
                return Err(error);
            }

            self.ensure_prompt_within_model_context_window()?;

            let request = ApiRequest {
                system_prompt: self.system_prompt.clone(),
                messages: self.session.messages.clone(),
            };
            let events = match self.api_client.stream(request) {
                Ok(events) => events,
                Err(error) => {
                    self.record_turn_failed(iterations, &error);
                    return Err(error);
                }
            };
            let (mut assistant_message, usage, turn_prompt_cache_events) =
                match build_assistant_message(events) {
                    Ok(result) => result,
                    Err(error) => {
                        self.record_turn_failed(iterations, &error);
                        return Err(error);
                    }
                };
            let recovered_compat_tool = recover_compat_text_tool_call(
                &mut assistant_message,
                self.session.model.as_deref(),
                iterations,
            );
            let malformed_compat_tool = !recovered_compat_tool
                && looks_like_malformed_compat_tool_call(
                    &assistant_message,
                    self.session.model.as_deref(),
                );
            let unsupported_mutation_completion =
                mutation_requested && !tool_results.iter().any(tool_result_succeeded);
            if let Some(usage) = usage {
                self.usage_tracker.record(usage);
            }
            prompt_cache_events.extend(turn_prompt_cache_events);
            let pending_tool_uses = assistant_message
                .blocks
                .iter()
                .filter_map(|block| match block {
                    ContentBlock::ToolUse { id, name, input } => {
                        Some((id.clone(), name.clone(), input.clone()))
                    }
                    _ => None,
                })
                .collect::<Vec<_>>();
            self.record_assistant_iteration(
                iterations,
                &assistant_message,
                pending_tool_uses.len(),
            );

            self.session
                .push_message(assistant_message.clone())
                .map_err(|error| RuntimeError::new(error.to_string()))?;
            assistant_messages.push(assistant_message);

            if pending_tool_uses.is_empty() {
                if malformed_compat_tool || unsupported_mutation_completion {
                    evidence_nudges = evidence_nudges.saturating_add(1);
                    if evidence_nudges > 2 {
                        let error = RuntimeError::new(
                            "model repeatedly claimed or attempted filesystem work without a valid tool call",
                        );
                        self.record_turn_failed(iterations, &error);
                        return Err(error);
                    }
                    let feedback = if malformed_compat_tool {
                        "Your previous response looked like a tool request but was not valid. Emit a native tool call, or emit exactly one JSON object shaped as {\"tool\":\"tool_name\",\"arguments\":{...}} with no prose. Do not claim success until the tool result confirms it."
                    } else {
                        "No filesystem tool succeeded in this turn, so the claimed change has no execution evidence. Use the appropriate tool now and do not report success until its result confirms the change."
                    };
                    self.session
                        .push_user_text(feedback)
                        .map_err(|error| RuntimeError::new(error.to_string()))?;
                    continue;
                }
                if self.completion_verify_should_run(!tool_results.is_empty()) {
                    match self.run_completion_verify() {
                        Ok(()) => break,
                        Err(feedback) => {
                            self.session
                                .push_user_text(feedback)
                                .map_err(|error| RuntimeError::new(error.to_string()))?;
                            continue;
                        }
                    }
                }
                if !self.completion_verify_should_run(!tool_results.is_empty()) {
                    self.maybe_log_completion_verify_skipped();
                    break;
                }
            }

            for (tool_use_id, tool_name, input) in pending_tool_uses {
                let pre_hook_result = self.run_pre_tool_use_hook(&tool_name, &input);
                let effective_input = pre_hook_result
                    .updated_input()
                    .map_or_else(|| input.clone(), ToOwned::to_owned);
                let permission_context = PermissionContext::new(
                    pre_hook_result.permission_override(),
                    pre_hook_result.permission_reason().map(ToOwned::to_owned),
                );

                let permission_outcome = if pre_hook_result.is_cancelled() {
                    PermissionOutcome::Deny {
                        reason: format_hook_message(
                            &pre_hook_result,
                            &format!("PreToolUse hook cancelled tool `{tool_name}`"),
                        ),
                    }
                } else if pre_hook_result.is_failed() {
                    PermissionOutcome::Deny {
                        reason: format_hook_message(
                            &pre_hook_result,
                            &format!("PreToolUse hook failed for tool `{tool_name}`"),
                        ),
                    }
                } else if pre_hook_result.is_denied() {
                    PermissionOutcome::Deny {
                        reason: format_hook_message(
                            &pre_hook_result,
                            &format!("PreToolUse hook denied tool `{tool_name}`"),
                        ),
                    }
                } else if let Some(prompt) = prompter.as_mut() {
                    self.permission_policy.authorize_with_context(
                        &tool_name,
                        &effective_input,
                        &permission_context,
                        Some(*prompt),
                    )
                } else {
                    self.permission_policy.authorize_with_context(
                        &tool_name,
                        &effective_input,
                        &permission_context,
                        None,
                    )
                };

                let result_message = match permission_outcome {
                    PermissionOutcome::Allow => {
                        self.record_tool_started(iterations, &tool_name);
                        let (mut output, mut is_error) = match tool_name.as_str() {
                            "TaskLedgerRead" => (
                                serde_json::to_string_pretty(&self.session.task_ledger())
                                    .map_err(|error| RuntimeError::new(error.to_string()))?,
                                false,
                            ),
                            "TaskLedgerUpdate" => {
                                let update = parse_task_ledger_update(&effective_input)?;
                                match self.session.update_task_ledger(update) {
                                    Ok(()) => (
                                        serde_json::to_string_pretty(&self.session.task_ledger())
                                            .map_err(|error| RuntimeError::new(error.to_string()))?,
                                        false,
                                    ),
                                    Err(error) => (error.to_string(), true),
                                }
                            }
                            _ => match self.tool_executor.execute(&tool_name, &effective_input) {
                                Ok(output) => (output, false),
                                Err(error) => (error.to_string(), true),
                            },
                        };
                        output = merge_hook_feedback(pre_hook_result.messages(), output, false);

                        let post_hook_result = if is_error {
                            self.run_post_tool_use_failure_hook(
                                &tool_name,
                                &effective_input,
                                &output,
                            )
                        } else {
                            self.run_post_tool_use_hook(
                                &tool_name,
                                &effective_input,
                                &output,
                                false,
                            )
                        };
                        if post_hook_result.is_denied()
                            || post_hook_result.is_failed()
                            || post_hook_result.is_cancelled()
                        {
                            is_error = true;
                        }
                        output = merge_hook_feedback(
                            post_hook_result.messages(),
                            output,
                            post_hook_result.is_denied()
                                || post_hook_result.is_failed()
                                || post_hook_result.is_cancelled(),
                        );

                        if let Some(limit) = tool_result_truncation_limit(&tool_name) {
                            if output.len() > limit {
                                output = truncate_tool_output(&output, limit);
                            }
                        }

                        ConversationMessage::tool_result(tool_use_id, &tool_name, output, is_error)
                    }
                    PermissionOutcome::Deny { reason } => ConversationMessage::tool_result(
                        tool_use_id,
                        &tool_name,
                        merge_hook_feedback(pre_hook_result.messages(), reason, true),
                        true,
                    ),
                };
                self.record_ledger_from_tool(&tool_name, &effective_input, &result_message)?;
                self.session
                    .push_message(result_message.clone())
                    .map_err(|error| RuntimeError::new(error.to_string()))?;
                self.record_tool_finished(iterations, &result_message);
                match tool_failure_signature(&result_message) {
                    Some((name, signature)) => {
                        let count = match failure_streak.take() {
                            Some((prev_name, prev_sig, prev_count))
                                if prev_name == name && prev_sig == signature =>
                            {
                                prev_count + 1
                            }
                            _ => 1,
                        };
                        if count >= IDENTICAL_TOOL_FAILURE_ABORT {
                            let error = RuntimeError::new(format!(
                                "tool `{name}` failed {count} times in a row with the same \
                                 error — aborting the turn instead of looping. Last error: \
                                 {signature}"
                            ));
                            self.record_turn_failed(iterations, &error);
                            return Err(error);
                        }
                        if count == IDENTICAL_TOOL_FAILURE_NUDGE {
                            self.session
                                .push_user_text(format!(
                                    "[loop-guard] The `{name}` call has failed {count} times in \
                                     a row with the same error. Do not repeat the call \
                                     unchanged. Re-read the error message, then fix the \
                                     parameters, switch tools (write_file/edit_file for file \
                                     content rather than shell heredocs), or tell the user why \
                                     the task cannot proceed."
                                ))
                                .map_err(|error| RuntimeError::new(error.to_string()))?;
                        }
                        failure_streak = Some((name, signature, count));
                    }
                    None => failure_streak = None,
                }
                tool_results.push(result_message);
            }
        }

        let auto_compaction = self.maybe_auto_compact();

        let summary = TurnSummary {
            assistant_messages,
            tool_results,
            prompt_cache_events,
            iterations,
            usage: self.usage_tracker.cumulative_usage(),
            auto_compaction,
        };
        self.record_turn_completed(&summary);

        Ok(summary)
    }

    #[must_use]
    pub fn compact(&self, config: CompactionConfig) -> CompactionResult {
        compact_session(&self.session, config)
    }

    #[must_use]
    pub fn estimated_tokens(&self) -> usize {
        estimate_session_tokens(&self.session)
    }

    #[must_use]
    pub fn usage(&self) -> &UsageTracker {
        &self.usage_tracker
    }

    #[must_use]
    pub fn session(&self) -> &Session {
        &self.session
    }

    pub fn api_client_mut(&mut self) -> &mut C {
        &mut self.api_client
    }

    pub fn session_mut(&mut self) -> &mut Session {
        &mut self.session
    }

    fn record_ledger_from_tool(
        &mut self,
        tool_name: &str,
        input: &str,
        result_message: &ConversationMessage,
    ) -> Result<(), RuntimeError> {
        let Some(ContentBlock::ToolResult {
            output, is_error, ..
        }) = result_message.blocks.first()
        else {
            return Ok(());
        };
        if *is_error {
            return Ok(());
        }

        match tool_name {
            "write_file" | "edit_file" => {
                if let Some(path) = extract_path_from_tool_payload(output) {
                    self.session
                        .record_changed_path(path)
                        .map_err(|error| RuntimeError::new(error.to_string()))?;
                }
            }
            "bash" => {
                if should_record_verification_command(input) {
                    self.session
                        .record_verification(input)
                        .map_err(|error| RuntimeError::new(error.to_string()))?;
                }
            }
            _ => {}
        }
        Ok(())
    }

    #[must_use]
    pub fn fork_session(&self, branch_name: Option<String>) -> Session {
        self.session.fork(branch_name)
    }

    #[must_use]
    pub fn into_session(self) -> Session {
        self.session
    }

    fn maybe_auto_compact(&mut self) -> Option<AutoCompactionEvent> {
        if self.usage_tracker.cumulative_usage().input_tokens
            < self.effective_auto_compaction_input_tokens_threshold()
        {
            return None;
        }

        let result = compact_session(
            &self.session,
            CompactionConfig {
                max_estimated_tokens: 0,
                ..CompactionConfig::default()
            },
        );

        if result.removed_message_count == 0 {
            return None;
        }

        self.session = result.compacted_session;
        Some(AutoCompactionEvent {
            removed_message_count: result.removed_message_count,
        })
    }

    fn record_turn_started(&self, user_input: &str) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert(
            "user_input".to_string(),
            Value::String(user_input.to_string()),
        );
        session_tracer.record("turn_started", attributes);
    }

    fn record_assistant_iteration(
        &self,
        iteration: usize,
        assistant_message: &ConversationMessage,
        pending_tool_use_count: usize,
    ) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert("iteration".to_string(), Value::from(iteration as u64));
        attributes.insert(
            "assistant_blocks".to_string(),
            Value::from(assistant_message.blocks.len() as u64),
        );
        attributes.insert(
            "pending_tool_use_count".to_string(),
            Value::from(pending_tool_use_count as u64),
        );
        session_tracer.record("assistant_iteration_completed", attributes);
    }

    fn record_tool_started(&self, iteration: usize, tool_name: &str) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert("iteration".to_string(), Value::from(iteration as u64));
        attributes.insert(
            "tool_name".to_string(),
            Value::String(tool_name.to_string()),
        );
        session_tracer.record("tool_execution_started", attributes);
    }

    fn record_tool_finished(&self, iteration: usize, result_message: &ConversationMessage) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let Some(ContentBlock::ToolResult {
            tool_name,
            is_error,
            ..
        }) = result_message.blocks.first()
        else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert("iteration".to_string(), Value::from(iteration as u64));
        attributes.insert("tool_name".to_string(), Value::String(tool_name.clone()));
        attributes.insert("is_error".to_string(), Value::Bool(*is_error));
        session_tracer.record("tool_execution_finished", attributes);
    }

    fn record_turn_completed(&self, summary: &TurnSummary) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert(
            "iterations".to_string(),
            Value::from(summary.iterations as u64),
        );
        attributes.insert(
            "assistant_messages".to_string(),
            Value::from(summary.assistant_messages.len() as u64),
        );
        attributes.insert(
            "tool_results".to_string(),
            Value::from(summary.tool_results.len() as u64),
        );
        attributes.insert(
            "prompt_cache_events".to_string(),
            Value::from(summary.prompt_cache_events.len() as u64),
        );
        session_tracer.record("turn_completed", attributes);
    }

    fn record_turn_failed(&self, iteration: usize, error: &RuntimeError) {
        let Some(session_tracer) = &self.session_tracer else {
            return;
        };

        let mut attributes = Map::new();
        attributes.insert("iteration".to_string(), Value::from(iteration as u64));
        attributes.insert("error".to_string(), Value::String(error.to_string()));
        session_tracer.record("turn_failed", attributes);
    }
}

/// Reads the automatic compaction threshold from the environment.
#[must_use]
pub fn auto_compaction_threshold_from_env() -> u32 {
    parse_auto_compaction_threshold(
        std::env::var(AUTO_COMPACTION_THRESHOLD_ENV_VAR)
            .ok()
            .as_deref(),
    )
}

#[must_use]
fn parse_auto_compaction_threshold(value: Option<&str>) -> u32 {
    value
        .and_then(|raw| raw.trim().parse::<u32>().ok())
        .filter(|threshold| *threshold > 0)
        .unwrap_or(DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD)
}

fn build_assistant_message(
    events: Vec<AssistantEvent>,
) -> Result<
    (
        ConversationMessage,
        Option<TokenUsage>,
        Vec<PromptCacheEvent>,
    ),
    RuntimeError,
> {
    let mut text = String::new();
    let mut blocks = Vec::new();
    let mut prompt_cache_events = Vec::new();
    let mut finished = false;
    let mut usage = None;

    for event in events {
        match event {
            AssistantEvent::TextDelta(delta) => text.push_str(&delta),
            AssistantEvent::ToolUse { id, name, input } => {
                flush_text_block(&mut text, &mut blocks);
                blocks.push(ContentBlock::ToolUse { id, name, input });
            }
            AssistantEvent::Usage(value) => usage = Some(value),
            AssistantEvent::PromptCache(event) => prompt_cache_events.push(event),
            AssistantEvent::MessageStop => {
                finished = true;
            }
        }
    }

    flush_text_block(&mut text, &mut blocks);

    if !finished {
        return Err(RuntimeError::new(
            "assistant stream ended without a message stop event",
        ));
    }
    if blocks.is_empty() {
        return Err(RuntimeError::new("assistant stream produced no content"));
    }

    Ok((
        ConversationMessage::assistant_with_usage(blocks, usage),
        usage,
        prompt_cache_events,
    ))
}

/// Some OpenAI-compatible reasoning models emit a tool request as the entire
/// assistant text instead of populating the protocol's `tool_calls` field.
/// Recover only the narrow, explicit envelope used by those models and only
/// for known affected model families. Permission checks still run normally.
fn recover_compat_text_tool_call(
    message: &mut ConversationMessage,
    model: Option<&str>,
    iteration: usize,
) -> bool {
    let model = model.unwrap_or_default().to_ascii_lowercase();
    if !model.contains("gpt-oss") && !model.contains("glm") {
        return false;
    }
    let [ContentBlock::Text { text }] = message.blocks.as_slice() else {
        return false;
    };
    let json_text = exact_compat_tool_json(text);
    let Ok(value) = serde_json::from_str::<Value>(json_text) else {
        return false;
    };
    let Some(object) = value.as_object() else {
        return false;
    };
    let (name, arguments) = if object.get("type").and_then(Value::as_str) == Some("tool") {
        (
            object.get("name").and_then(Value::as_str),
            object.get("arguments"),
        )
    } else if object.get("type").and_then(Value::as_str) == Some("function") {
        let function = object.get("function").and_then(Value::as_object);
        (
            function
                .and_then(|value| value.get("name"))
                .and_then(Value::as_str),
            function.and_then(|value| value.get("arguments")),
        )
    } else if object.len() == 2 {
        (
            object.get("tool").and_then(Value::as_str),
            object.get("arguments"),
        )
    } else if object.len() == 1 {
        object
            .iter()
            .next()
            .map_or((None, None), |(name, arguments)| {
                (Some(name.as_str()), Some(arguments))
            })
    } else {
        (None, None)
    };
    let Some(name) = name else {
        return false;
    };
    if name.is_empty()
        || name.len() > 128
        || !name
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-'))
    {
        return false;
    }
    let Some(arguments) = arguments.and_then(normalize_compat_tool_arguments) else {
        return false;
    };
    message.blocks = vec![ContentBlock::ToolUse {
        id: format!("compat_text_tool_{iteration}"),
        name: name.to_string(),
        input: arguments.to_string(),
    }];
    true
}

fn exact_compat_tool_json(text: &str) -> &str {
    let trimmed = text.trim();
    if let Some(fenced) = trimmed
        .strip_prefix("```json")
        .and_then(|value| value.strip_suffix("```"))
    {
        return fenced.trim();
    }
    if let Some(fenced) = trimmed
        .strip_prefix("```")
        .and_then(|value| value.strip_suffix("```"))
    {
        return fenced.trim();
    }
    trimmed
}

fn normalize_compat_tool_arguments(value: &Value) -> Option<Value> {
    if value.is_object() {
        return Some(value.clone());
    }
    value
        .as_str()
        .and_then(|encoded| serde_json::from_str::<Value>(encoded).ok())
        .filter(Value::is_object)
}

fn compat_text_model(model: Option<&str>) -> bool {
    let model = model.unwrap_or_default().to_ascii_lowercase();
    model.contains("gpt-oss") || model.contains("glm")
}

fn looks_like_malformed_compat_tool_call(
    message: &ConversationMessage,
    model: Option<&str>,
) -> bool {
    if !compat_text_model(model) {
        return false;
    }
    let [ContentBlock::Text { text }] = message.blocks.as_slice() else {
        return false;
    };
    let trimmed = text.trim();
    if !(trimmed.starts_with('{') || trimmed.starts_with("```")) {
        return false;
    }
    trimmed.contains("\"tool\"")
        || trimmed.contains("\"name\"")
        || trimmed.contains("\"arguments\"")
        || ["write_file", "edit_file", "bash", "PowerShell"]
            .iter()
            .any(|name| trimmed.contains(&format!("\"{name}\"")))
}

fn user_requests_filesystem_execution(input: &str) -> bool {
    let lower = input.to_ascii_lowercase();
    if [
        "how do i ",
        "how can i ",
        "how to ",
        "show me how",
        "explain how",
        "give me an example",
    ]
    .iter()
    .any(|informational| lower.contains(informational))
    {
        return false;
    }
    [
        "create ",
        "make ",
        "build ",
        "write ",
        "edit ",
        "modify ",
        "delete ",
        "remove ",
        "rename ",
        "move ",
        "copy ",
        "generate ",
        "save ",
    ]
    .iter()
    .any(|verb| lower.contains(verb))
}

fn session_has_pending_filesystem_execution(session: &Session) -> bool {
    let mut pending = false;
    for message in &session.messages {
        match message.role {
            crate::session::MessageRole::User => {
                if message.blocks.iter().any(|block| {
                    matches!(block, ContentBlock::Text { text } if user_requests_filesystem_execution(text))
                }) {
                    pending = true;
                }
            }
            crate::session::MessageRole::Tool => {
                if message.blocks.iter().any(|block| {
                    matches!(
                        block,
                        ContentBlock::ToolResult {
                            tool_name,
                            is_error: false,
                            ..
                        } if matches!(tool_name.as_str(), "write_file" | "edit_file" | "bash" | "PowerShell")
                    )
                }) {
                    pending = false;
                }
            }
            crate::session::MessageRole::System | crate::session::MessageRole::Assistant => {}
        }
    }
    pending
}

fn tool_result_succeeded(message: &ConversationMessage) -> bool {
    message.blocks.iter().any(|block| {
        matches!(
            block,
            ContentBlock::ToolResult {
                is_error: false,
                ..
            }
        )
    })
}

fn flush_text_block(text: &mut String, blocks: &mut Vec<ContentBlock>) {
    if !text.is_empty() {
        blocks.push(ContentBlock::Text {
            text: std::mem::take(text),
        });
    }
}

fn format_hook_message(result: &HookRunResult, fallback: &str) -> String {
    if result.messages().is_empty() {
        fallback.to_string()
    } else {
        result.messages().join("\n")
    }
}

fn detect_completion_verify_command(workspace: &Path) -> Option<String> {
    let mut cur = workspace.to_path_buf();
    for _ in 0..4 {
        if cur.join("Cargo.toml").is_file() {
            return Some("cargo check".to_string());
        }
        if !cur.pop() {
            break;
        }
    }
    if workspace.join("pyproject.toml").is_file()
        || workspace.join("requirements.txt").is_file()
        || workspace.join("setup.py").is_file()
    {
        return Some("python -m pytest -q".to_string());
    }
    if dir_has_test_py(workspace) {
        return Some("python -m pytest -q".to_string());
    }
    if let Ok(pkg) = std::fs::read_to_string(workspace.join("package.json")) {
        if pkg.contains("\"scripts\"") && pkg.contains("\"test\"") {
            return Some("npm test --silent".to_string());
        }
    }
    None
}

fn dir_has_test_py(workspace: &Path) -> bool {
    let Ok(entries) = std::fs::read_dir(workspace) else {
        return false;
    };
    entries.filter_map(Result::ok).any(|entry| {
        let name = entry.file_name();
        let n = name.to_string_lossy();
        n.starts_with("test_") && n.ends_with(".py")
    })
}

/// Extract a (tool name, stable error signature) pair from a failed tool
/// result so consecutive identical failures can be counted. Returns `None`
/// for successful results. The signature is the first line of the error,
/// capped, so byte-identical retries match while different errors reset.
fn tool_failure_signature(message: &ConversationMessage) -> Option<(String, String)> {
    message.blocks.iter().find_map(|block| match block {
        ContentBlock::ToolResult {
            tool_name,
            output,
            is_error,
            ..
        } if *is_error => {
            let first_line = output.lines().next().unwrap_or_default();
            let mut signature = first_line.chars().take(160).collect::<String>();
            if signature.is_empty() {
                signature = String::from("(empty error)");
            }
            Some((tool_name.clone(), signature))
        }
        _ => None,
    })
}

fn extract_path_from_tool_payload(output: &str) -> Option<String> {
    let value = serde_json::from_str::<Value>(output).ok()?;
    let object = value.as_object()?;
    for key in ["path", "file_path", "filePath", "target_path", "targetPath"] {
        if let Some(path) = object.get(key).and_then(Value::as_str) {
            return Some(path.replace('\\', "/"));
        }
    }
    None
}

fn should_record_verification_command(command: &str) -> bool {
    let normalized = command
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_ascii_lowercase();
    normalized.contains("cargo test")
        || normalized.contains("cargo clippy")
        || normalized.contains("cargo check")
        || normalized.contains("pytest")
        || normalized.contains("npm test")
        || normalized.contains("pnpm test")
        || normalized.contains("yarn test")
        || normalized.contains("go test")
}

fn parse_task_ledger_update(input: &str) -> Result<SessionTaskLedgerUpdate, RuntimeError> {
    let value = serde_json::from_str::<Value>(input).map_err(|error| {
        RuntimeError::new(format!("invalid TaskLedgerUpdate input JSON: {error}"))
    })?;
    let object = value
        .as_object()
        .ok_or_else(|| RuntimeError::new("TaskLedgerUpdate input must be a JSON object"))?;
    Ok(SessionTaskLedgerUpdate {
        objective: object
            .get("objective")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        constraints: json_string_array(object.get("constraints")),
        decisions: json_string_array(object.get("decisions")),
        relevant_paths: json_string_array(object.get("relevant_paths")),
        changed_paths: json_string_array(object.get("changed_paths")),
        verification: json_string_array(object.get("verification")),
        next_steps: json_string_array(object.get("next_steps")),
        repo_snapshot_id: object
            .get("repo_snapshot_id")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
    })
}

fn json_string_array(value: Option<&Value>) -> Vec<String> {
    let Some(array) = value.and_then(Value::as_array) else {
        return Vec::new();
    };
    array
        .iter()
        .filter_map(Value::as_str)
        .map(ToOwned::to_owned)
        .collect()
}

fn merge_hook_feedback(messages: &[String], output: String, is_error: bool) -> String {
    if messages.is_empty() {
        return output;
    }

    let mut sections = Vec::new();
    if !output.trim().is_empty() {
        sections.push(output);
    }
    let label = if is_error {
        "Hook feedback (error)"
    } else {
        "Hook feedback"
    };
    sections.push(format!("{label}:\n{}", messages.join("\n")));
    sections.join("\n\n")
}

fn completion_verify_output_ok(output: &BashCommandOutput) -> bool {
    !output.interrupted && output.return_code_interpretation.is_none()
}

const MAX_COMPLETION_VERIFY_FEEDBACK: usize = 12_000;
const MAX_COMPLETION_VERIFY_STREAM: usize = 6_000;

fn format_completion_verify_feedback(command: &str, output: &BashCommandOutput) -> String {
    let mut body = String::from(
        "[Engine completion verification failed — the turn cannot finish until this passes.]\n\n\
         The configured verification command did not succeed (non-zero exit, error output, or timeout).\n\
         Fix the issue and ensure this command succeeds before stopping.\n\n\
         Command:\n```bash\n",
    );
    body.push_str(command);
    body.push_str("\n```\n\n--- stdout ---\n");
    body.push_str(&truncate_completion_stream(&output.stdout));
    body.push_str("\n\n--- stderr ---\n");
    body.push_str(&truncate_completion_stream(&output.stderr));
    if output.interrupted {
        body.push_str("\n\n(Verify command timed out.)\n");
    }
    if let Some(code) = &output.return_code_interpretation {
        let _ = write!(body, "\n({code})\n");
    }
    if body.len() > MAX_COMPLETION_VERIFY_FEEDBACK {
        body.truncate(MAX_COMPLETION_VERIFY_FEEDBACK);
        body.push_str("\n\n[truncated]");
    }
    body
}

fn truncate_completion_stream(s: &str) -> String {
    if s.len() <= MAX_COMPLETION_VERIFY_STREAM {
        return s.to_string();
    }
    let mut end = MAX_COMPLETION_VERIFY_STREAM;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    format!(
        "{}…\n[truncated {} bytes]",
        &s[..end],
        s.len().saturating_sub(end)
    )
}

type ToolHandler = Box<dyn FnMut(&str) -> Result<String, ToolError>>;

/// Simple in-memory tool executor for tests and lightweight integrations.
#[derive(Default)]
pub struct StaticToolExecutor {
    handlers: BTreeMap<String, ToolHandler>,
}

impl StaticToolExecutor {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn register(
        mut self,
        tool_name: impl Into<String>,
        handler: impl FnMut(&str) -> Result<String, ToolError> + 'static,
    ) -> Self {
        self.handlers.insert(tool_name.into(), Box::new(handler));
        self
    }
}

impl ToolExecutor for StaticToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError> {
        self.handlers
            .get_mut(tool_name)
            .ok_or_else(|| ToolError::new(format!("unknown tool: {tool_name}")))?(input)
    }
}

#[cfg(test)]
mod completion_verify_unit_tests {
    use super::{completion_verify_output_ok, format_completion_verify_feedback};
    use crate::bash::BashCommandOutput;

    #[test]
    fn completion_verify_ok_requires_clean_exit() {
        let ok = BashCommandOutput {
            stdout: "ok".into(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: None,
            backgrounded_by_user: None,
            assistant_auto_backgrounded: None,
            dangerously_disable_sandbox: None,
            return_code_interpretation: None,
            no_output_expected: None,
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: None,
        };
        assert!(completion_verify_output_ok(&ok));
        let bad = BashCommandOutput {
            stdout: "ok".into(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: None,
            backgrounded_by_user: None,
            assistant_auto_backgrounded: None,
            dangerously_disable_sandbox: None,
            return_code_interpretation: Some("exit_code:1".into()),
            no_output_expected: None,
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: None,
        };
        assert!(!completion_verify_output_ok(&bad));
        let timed = BashCommandOutput {
            stdout: "ok".into(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: true,
            is_image: None,
            background_task_id: None,
            backgrounded_by_user: None,
            assistant_auto_backgrounded: None,
            dangerously_disable_sandbox: None,
            return_code_interpretation: None,
            no_output_expected: None,
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: None,
        };
        assert!(!completion_verify_output_ok(&timed));
    }

    #[test]
    fn completion_verify_feedback_includes_command_snippet() {
        let out = BashCommandOutput {
            stdout: "a".into(),
            stderr: "b".into(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: None,
            backgrounded_by_user: None,
            assistant_auto_backgrounded: None,
            dangerously_disable_sandbox: None,
            return_code_interpretation: Some("exit_code:2".into()),
            no_output_expected: None,
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: None,
        };
        let msg = format_completion_verify_feedback("cargo check", &out);
        assert!(msg.contains("cargo check"));
        assert!(msg.contains("exit_code:2"));
        assert!(msg.contains("stdout"));
        assert!(msg.contains("stderr"));
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_assistant_message, parse_auto_compaction_threshold, recover_compat_text_tool_call,
        session_has_pending_filesystem_execution, tool_result_succeeded, ApiClient, ApiRequest,
        AssistantEvent, AutoCompactionEvent, ConversationRuntime, PromptCacheEvent, RuntimeError,
        StaticToolExecutor, ToolExecutor, DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD,
    };
    use crate::compact::CompactionConfig;
    use crate::config::{RuntimeFeatureConfig, RuntimeHookConfig};
    use crate::permissions::{
        PermissionMode, PermissionPolicy, PermissionPromptDecision, PermissionPrompter,
        PermissionRequest,
    };
    use crate::prompt::{ProjectContext, SystemPromptBuilder};
    use crate::session::{ContentBlock, MessageRole, Session};
    use crate::usage::TokenUsage;
    use crate::ToolError;
    use std::fs;
    use std::path::PathBuf;
    use std::sync::Arc;
    use std::time::{SystemTime, UNIX_EPOCH};
    use telemetry::{MemoryTelemetrySink, SessionTracer, TelemetryEvent};

    struct ScriptedApiClient {
        call_count: usize,
    }

    struct TextToolCompatApiClient {
        call_count: usize,
    }

    struct GuardedCompatApiClient {
        call_count: usize,
        first_response: &'static str,
    }

    struct FailedThenClaimedApiClient {
        call_count: usize,
    }

    impl ApiClient for TextToolCompatApiClient {
        fn stream(&mut self, _request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
            self.call_count += 1;
            let text = if self.call_count == 1 {
                r#"{"tool":"write_file","arguments":{"path":"D:/Proj 1/index.html","content":"ok"}}"#
            } else {
                "The file was created."
            };
            Ok(vec![
                AssistantEvent::TextDelta(text.to_string()),
                AssistantEvent::MessageStop,
            ])
        }
    }

    impl ApiClient for GuardedCompatApiClient {
        fn stream(&mut self, _request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
            self.call_count += 1;
            let text = match self.call_count {
                1 => self.first_response,
                2 => r#"{"tool":"write_file","arguments":{"path":"pacman.html","content":"game"}}"#,
                _ => "The verified file is ready.",
            };
            Ok(vec![
                AssistantEvent::TextDelta(text.to_string()),
                AssistantEvent::MessageStop,
            ])
        }
    }

    impl ApiClient for FailedThenClaimedApiClient {
        fn stream(&mut self, _request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
            self.call_count += 1;
            let text = match self.call_count {
                1 | 3 => {
                    r#"{"tool":"write_file","arguments":{"path":"pacman.html","content":"game"}}"#
                }
                2 => "The file has been created successfully.",
                _ => "The file is now verified.",
            };
            Ok(vec![
                AssistantEvent::TextDelta(text.to_string()),
                AssistantEvent::MessageStop,
            ])
        }
    }

    #[test]
    fn recovers_text_encoded_tool_call_for_affected_compat_model() {
        let mut message = crate::session::ConversationMessage::assistant(vec![
            ContentBlock::Text {
                text: r#"{"type":"tool","name":"write_file","arguments":{"path":"D:/Proj 1/index.html","content":"ok"}}"#.to_string(),
            },
        ]);

        assert!(recover_compat_text_tool_call(
            &mut message,
            Some("gpt-oss-120b"),
            2
        ));
        assert!(matches!(
            &message.blocks[0],
            ContentBlock::ToolUse { id, name, input }
                if id == "compat_text_tool_2"
                    && name == "write_file"
                    && input.contains("index.html")
        ));
    }

    #[test]
    fn recovers_cerebras_tool_arguments_envelope() {
        let mut message =
            crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                text:
                    r#"{"tool":"write_file","arguments":{"path":"pacman.html","content":"game"}}"#
                        .to_string(),
            }]);

        assert!(recover_compat_text_tool_call(
            &mut message,
            Some("gpt-oss-120b"),
            1
        ));
        assert!(matches!(
            &message.blocks[0],
            ContentBlock::ToolUse { name, input, .. }
                if name == "write_file" && input.contains("pacman.html")
        ));
    }

    #[test]
    fn recovers_singleton_tool_name_envelope() {
        let mut message =
            crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                text: r#"{"write_file":{"path":"D:/Proj 1/index.html","content":"game"}}"#
                    .to_string(),
            }]);

        assert!(recover_compat_text_tool_call(
            &mut message,
            Some("gpt-oss-120b"),
            1
        ));
        assert!(matches!(
            &message.blocks[0],
            ContentBlock::ToolUse { name, input, .. }
                if name == "write_file" && input.contains("D:/Proj 1/index.html")
        ));
    }

    #[test]
    fn recovers_fenced_and_string_encoded_compat_arguments() {
        let mut message = crate::session::ConversationMessage::assistant(vec![
            ContentBlock::Text {
                text: "```json\n{\"tool\":\"write_file\",\"arguments\":\"{\\\"path\\\":\\\"pacman.html\\\",\\\"content\\\":\\\"game\\\"}\"}\n```".to_string(),
            },
        ]);

        assert!(recover_compat_text_tool_call(
            &mut message,
            Some("gpt-oss-120b"),
            1
        ));
        assert!(matches!(
            &message.blocks[0],
            ContentBlock::ToolUse { name, input, .. }
                if name == "write_file" && input.contains("pacman.html")
        ));
    }

    #[test]
    fn recovers_raw_openai_function_envelope() {
        let mut message = crate::session::ConversationMessage::assistant(vec![
            ContentBlock::Text {
                text: r#"{"type":"function","function":{"name":"write_file","arguments":"{\"path\":\"pacman.html\",\"content\":\"game\"}"}}"#.to_string(),
            },
        ]);

        assert!(recover_compat_text_tool_call(
            &mut message,
            Some("gpt-oss-120b"),
            1
        ));
    }

    #[test]
    fn rejects_malformed_or_extra_field_compat_envelopes() {
        for text in [
            r#"{"tool":"write_file","arguments":{broken}"#,
            r#"{"tool":"write_file","arguments":{"path":"x"},"claim":"done"}"#,
            r#"{"tool":"write file","arguments":{"path":"x"}}"#,
            r#"{"tool":"write_file","arguments":"not-json"}"#,
        ] {
            let mut message =
                crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                    text: text.to_string(),
                }]);
            assert!(!recover_compat_text_tool_call(
                &mut message,
                Some("gpt-oss-120b"),
                1
            ));
        }
    }

    #[test]
    fn does_not_execute_text_tool_envelopes_from_unaffected_models_or_mixed_text() {
        let text = r#"{"type":"tool","name":"bash","arguments":{"command":"echo hi"}}"#;
        let mut unaffected =
            crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                text: text.to_string(),
            }]);
        assert!(!recover_compat_text_tool_call(
            &mut unaffected,
            Some("claude-sonnet-4-6"),
            1
        ));

        let mut mixed = crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
            text: format!("Here is an example:\n{text}"),
        }]);
        assert!(!recover_compat_text_tool_call(
            &mut mixed,
            Some("gpt-oss-120b"),
            1
        ));
    }

    #[test]
    fn compat_text_tool_call_executes_through_normal_permission_and_tool_loop() {
        let observed = Arc::new(std::sync::Mutex::new(Vec::new()));
        let observed_by_tool = observed.clone();
        let executor = StaticToolExecutor::new().register("write_file", move |input| {
            observed_by_tool
                .lock()
                .expect("observed input lock")
                .push(input.to_string());
            Ok("created".to_string())
        });
        let mut session = Session::new();
        session.model = Some("gpt-oss-120b".to_string());
        let mut runtime = ConversationRuntime::new(
            session,
            TextToolCompatApiClient { call_count: 0 },
            executor,
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        let summary = runtime
            .run_turn("create the file", None)
            .expect("compat tool call should execute");

        assert_eq!(summary.iterations, 2);
        assert_eq!(summary.tool_results.len(), 1);
        let observed = observed.lock().expect("observed input lock");
        assert_eq!(observed.len(), 1);
        assert!(observed[0].contains("D:/Proj 1/index.html"));
    }

    fn run_guarded_compat_scenario(first_response: &'static str) -> (usize, usize) {
        let executor =
            StaticToolExecutor::new().register("write_file", |_input| Ok("created".to_string()));
        let mut session = Session::new();
        session.model = Some("gpt-oss-120b".to_string());
        let mut runtime = ConversationRuntime::new(
            session,
            GuardedCompatApiClient {
                call_count: 0,
                first_response,
            },
            executor,
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );
        let summary = runtime
            .run_turn("build a pacman game in an html", None)
            .expect("guarded scenario should recover");
        (summary.iterations, summary.tool_results.len())
    }

    #[test]
    fn malformed_compat_tool_call_is_nudged_instead_of_treated_as_completion() {
        let (iterations, tool_results) = run_guarded_compat_scenario(
            r#"{"tool":"write_file","arguments":{"path":"pacman.html",broken}}"#,
        );
        assert_eq!(iterations, 3);
        assert_eq!(tool_results, 1);
    }

    #[test]
    fn unsupported_filesystem_success_claim_is_nudged_until_tool_evidence_exists() {
        let (iterations, tool_results) =
            run_guarded_compat_scenario("The file has been created and the game is complete.");
        assert_eq!(iterations, 3);
        assert_eq!(tool_results, 1);
    }

    #[test]
    fn code_only_response_to_build_request_is_nudged_into_tool_execution() {
        let (iterations, tool_results) = run_guarded_compat_scenario(
            "Here are the three file contents. Run write_file for each JSON block.",
        );
        assert_eq!(iterations, 3);
        assert_eq!(tool_results, 1);
    }

    #[test]
    fn pending_filesystem_execution_survives_follow_up_questions_until_write_succeeds() {
        let mut session = Session::new();
        session
            .push_user_text("build a pacman game in an html")
            .expect("user message");
        session
            .push_message(crate::session::ConversationMessage::assistant(vec![
                ContentBlock::Text {
                    text: "Here is the code; use write_file.".to_string(),
                },
            ]))
            .expect("assistant message");
        session
            .push_user_text("where is it located?")
            .expect("follow-up");
        assert!(session_has_pending_filesystem_execution(&session));

        session
            .push_message(crate::session::ConversationMessage::tool_result(
                "tool-1",
                "write_file",
                "created",
                false,
            ))
            .expect("tool result");
        assert!(!session_has_pending_filesystem_execution(&session));
    }

    #[test]
    fn failed_tool_result_does_not_count_as_success_evidence() {
        let mut attempts = 0_u8;
        let executor = StaticToolExecutor::new().register("write_file", move |_input| {
            attempts = attempts.saturating_add(1);
            if attempts == 1 {
                Err(ToolError::new("simulated write failure"))
            } else {
                Ok("created".to_string())
            }
        });
        let mut session = Session::new();
        session.model = Some("gpt-oss-120b".to_string());
        let mut runtime = ConversationRuntime::new(
            session,
            FailedThenClaimedApiClient { call_count: 0 },
            executor,
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        let summary = runtime
            .run_turn("build a pacman game in an html", None)
            .expect("second write should recover");

        assert_eq!(summary.iterations, 4);
        assert_eq!(summary.tool_results.len(), 2);
        assert!(tool_result_succeeded(
            summary.tool_results.last().expect("successful result")
        ));
    }

    impl ApiClient for ScriptedApiClient {
        fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
            self.call_count += 1;
            match self.call_count {
                1 => {
                    assert!(request
                        .messages
                        .iter()
                        .any(|message| message.role == MessageRole::User));
                    Ok(vec![
                        AssistantEvent::TextDelta("Let me calculate that.".to_string()),
                        AssistantEvent::ToolUse {
                            id: "tool-1".to_string(),
                            name: "add".to_string(),
                            input: "2,2".to_string(),
                        },
                        AssistantEvent::Usage(TokenUsage {
                            input_tokens: 20,
                            output_tokens: 6,
                            cache_creation_input_tokens: 1,
                            cache_read_input_tokens: 2,
                        }),
                        AssistantEvent::MessageStop,
                    ])
                }
                2 => {
                    let last_message = request
                        .messages
                        .last()
                        .expect("tool result should be present");
                    assert_eq!(last_message.role, MessageRole::Tool);
                    Ok(vec![
                        AssistantEvent::TextDelta("The answer is 4.".to_string()),
                        AssistantEvent::Usage(TokenUsage {
                            input_tokens: 24,
                            output_tokens: 4,
                            cache_creation_input_tokens: 1,
                            cache_read_input_tokens: 3,
                        }),
                        AssistantEvent::PromptCache(PromptCacheEvent {
                            unexpected: true,
                            reason:
                                "cache read tokens dropped while prompt fingerprint remained stable"
                                    .to_string(),
                            previous_cache_read_input_tokens: 6_000,
                            current_cache_read_input_tokens: 1_000,
                            token_drop: 5_000,
                        }),
                        AssistantEvent::MessageStop,
                    ])
                }
                _ => unreachable!("extra API call"),
            }
        }
    }

    struct PromptAllowOnce;

    impl PermissionPrompter for PromptAllowOnce {
        fn decide(&mut self, request: &PermissionRequest) -> PermissionPromptDecision {
            assert_eq!(request.tool_name, "add");
            PermissionPromptDecision::Allow
        }
    }

    #[test]
    fn runs_user_to_tool_to_result_loop_end_to_end_and_tracks_usage() {
        let api_client = ScriptedApiClient { call_count: 0 };
        let tool_executor = StaticToolExecutor::new().register("add", |input| {
            let total = input
                .split(',')
                .map(|part| part.parse::<i32>().expect("input must be valid integer"))
                .sum::<i32>();
            Ok(total.to_string())
        });
        let permission_policy = PermissionPolicy::new(PermissionMode::WorkspaceWrite);
        let system_prompt = SystemPromptBuilder::new()
            .with_project_context(ProjectContext {
                cwd: PathBuf::from("/tmp/project"),
                current_date: "2026-03-31".to_string(),
                git_status: None,
                git_diff: None,
                git_context: None,
                instruction_files: Vec::new(),
            })
            .with_os("linux", "6.8")
            .build();
        let mut runtime = ConversationRuntime::new(
            Session::new(),
            api_client,
            tool_executor,
            permission_policy,
            system_prompt,
        );

        let summary = runtime
            .run_turn("what is 2 + 2?", Some(&mut PromptAllowOnce))
            .expect("conversation loop should succeed");

        assert_eq!(summary.iterations, 2);
        assert_eq!(summary.assistant_messages.len(), 2);
        assert_eq!(summary.tool_results.len(), 1);
        assert_eq!(summary.prompt_cache_events.len(), 1);
        assert_eq!(runtime.session().messages.len(), 4);
        assert_eq!(summary.usage.output_tokens, 10);
        assert_eq!(summary.auto_compaction, None);
        assert!(matches!(
            runtime.session().messages[1].blocks[1],
            ContentBlock::ToolUse { .. }
        ));
        assert!(matches!(
            runtime.session().messages[2].blocks[0],
            ContentBlock::ToolResult {
                is_error: false,
                ..
            }
        ));
    }

    #[test]
    fn records_runtime_session_trace_events() {
        let sink = Arc::new(MemoryTelemetrySink::default());
        let tracer = SessionTracer::new("session-runtime", sink.clone());
        let mut runtime = ConversationRuntime::new(
            Session::new(),
            ScriptedApiClient { call_count: 0 },
            StaticToolExecutor::new().register("add", |_input| Ok("4".to_string())),
            PermissionPolicy::new(PermissionMode::WorkspaceWrite),
            vec!["system".to_string()],
        )
        .with_session_tracer(tracer);

        runtime
            .run_turn("what is 2 + 2?", Some(&mut PromptAllowOnce))
            .expect("conversation loop should succeed");

        let events = sink.events();
        let trace_names = events
            .iter()
            .filter_map(|event| match event {
                TelemetryEvent::SessionTrace(trace) => Some(trace.name.as_str()),
                _ => None,
            })
            .collect::<Vec<_>>();

        assert!(trace_names.contains(&"turn_started"));
        assert!(trace_names.contains(&"assistant_iteration_completed"));
        assert!(trace_names.contains(&"tool_execution_started"));
        assert!(trace_names.contains(&"tool_execution_finished"));
        assert!(trace_names.contains(&"turn_completed"));
    }

    #[test]
    fn records_denied_tool_results_when_prompt_rejects() {
        struct RejectPrompter;
        impl PermissionPrompter for RejectPrompter {
            fn decide(&mut self, _request: &PermissionRequest) -> PermissionPromptDecision {
                PermissionPromptDecision::Deny {
                    reason: "not now".to_string(),
                }
            }
        }

        struct SingleCallApiClient;
        impl ApiClient for SingleCallApiClient {
            fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
                if request
                    .messages
                    .iter()
                    .any(|message| message.role == MessageRole::Tool)
                {
                    return Ok(vec![
                        AssistantEvent::TextDelta("I could not use the tool.".to_string()),
                        AssistantEvent::MessageStop,
                    ]);
                }
                Ok(vec![
                    AssistantEvent::ToolUse {
                        id: "tool-1".to_string(),
                        name: "blocked".to_string(),
                        input: "secret".to_string(),
                    },
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut runtime = ConversationRuntime::new(
            Session::new(),
            SingleCallApiClient,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::WorkspaceWrite),
            vec!["system".to_string()],
        );

        let summary = runtime
            .run_turn("use the tool", Some(&mut RejectPrompter))
            .expect("conversation should continue after denied tool");

        assert_eq!(summary.tool_results.len(), 1);
        assert!(matches!(
            &summary.tool_results[0].blocks[0],
            ContentBlock::ToolResult { is_error: true, output, .. } if output == "not now"
        ));
    }

    #[test]
    fn denies_tool_use_when_pre_tool_hook_blocks() {
        struct SingleCallApiClient;
        impl ApiClient for SingleCallApiClient {
            fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
                if request
                    .messages
                    .iter()
                    .any(|message| message.role == MessageRole::Tool)
                {
                    return Ok(vec![
                        AssistantEvent::TextDelta("blocked".to_string()),
                        AssistantEvent::MessageStop,
                    ]);
                }
                Ok(vec![
                    AssistantEvent::ToolUse {
                        id: "tool-1".to_string(),
                        name: "blocked".to_string(),
                        input: r#"{"path":"secret.txt"}"#.to_string(),
                    },
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut runtime = ConversationRuntime::new_with_features(
            Session::new(),
            SingleCallApiClient,
            StaticToolExecutor::new().register("blocked", |_input| {
                panic!("tool should not execute when hook denies")
            }),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
            &RuntimeFeatureConfig::default().with_hooks(RuntimeHookConfig::new(
                vec![shell_snippet("printf 'blocked by hook'; exit 2")],
                Vec::new(),
                Vec::new(),
            )),
        );

        let summary = runtime
            .run_turn("use the tool", None)
            .expect("conversation should continue after hook denial");

        assert_eq!(summary.tool_results.len(), 1);
        let ContentBlock::ToolResult {
            is_error, output, ..
        } = &summary.tool_results[0].blocks[0]
        else {
            panic!("expected tool result block");
        };
        assert!(
            *is_error,
            "hook denial should produce an error result: {output}"
        );
        assert!(
            output.contains("denied tool") || output.contains("blocked by hook"),
            "unexpected hook denial output: {output:?}"
        );
    }

    #[test]
    fn denies_tool_use_when_pre_tool_hook_fails() {
        struct SingleCallApiClient;
        impl ApiClient for SingleCallApiClient {
            fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
                if request
                    .messages
                    .iter()
                    .any(|message| message.role == MessageRole::Tool)
                {
                    return Ok(vec![
                        AssistantEvent::TextDelta("failed".to_string()),
                        AssistantEvent::MessageStop,
                    ]);
                }
                Ok(vec![
                    AssistantEvent::ToolUse {
                        id: "tool-1".to_string(),
                        name: "blocked".to_string(),
                        input: r#"{"path":"secret.txt"}"#.to_string(),
                    },
                    AssistantEvent::MessageStop,
                ])
            }
        }

        // given
        let mut runtime = ConversationRuntime::new_with_features(
            Session::new(),
            SingleCallApiClient,
            StaticToolExecutor::new().register("blocked", |_input| {
                panic!("tool should not execute when hook fails")
            }),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
            &RuntimeFeatureConfig::default().with_hooks(RuntimeHookConfig::new(
                vec![shell_snippet("printf 'broken hook'; exit 1")],
                Vec::new(),
                Vec::new(),
            )),
        );

        // when
        let summary = runtime
            .run_turn("use the tool", None)
            .expect("conversation should continue after hook failure");

        // then
        assert_eq!(summary.tool_results.len(), 1);
        let ContentBlock::ToolResult {
            is_error, output, ..
        } = &summary.tool_results[0].blocks[0]
        else {
            panic!("expected tool result block");
        };
        assert!(
            *is_error,
            "hook failure should produce an error result: {output}"
        );
        assert!(
            output.contains("exited with status 1") || output.contains("broken hook"),
            "unexpected hook failure output: {output:?}"
        );
    }

    #[test]
    #[cfg_attr(windows, ignore = "requires POSIX-compatible shell hook fixture")]
    fn appends_post_tool_hook_feedback_to_tool_result() {
        struct TwoCallApiClient {
            calls: usize,
        }

        impl ApiClient for TwoCallApiClient {
            fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
                self.calls += 1;
                match self.calls {
                    1 => Ok(vec![
                        AssistantEvent::ToolUse {
                            id: "tool-1".to_string(),
                            name: "add".to_string(),
                            input: r#"{"lhs":2,"rhs":2}"#.to_string(),
                        },
                        AssistantEvent::MessageStop,
                    ]),
                    2 => {
                        assert!(request
                            .messages
                            .iter()
                            .any(|message| message.role == MessageRole::Tool));
                        Ok(vec![
                            AssistantEvent::TextDelta("done".to_string()),
                            AssistantEvent::MessageStop,
                        ])
                    }
                    _ => unreachable!("extra API call"),
                }
            }
        }

        let mut runtime = ConversationRuntime::new_with_features(
            Session::new(),
            TwoCallApiClient { calls: 0 },
            StaticToolExecutor::new().register("add", |_input| Ok("4".to_string())),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
            &RuntimeFeatureConfig::default().with_hooks(RuntimeHookConfig::new(
                vec![shell_snippet("printf 'pre hook ran'")],
                vec![shell_snippet("printf 'post hook ran'")],
                Vec::new(),
            )),
        );

        let summary = runtime
            .run_turn("use add", None)
            .expect("tool loop succeeds");

        assert_eq!(summary.tool_results.len(), 1);
        let ContentBlock::ToolResult {
            is_error, output, ..
        } = &summary.tool_results[0].blocks[0]
        else {
            panic!("expected tool result block");
        };
        assert!(
            !*is_error,
            "post hook should preserve non-error result: {output:?}"
        );
        assert!(
            output.contains('4'),
            "tool output missing value: {output:?}"
        );
        assert!(
            output.contains("pre hook ran"),
            "tool output missing pre hook feedback: {output:?}"
        );
        assert!(
            output.contains("post hook ran"),
            "tool output missing post hook feedback: {output:?}"
        );
    }

    #[test]
    fn appends_post_tool_use_failure_hook_feedback_to_tool_result() {
        struct TwoCallApiClient {
            calls: usize,
        }

        impl ApiClient for TwoCallApiClient {
            fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError> {
                self.calls += 1;
                match self.calls {
                    1 => Ok(vec![
                        AssistantEvent::ToolUse {
                            id: "tool-1".to_string(),
                            name: "fail".to_string(),
                            input: r#"{"path":"README.md"}"#.to_string(),
                        },
                        AssistantEvent::MessageStop,
                    ]),
                    2 => {
                        assert!(request
                            .messages
                            .iter()
                            .any(|message| message.role == MessageRole::Tool));
                        Ok(vec![
                            AssistantEvent::TextDelta("done".to_string()),
                            AssistantEvent::MessageStop,
                        ])
                    }
                    _ => unreachable!("extra API call"),
                }
            }
        }

        // given
        let mut runtime = ConversationRuntime::new_with_features(
            Session::new(),
            TwoCallApiClient { calls: 0 },
            StaticToolExecutor::new()
                .register("fail", |_input| Err(ToolError::new("tool exploded"))),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
            &RuntimeFeatureConfig::default().with_hooks(RuntimeHookConfig::new(
                Vec::new(),
                vec![shell_snippet("printf 'post hook should not run'")],
                vec![shell_snippet("printf 'failure hook ran'")],
            )),
        );

        // when
        let summary = runtime
            .run_turn("use fail", None)
            .expect("tool loop succeeds");

        // then
        assert_eq!(summary.tool_results.len(), 1);
        let ContentBlock::ToolResult {
            is_error, output, ..
        } = &summary.tool_results[0].blocks[0]
        else {
            panic!("expected tool result block");
        };
        assert!(
            *is_error,
            "failure hook path should preserve error result: {output:?}"
        );
        assert!(
            output.contains("tool exploded"),
            "tool output missing failure reason: {output:?}"
        );
        assert!(
            output.contains("failure hook ran"),
            "tool output missing failure hook feedback: {output:?}"
        );
        assert!(
            !output.contains("post hook should not run"),
            "normal post hook should not run on tool failure: {output:?}"
        );
    }

    #[test]
    fn reconstructs_usage_tracker_from_restored_session() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut session = Session::new();
        session
            .messages
            .push(crate::session::ConversationMessage::assistant_with_usage(
                vec![ContentBlock::Text {
                    text: "earlier".to_string(),
                }],
                Some(TokenUsage {
                    input_tokens: 11,
                    output_tokens: 7,
                    cache_creation_input_tokens: 2,
                    cache_read_input_tokens: 1,
                }),
            ));

        let runtime = ConversationRuntime::new(
            session,
            SimpleApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        assert_eq!(runtime.usage().turns(), 1);
        assert_eq!(runtime.usage().cumulative_usage().total_tokens(), 21);
    }

    #[test]
    fn compacts_session_after_turns() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut runtime = ConversationRuntime::new(
            Session::new(),
            SimpleApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );
        runtime.run_turn("a", None).expect("turn a");
        runtime.run_turn("b", None).expect("turn b");
        runtime.run_turn("c", None).expect("turn c");

        let result = runtime.compact(CompactionConfig {
            preserve_recent_messages: 2,
            max_estimated_tokens: 1,
        });
        assert!(result.summary.contains("Conversation summary"));
        assert_eq!(
            result.compacted_session.messages[0].role,
            MessageRole::System
        );
        assert_eq!(
            result.compacted_session.session_id,
            runtime.session().session_id
        );
        assert!(result.compacted_session.compaction.is_some());
    }

    #[test]
    fn persists_conversation_turn_messages_to_jsonl_session() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let path = temp_session_path("persisted-turn");
        let session = Session::new().with_persistence_path(path.clone());
        let mut runtime = ConversationRuntime::new(
            session,
            SimpleApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        runtime
            .run_turn("persist this turn", None)
            .expect("turn should succeed");

        let restored = Session::load_from_path(&path).expect("persisted session should reload");
        fs::remove_file(&path).expect("temp session file should be removable");

        assert_eq!(restored.messages.len(), 2);
        assert_eq!(restored.messages[0].role, MessageRole::User);
        assert_eq!(restored.messages[1].role, MessageRole::Assistant);
        assert_eq!(restored.session_id, runtime.session().session_id);
    }

    #[test]
    fn forks_runtime_session_without_mutating_original() {
        let mut session = Session::new();
        session
            .push_user_text("branch me")
            .expect("message should append");

        let runtime = ConversationRuntime::new(
            session.clone(),
            ScriptedApiClient { call_count: 0 },
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        let forked = runtime.fork_session(Some("alt-path".to_string()));

        assert_eq!(forked.messages, session.messages);
        assert_ne!(forked.session_id, session.session_id);
        assert_eq!(
            forked
                .fork
                .as_ref()
                .map(|fork| (fork.parent_session_id.as_str(), fork.branch_name.as_deref())),
            Some((session.session_id.as_str(), Some("alt-path")))
        );
        assert!(runtime.session().fork.is_none());
    }

    fn temp_session_path(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("runtime-conversation-{label}-{nanos}.json"))
    }

    #[cfg(windows)]
    fn shell_snippet(script: &str) -> String {
        script.replace('\'', "\"")
    }

    #[cfg(not(windows))]
    fn shell_snippet(script: &str) -> String {
        script.to_string()
    }

    #[test]
    fn auto_compacts_when_cumulative_input_threshold_is_crossed() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::Usage(TokenUsage {
                        input_tokens: 120_000,
                        output_tokens: 4,
                        cache_creation_input_tokens: 0,
                        cache_read_input_tokens: 0,
                    }),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut session = Session::new();
        session.messages = vec![
            crate::session::ConversationMessage::user_text("one"),
            crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                text: "two".to_string(),
            }]),
            crate::session::ConversationMessage::user_text("three"),
            crate::session::ConversationMessage::assistant(vec![ContentBlock::Text {
                text: "four".to_string(),
            }]),
        ];

        let mut runtime = ConversationRuntime::new(
            session,
            SimpleApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        )
        .with_auto_compaction_input_tokens_threshold(100_000);

        let summary = runtime
            .run_turn("trigger", None)
            .expect("turn should succeed");

        assert_eq!(
            summary.auto_compaction,
            Some(AutoCompactionEvent {
                removed_message_count: 2,
            })
        );
        assert_eq!(runtime.session().messages[0].role, MessageRole::System);
    }

    #[test]
    fn skips_auto_compaction_below_threshold() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::Usage(TokenUsage {
                        input_tokens: 99_999,
                        output_tokens: 4,
                        cache_creation_input_tokens: 0,
                        cache_read_input_tokens: 0,
                    }),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut runtime = ConversationRuntime::new(
            Session::new(),
            SimpleApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        )
        .with_auto_compaction_input_tokens_threshold(100_000);

        let summary = runtime
            .run_turn("trigger", None)
            .expect("turn should succeed");
        assert_eq!(summary.auto_compaction, None);
        assert_eq!(runtime.session().messages.len(), 2);
    }

    #[test]
    fn auto_compaction_threshold_defaults_and_parses_values() {
        assert_eq!(
            parse_auto_compaction_threshold(None),
            DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD
        );
        assert_eq!(parse_auto_compaction_threshold(Some("4321")), 4321);
        assert_eq!(
            parse_auto_compaction_threshold(Some("0")),
            DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD
        );
        assert_eq!(
            parse_auto_compaction_threshold(Some("not-a-number")),
            DEFAULT_AUTO_COMPACTION_INPUT_TOKENS_THRESHOLD
        );
    }

    #[test]
    fn detect_completion_verify_command_finds_cargo_in_parent() {
        let ws = std::env::temp_dir().join(format!("cv-cargo-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&ws);
        std::fs::create_dir_all(ws.join("nested")).unwrap();
        std::fs::write(
            ws.join("Cargo.toml"),
            "[package]\nname = \"x\"\nversion = \"0.1.0\"\n",
        )
        .unwrap();
        assert_eq!(
            super::detect_completion_verify_command(&ws.join("nested")).as_deref(),
            Some("cargo check")
        );
        let _ = std::fs::remove_dir_all(&ws);
    }

    #[test]
    fn detect_completion_verify_command_python_via_requirements() {
        let ws = std::env::temp_dir().join(format!("cv-req-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&ws);
        std::fs::create_dir_all(&ws).unwrap();
        std::fs::write(ws.join("requirements.txt"), "flask\n").unwrap();
        assert_eq!(
            super::detect_completion_verify_command(&ws).as_deref(),
            Some("python -m pytest -q")
        );
        let _ = std::fs::remove_dir_all(&ws);
    }

    #[test]
    fn compaction_health_probe_blocks_turn_when_tool_executor_is_broken() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                panic!("API should not run when health probe fails");
            }
        }

        let mut session = Session::new();
        session.record_compaction("summarized earlier work", 4);
        session
            .push_user_text("previous message")
            .expect("message should append");

        let tool_executor = StaticToolExecutor::new().register("glob_search", |_input| {
            Err(ToolError::new("transport unavailable"))
        });
        let mut runtime = ConversationRuntime::new(
            session,
            SimpleApi,
            tool_executor,
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        let error = runtime
            .run_turn("trigger", None)
            .expect_err("health probe failure should abort the turn");
        assert!(
            error
                .to_string()
                .contains("Session health probe failed after compaction"),
            "unexpected error: {error}"
        );
        assert!(
            error.to_string().contains("transport unavailable"),
            "expected underlying probe error: {error}"
        );
    }

    #[test]
    fn compaction_health_probe_skips_empty_compacted_session() {
        struct SimpleApi;
        impl ApiClient for SimpleApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::TextDelta("done".to_string()),
                    AssistantEvent::MessageStop,
                ])
            }
        }

        let mut session = Session::new();
        session.record_compaction("fresh summary", 2);

        let tool_executor = StaticToolExecutor::new().register("glob_search", |_input| {
            Err(ToolError::new(
                "glob_search should not run for an empty compacted session",
            ))
        });
        let mut runtime = ConversationRuntime::new(
            session,
            SimpleApi,
            tool_executor,
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        let summary = runtime
            .run_turn("trigger", None)
            .expect("empty compacted session should not fail health probe");
        assert_eq!(summary.auto_compaction, None);
        assert_eq!(runtime.session().messages.len(), 2);
    }

    #[test]
    fn build_assistant_message_requires_message_stop_event() {
        // given
        let events = vec![AssistantEvent::TextDelta("hello".to_string())];

        // when
        let error = build_assistant_message(events)
            .expect_err("assistant messages should require a stop event");

        // then
        assert!(error
            .to_string()
            .contains("assistant stream ended without a message stop event"));
    }

    #[test]
    fn build_assistant_message_requires_content() {
        // given
        let events = vec![AssistantEvent::MessageStop];

        // when
        let error =
            build_assistant_message(events).expect_err("assistant messages should require content");

        // then
        assert!(error
            .to_string()
            .contains("assistant stream produced no content"));
    }

    #[test]
    fn static_tool_executor_rejects_unknown_tools() {
        // given
        let mut executor = StaticToolExecutor::new();

        // when
        let error = executor
            .execute("missing", "{}")
            .expect_err("unregistered tools should fail");

        // then
        assert_eq!(error.to_string(), "unknown tool: missing");
    }

    #[test]
    fn run_turn_errors_when_max_iterations_is_exceeded() {
        struct LoopingApi;

        impl ApiClient for LoopingApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Ok(vec![
                    AssistantEvent::ToolUse {
                        id: "tool-1".to_string(),
                        name: "echo".to_string(),
                        input: "payload".to_string(),
                    },
                    AssistantEvent::MessageStop,
                ])
            }
        }

        // given
        let mut runtime = ConversationRuntime::new(
            Session::new(),
            LoopingApi,
            StaticToolExecutor::new().register("echo", |input| Ok(input.to_string())),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        )
        .with_max_iterations(1);

        // when
        let error = runtime
            .run_turn("loop", None)
            .expect_err("conversation loop should stop after the configured limit");

        // then
        assert!(error
            .to_string()
            .contains("conversation loop exceeded the maximum number of iterations"));
    }

    #[test]
    fn run_turn_propagates_api_errors() {
        struct FailingApi;

        impl ApiClient for FailingApi {
            fn stream(
                &mut self,
                _request: ApiRequest,
            ) -> Result<Vec<AssistantEvent>, RuntimeError> {
                Err(RuntimeError::new("upstream failed"))
            }
        }

        // given
        let mut runtime = ConversationRuntime::new(
            Session::new(),
            FailingApi,
            StaticToolExecutor::new(),
            PermissionPolicy::new(PermissionMode::DangerFullAccess),
            vec!["system".to_string()],
        );

        // when
        let error = runtime
            .run_turn("hello", None)
            .expect_err("API failures should propagate");

        // then
        assert_eq!(error.to_string(), "upstream failed");
    }
}
