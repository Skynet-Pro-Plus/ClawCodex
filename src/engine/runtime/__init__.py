"""Runtime Observation Module - Log tailing, exception capture, and process inspection."""

from .logs import tail_logs, TailLogsConfig
from .exceptions import read_recent_exceptions, ExceptionCapture
from .process_observer import (
    watch_process,
    inspect_open_ports,
    ProcessInfo,
    PortInfo,
)
from .http_observer import observe_http_traffic, HTTPTransaction

__all__ = [
    # Logs
    "tail_logs",
    "TailLogsConfig",
    # Exceptions
    "read_recent_exceptions",
    "ExceptionCapture",
    # Process
    "watch_process",
    "inspect_open_ports",
    "ProcessInfo",
    "PortInfo",
    # HTTP
    "observe_http_traffic",
    "HTTPTransaction",
]
