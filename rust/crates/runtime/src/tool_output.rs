//! Truncate tool result payloads before they are appended to the session transcript.

/// Truncate UTF-8 `text` to at most `max_bytes`, appending a short marker when trimmed.
#[must_use]
pub fn truncate_tool_output(text: &str, max_bytes: usize) -> String {
    if text.len() <= max_bytes {
        return text.to_string();
    }
    let mut end = max_bytes;
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    let mut out = text[..end].to_string();
    out.push_str("\n\n[tool output truncated]");
    out
}

/// Per-tool max JSON/text payload size for session persistence (bytes).
#[must_use]
pub fn tool_result_truncation_limit(tool_name: &str) -> Option<usize> {
    match tool_name {
        "WebSearch" => Some(8_192),
        "WebFetch" => Some(24_576),
        "TodoWrite" => Some(2_048),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_under_limit_is_unchanged() {
        assert_eq!(truncate_tool_output("hello", 10), "hello");
    }

    #[test]
    fn truncate_adds_marker() {
        let s = "x".repeat(100);
        let out = truncate_tool_output(&s, 20);
        assert!(out.len() < s.len());
        assert!(out.ends_with("[tool output truncated]"));
    }
}
