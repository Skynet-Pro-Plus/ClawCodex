"""Exception Capture - Read and analyze exception stack traces."""

from __future__ import annotations

import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ExceptionInfo:
    """Captured exception information."""
    
    type: str
    message: str
    traceback: str
    timestamp: datetime
    source_file: str | None = None
    source_line: int | None = None
    stack_frames: list[dict[str, Any]] = field(default_factory=list)
    service: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "traceback": self.traceback,
            "timestamp": self.timestamp.isoformat(),
            "source_file": self.source_file,
            "source_line": self.source_line,
            "stack_frames": self.stack_frames,
            "service": self.service,
        }


@dataclass
class ExceptionPattern:
    """A pattern for matching similar exceptions."""
    
    signature: str
    category: str
    description: str
    suggested_fix: str | None = None
    frequency: int = 0


class ExceptionCapture:
    """Captures and analyzes exceptions from logs and trace files."""
    
    # Common exception patterns
    PATTERNS = [
        # Python exceptions
        (r"(\w+Error): (.+)", "python"),
        (r"(\w+Exception): (.+)", "python"),
        (r"Traceback \(most recent call last\):", "traceback_start"),
        # JavaScript/Node exceptions
        (r"(?:Error|Exception): (.+?)(?:\n|    at)", "javascript"),
        # Generic patterns
        (r"(?:FATAL|CRITICAL|ERROR): (.+)", "log_error"),
    ]
    
    def __init__(self):
        self._patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(p, re.MULTILINE), t) for p, t in self.PATTERNS
        ]
    
    def capture_from_text(self, text: str, service: str | None = None) -> list[ExceptionInfo]:
        """Capture exceptions from text content.
        
        Args:
            text: Text content to search for exceptions
            service: Optional service name for context
            
        Returns:
            List of captured exceptions
        """
        exceptions = []
        
        # Find traceback sections
        traceback_pattern = r'Traceback \(most recent call last\):\n((?:.*\n){1,20})'
        matches = re.finditer(traceback_pattern, text)
        
        for match in matches:
            # Extract traceback
            tb_start = match.start()
            tb_text = match.group(0)
            
            # Find the exception type and message before traceback
            pre_text = text[max(0, tb_start - 500):tb_start]
            exception_match = re.search(r'(\w+(?:Error|Exception)): (.+)', pre_text)
            
            if exception_match:
                exc_type = exception_match.group(1)
                exc_message = exception_match.group(2)
            else:
                exc_type = "UnknownError"
                exc_message = "Unknown error"
            
            # Parse stack frames
            frames = self._parse_traceback(tb_text)
            
            # Get source location from first non-standard frame
            source_file = None
            source_line = None
            for frame in frames:
                if not self._is_stdlib_frame(frame.get("file", "")):
                    source_file = frame.get("file")
                    source_line = frame.get("line")
                    break
            
            exceptions.append(ExceptionInfo(
                type=exc_type,
                message=exc_message,
                traceback=tb_text,
                timestamp=datetime.now(),
                source_file=source_file,
                source_line=source_line,
                stack_frames=frames,
                service=service,
            ))
        
        # Also find single-line error patterns
        for pattern, ptype in self._patterns:
            if ptype not in ("traceback_start",):
                for match in pattern.finditer(text):
                    if match.lastindex and match.lastindex >= 2:
                        exc_type = match.group(1)
                        exc_message = match.group(2)
                        
                        # Avoid duplicates from traceback parsing
                        if not any(
                            e.type == exc_type and e.message == exc_message
                            for e in exceptions
                        ):
                            exceptions.append(ExceptionInfo(
                                type=exc_type,
                                message=exc_message,
                                traceback="",
                                timestamp=datetime.now(),
                                service=service,
                            ))
        
        return exceptions
    
    def capture_from_file(self, path: str, service: str | None = None) -> list[ExceptionInfo]:
        """Capture exceptions from a log file.
        
        Args:
            path: Path to log file
            service: Optional service name
            
        Returns:
            List of captured exceptions
        """
        if not os.path.exists(path):
            return []
        
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return self.capture_from_text(content, service)
        except (IOError, OSError):
            return []
    
    def capture_from_logs(
        self,
        log_paths: list[str] | None = None,
        service: str | None = None,
        since: datetime | None = None,
    ) -> list[ExceptionInfo]:
        """Capture exceptions from multiple log files.
        
        Args:
            log_paths: List of log file paths (default: auto-discover)
            service: Optional service name
            since: Only capture exceptions after this time
            
        Returns:
            List of captured exceptions
        """
        from .logs import find_log_files
        
        if log_paths is None:
            log_paths = find_log_files()
        
        all_exceptions = []
        
        for path in log_paths:
            exceptions = self.capture_from_file(path, service)
            
            # Filter by timestamp if specified
            if since:
                exceptions = [e for e in exceptions if e.timestamp >= since]
            
            all_exceptions.extend(exceptions)
        
        # Sort by timestamp (most recent first)
        all_exceptions.sort(key=lambda e: e.timestamp, reverse=True)
        
        return all_exceptions
    
    def _parse_traceback(self, traceback_text: str) -> list[dict[str, Any]]:
        """Parse a Python traceback into frame information.
        
        Args:
            traceback_text: Raw traceback text
            
        Returns:
            List of frame dicts with file, line, function keys
        """
        frames = []
        
        # Pattern: File "...", line N, in function
        #          OR  File "...", line N
        frame_pattern = r'File "([^"]+)", line (\d+)(?:, in (\w+))?'
        
        for match in re.finditer(frame_pattern, traceback_text):
            file_path = match.group(1)
            line_num = int(match.group(2))
            function = match.group(3) or "<module>"
            
            # Extract the code line if available
            code_context = ""
            context_start = match.end()
            context_end = traceback_text.find('\n', context_start)
            if context_end > 0:
                code_line = traceback_text[context_start:context_end].strip()
                if code_line and not code_line.startswith("File "):
                    code_context = code_line
            
            frames.append({
                "file": file_path,
                "line": line_num,
                "function": function,
                "code": code_context,
            })
        
        return frames
    
    def _is_stdlib_frame(self, file_path: str) -> bool:
        """Check if a frame is from standard library."""
        stdlib_paths = [
            "/usr/lib/python",
            "/usr/local/lib/python",
            "C:\\Python",
            "site-packages",
            "\\lib\\",
            "/lib/",
        ]
        
        for stdlib in stdlib_paths:
            if stdlib in file_path:
                return True
        
        return False
    
    def extract_error_signature(self, exception: ExceptionInfo) -> str:
        """Extract a signature for grouping similar exceptions.
        
        Args:
            exception: Exception to signature
            
        Returns:
            Signature string
        """
        # Use exception type + first frame location as signature
        frames = exception.stack_frames
        
        if frames:
            first_user_frame = next(
                (f for f in frames if not self._is_stdlib_frame(f.get("file", ""))),
                frames[0] if frames else None
            )
            
            if first_user_frame:
                return f"{exception.type}@{first_user_frame.get('file', 'unknown')}:{first_user_frame.get('line', 0)}"
        
        return f"{exception.type}@unknown:0"


def read_recent_exceptions(
    service: str | None = None,
    hours: int = 24,
    log_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Read recent exception stack traces.
    
    Args:
        service: Optional service name to filter
        hours: Number of hours to look back (default: 24)
        log_paths: Optional list of specific log paths
        
    Returns:
        Dict with exceptions and metadata
    """
    capture = ExceptionCapture()
    
    # Calculate time threshold
    since = datetime.now() - timedelta(hours=hours)
    
    # Capture exceptions
    exceptions = capture.capture_from_logs(
        log_paths=log_paths,
        service=service,
        since=since,
    )
    
    # Group by signature
    signatures: dict[str, list[ExceptionInfo]] = {}
    for exc in exceptions:
        sig = capture.extract_error_signature(exc)
        if sig not in signatures:
            signatures[sig] = []
        signatures[sig].append(exc)
    
    # Build response
    return {
        "exceptions": [e.to_dict() for e in exceptions[:100]],  # Limit to 100
        "count": len(exceptions),
        "unique_signatures": len(signatures),
        "signatures": [
            {
                "signature": sig,
                "count": len(excs),
                "example": excs[0].to_dict(),
            }
            for sig, excs in signatures.items()
        ],
        "message": f"Captured {len(exceptions)} exceptions with {len(signatures)} unique signatures",
    }


def analyze_exception_trends(
    exceptions: list[ExceptionInfo],
) -> dict[str, Any]:
    """Analyze trends in exception data.
    
    Args:
        exceptions: List of captured exceptions
        
    Returns:
        Dict with trend analysis
    """
    if not exceptions:
        return {"trends": [], "summary": "No exceptions to analyze"}
    
    # Group by type
    by_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_hour: dict[str, int] = {}
    
    for exc in exceptions:
        by_type[exc.type] = by_type.get(exc.type, 0) + 1
        
        if exc.source_file:
            # Extract module from path
            module = exc.source_file.split('/')[-1].split('\\')[-1]
            by_source[module] = by_source.get(module, 0) + 1
        
        # Group by hour
        hour_key = exc.timestamp.strftime('%Y-%m-%d %H:00')
        by_hour[hour_key] = by_hour.get(hour_key, 0) + 1
    
    # Find most common
    top_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]
    top_sources = sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "total_exceptions": len(exceptions),
        "time_range": {
            "start": min(e.timestamp for e in exceptions).isoformat(),
            "end": max(e.timestamp for e in exceptions).isoformat(),
        },
        "top_exception_types": [{"type": t, "count": c} for t, c in top_types],
        "top_sources": [{"source": s, "count": c} for s, c in top_sources],
        "exceptions_by_hour": by_hour,
        "error_rate_per_hour": len(exceptions) / max(1, len(set(by_hour.keys()))),
    }
