use serde::{Deserialize, Serialize};

pub const MAX_SSE_PENDING_LINE_BYTES: usize = 64 * 1024;
pub const MAX_SSE_EVENT_DATA_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SseEvent {
    pub event: Option<String>,
    pub data: String,
    pub id: Option<String>,
    pub retry: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SseParseError {
    message: String,
}

impl SseParseError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for SseParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for SseParseError {}

#[derive(Debug, Clone, Default)]
pub struct IncrementalSseParser {
    buffer: String,
    event_name: Option<String>,
    data_lines: Vec<String>,
    data_bytes: usize,
    id: Option<String>,
    retry: Option<u64>,
}

impl IncrementalSseParser {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push_chunk(&mut self, chunk: &str) -> Result<Vec<SseEvent>, SseParseError> {
        self.buffer.push_str(chunk);
        if self.buffer.len() > MAX_SSE_PENDING_LINE_BYTES && !self.buffer.contains('\n') {
            self.reset();
            return Err(SseParseError::new(format!(
                "SSE line exceeded maximum length of {MAX_SSE_PENDING_LINE_BYTES} bytes"
            )));
        }

        let mut events = Vec::new();

        while let Some(index) = self.buffer.find('\n') {
            let mut line = self.buffer.drain(..=index).collect::<String>();
            if line.ends_with('\n') {
                line.pop();
            }
            if line.ends_with('\r') {
                line.pop();
            }
            self.process_line(&line, &mut events)?;
        }

        Ok(events)
    }

    pub fn finish(&mut self) -> Result<Vec<SseEvent>, SseParseError> {
        let mut events = Vec::new();
        if !self.buffer.is_empty() {
            let line = std::mem::take(&mut self.buffer);
            self.process_line(line.trim_end_matches('\r'), &mut events)?;
        }
        if let Some(event) = self.take_event() {
            events.push(event);
        }
        Ok(events)
    }

    fn process_line(
        &mut self,
        line: &str,
        events: &mut Vec<SseEvent>,
    ) -> Result<(), SseParseError> {
        if line.is_empty() {
            if let Some(event) = self.take_event() {
                events.push(event);
            }
            return Ok(());
        }

        if line.starts_with(':') {
            return Ok(());
        }

        let (field, value) = line.split_once(':').map_or((line, ""), |(field, value)| {
            let trimmed = value.strip_prefix(' ').unwrap_or(value);
            (field, trimmed)
        });

        match field {
            "event" => self.event_name = Some(value.to_owned()),
            "data" => self.push_data_line(value)?,
            "id" => self.id = Some(value.to_owned()),
            "retry" => self.retry = value.parse::<u64>().ok(),
            _ => {}
        }
        Ok(())
    }

    fn push_data_line(&mut self, value: &str) -> Result<(), SseParseError> {
        let separator = usize::from(!self.data_lines.is_empty());
        let next_bytes = self
            .data_bytes
            .saturating_add(separator)
            .saturating_add(value.len());
        if next_bytes > MAX_SSE_EVENT_DATA_BYTES {
            self.reset();
            return Err(SseParseError::new(format!(
                "SSE event data exceeded maximum length of {MAX_SSE_EVENT_DATA_BYTES} bytes"
            )));
        }
        self.data_bytes = next_bytes;
        self.data_lines.push(value.to_owned());
        Ok(())
    }

    fn take_event(&mut self) -> Option<SseEvent> {
        if self.data_lines.is_empty()
            && self.event_name.is_none()
            && self.id.is_none()
            && self.retry.is_none()
        {
            return None;
        }

        let data = self.data_lines.join("\n");
        self.data_lines.clear();
        self.data_bytes = 0;

        Some(SseEvent {
            event: self.event_name.take(),
            data,
            id: self.id.take(),
            retry: self.retry.take(),
        })
    }

    fn reset(&mut self) {
        self.buffer.clear();
        self.event_name = None;
        self.data_lines.clear();
        self.data_bytes = 0;
        self.id = None;
        self.retry = None;
    }
}

#[cfg(test)]
mod tests {
    use super::{
        IncrementalSseParser, SseEvent, MAX_SSE_EVENT_DATA_BYTES, MAX_SSE_PENDING_LINE_BYTES,
    };

    #[test]
    fn parses_streaming_events() {
        // given
        let mut parser = IncrementalSseParser::new();

        // when
        let first = parser
            .push_chunk("event: message\ndata: hel")
            .expect("partial event");

        // then
        assert!(first.is_empty());

        let second = parser
            .push_chunk("lo\n\nid: 1\ndata: world\n\n")
            .expect("completed events");
        assert_eq!(
            second,
            vec![
                SseEvent {
                    event: Some(String::from("message")),
                    data: String::from("hello"),
                    id: None,
                    retry: None,
                },
                SseEvent {
                    event: None,
                    data: String::from("world"),
                    id: Some(String::from("1")),
                    retry: None,
                },
            ]
        );
    }

    #[test]
    fn finish_flushes_a_trailing_event_without_separator() {
        // given
        let mut parser = IncrementalSseParser::new();
        parser
            .push_chunk("event: message\ndata: trailing")
            .expect("trailing event");

        // when
        let events = parser.finish().expect("finish");

        // then
        assert_eq!(
            events,
            vec![SseEvent {
                event: Some("message".to_string()),
                data: "trailing".to_string(),
                id: None,
                retry: None,
            }]
        );
    }

    #[test]
    fn rejects_line_without_newline_after_limit() {
        let mut parser = IncrementalSseParser::new();
        let error = parser
            .push_chunk(&"x".repeat(MAX_SSE_PENDING_LINE_BYTES + 1))
            .expect_err("oversized line should fail");

        assert!(error.to_string().contains("SSE line exceeded"));
    }

    #[test]
    fn rejects_event_data_after_limit() {
        let mut parser = IncrementalSseParser::new();
        let error = parser
            .push_chunk(&format!(
                "data: {}\n",
                "x".repeat(MAX_SSE_EVENT_DATA_BYTES + 1)
            ))
            .expect_err("oversized event should fail");

        assert!(error.to_string().contains("SSE event data exceeded"));
    }
}
