"""Log Tailing - Real-time log monitoring and streaming."""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator


@dataclass
class TailLogsConfig:
    """Configuration for log tailing."""
    
    service: str | None = None
    lines: int = 200
    follow: bool = False
    since: datetime | None = None
    filter_pattern: str | None = None
    log_dirs: list[str] = field(default_factory=lambda: [
        "logs",
        "var/log",
        "/var/log",
    ])


@dataclass
class LogEntry:
    """A single log entry."""
    
    timestamp: datetime
    level: str
    message: str
    source: str
    line_number: int
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "line_number": self.line_number,
        }


class LogTailingSession:
    """Active log tailing session."""
    
    def __init__(
        self,
        paths: list[str],
        config: TailLogsConfig,
    ):
        self.paths = paths
        self.config = config
        self._stop_event = threading.Event()
        self._read_positions: dict[str, int] = {}
        self._lock = threading.Lock()
    
    def stop(self) -> None:
        """Stop the tailing session."""
        self._stop_event.set()
    
    def tail(self) -> Generator[LogEntry, None, None]:
        """Tail logs and yield entries."""
        # Initialize read positions
        for path in self.paths:
            if os.path.exists(path):
                self._read_positions[path] = self._get_file_size(path)
        
        while not self._stop_event.is_set():
            for path in self.paths:
                if os.path.exists(path):
                    yield from self._read_new_lines(path)
            
            if not self.config.follow:
                break
            
            time.sleep(0.5)
    
    def _read_new_lines(self, path: str) -> Generator[LogEntry, None, None]:
        """Read new lines from a file since last read."""
        with self._lock:
            current_size = self._get_file_size(path)
            last_pos = self._read_positions.get(path, 0)
            
            if current_size < last_pos:
                # File was truncated, start from beginning
                last_pos = 0
            
            if current_size == last_pos:
                return
            
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(last_pos)
                    line_number = self._count_lines(path, last_pos)
                    
                    for line in f:
                        line = line.rstrip('\n\r')
                        if line:
                            entry = self._parse_line(line, path, line_number)
                            if entry and self._filter_entry(entry):
                                yield entry
                            line_number += 1
                    
                    self._read_positions[path] = f.tell()
            except (IOError, OSError):
                pass
    
    def _get_file_size(self, path: str) -> int:
        """Get current file size."""
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    
    def _count_lines(self, path: str, byte_pos: int) -> int:
        """Count lines up to a byte position."""
        try:
            with open(path, 'rb') as f:
                f.seek(0)
                return sum(1 for _ in iter(lambda: f.readline(), b'') if f.tell() <= byte_pos)
        except OSError:
            return 0
    
    def _parse_line(self, line: str, source: str, line_number: int) -> LogEntry | None:
        """Parse a log line into a LogEntry."""
        # Common log formats
        patterns = [
            # ISO timestamp with level: 2024-01-15T10:30:00 INFO message
            (r'^(\d{4}-\d{2}-\d{2}T[\d:]+(?:\.\d+)?Z?)\s+(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\s+(.*)$', 'iso'),
            # Common log format: [2024-01-15 10:30:00] INFO: message
            (r'^\[(\d{4}-\d{2}-\d{2}\s+[\d:]+)\]\s+(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL):?\s*(.*)$', 'bracket'),
            # Simple timestamp: 2024-01-15 10:30:00 INFO message
            (r'^(\d{4}-\d{2}-\d{2}\s+[\d:]+)\s+(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\s+(.*)$', 'simple'),
        ]
        
        for pattern, fmt in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                timestamp_str, level, message = match.groups()
                try:
                    if 'T' in timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    timestamp = datetime.now()
                
                return LogEntry(
                    timestamp=timestamp,
                    level=level.upper(),
                    message=message.strip(),
                    source=source,
                    line_number=line_number,
                )
        
        # Fallback: no recognized format
        return LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            message=line,
            source=source,
            line_number=line_number,
        )
    
    def _filter_entry(self, entry: LogEntry) -> bool:
        """Filter entry based on config."""
        # Filter by service if specified
        if self.config.service:
            if self.config.service.lower() not in entry.source.lower():
                return False
        
        # Filter by pattern if specified
        if self.config.filter_pattern:
            pattern = re.compile(self.config.filter_pattern, re.IGNORECASE)
            if not pattern.search(entry.message):
                return False
        
        # Filter by since timestamp
        if self.config.since:
            if entry.timestamp < self.config.since:
                return False
        
        return True


def find_log_files(
    base_path: str | None = None,
    patterns: list[str] | None = None,
) -> list[str]:
    """Find log files in common locations.
    
    Args:
        base_path: Base path to search from (default: current directory)
        patterns: File patterns to match (default: common log patterns)
        
    Returns:
        List of log file paths
    """
    base_path = base_path or os.getcwd()
    patterns = patterns or [
        "*.log",
        "*.logs",
        "*.out",
        "logs/**/*.log",
        "var/log/**/*.log",
    ]
    
    files = []
    base = Path(base_path)
    
    for pattern in patterns:
        try:
            files.extend(str(p) for p in base.rglob(pattern) if p.is_file())
        except (OSError, RuntimeError):
            pass
    
    return sorted(set(files))


def tail_logs(
    service: str | None = None,
    lines: int = 200,
    follow: bool = False,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Tail application logs in real-time.
    
    Args:
        service: Optional service name to filter logs
        lines: Number of recent lines to return
        follow: Whether to follow logs continuously
        log_dir: Optional specific log directory
        
    Returns:
        Dict with logs and metadata
    """
    config = TailLogsConfig(
        service=service,
        lines=lines,
        follow=follow,
    )
    
    # Find log files
    if log_dir:
        paths = [log_dir]
    else:
        paths = find_log_files()
    
    if not paths:
        return {
            "logs": [],
            "count": 0,
            "sources": [],
            "message": "No log files found",
        }
    
    # Read recent lines
    all_entries: list[LogEntry] = []
    sources = set()
    
    for path in paths:
        if os.path.exists(path):
            sources.add(path)
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    file_lines = f.readlines()
                    
                    # Get last N lines
                    recent = file_lines[-lines:] if len(file_lines) > lines else file_lines
                    
                    # Parse each line
                    line_num = max(0, len(file_lines) - len(recent))
                    for line in recent:
                        line = line.rstrip('\n\r')
                        if line:
                            entry = LogTailingSession([], config)._parse_line(line, path, line_num)
                            if entry:
                                all_entries.append(entry)
                            line_num += 1
                            
            except (IOError, OSError):
                pass
    
    # Sort by timestamp
    all_entries.sort(key=lambda e: e.timestamp)
    
    return {
        "logs": [e.to_dict() for e in all_entries],
        "count": len(all_entries),
        "sources": list(sources),
        "message": f"Found {len(all_entries)} log entries from {len(sources)} sources",
    }


def stream_logs(
    service: str | None = None,
    filter_pattern: str | None = None,
) -> LogTailingSession:
    """Create a streaming log session.
    
    Args:
        service: Optional service name to filter
        filter_pattern: Regex pattern to filter messages
        
    Returns:
        LogTailingSession that can be iterated
    """
    config = TailLogsConfig(
        service=service,
        follow=True,
        filter_pattern=filter_pattern,
    )
    
    paths = find_log_files()
    
    session = LogTailingSession(paths, config)
    return session
