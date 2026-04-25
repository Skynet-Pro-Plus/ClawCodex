"""Tool Result Envelope - Standard response format for all tool invocations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ToolResultStatus(Enum):
    """Status codes for tool execution results."""
    
    SUCCESS = "success"                     # Execution completed successfully
    ERROR = "error"                        # Execution failed with error
    NOT_FOUND = "not_found"               # Tool not registered
    TIMEOUT = "timeout"                    # Execution timed out
    PERMISSION_DENIED = "permission_denied"  # Permission check failed
    REQUIRES_CONFIRMATION = "requires_confirmation"  # User confirmation needed
    INVALID_ARGUMENTS = "invalid_arguments"  # Arguments don't match schema


@dataclass
class ToolResult:
    """Standard envelope for tool execution results.
    
    Every tool invocation MUST return this structure. This ensures:
    - Consistent error handling
    - Audit trail completeness
    - Replay capability
    - Caching support
    """
    
    # Core result
    ok: bool
    tool_name: str
    data: Any = None
    
    # Diagnostic information
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    
    # Performance metrics
    timing_ms: int = 0
    
    # Caching and replay
    cache_key: str = ""
    replayable: bool = True
    
    # Extended metadata
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    audit_trail: AuditRef | None = None
    
    # Context
    execution_context: ExecutionContext | None = None
    
    def __post_init__(self):
        """Set default status based on ok flag."""
        if not self.ok and self.status == ToolResultStatus.SUCCESS:
            self.status = ToolResultStatus.ERROR
    
    @property
    def has_warnings(self) -> bool:
        """Check if result has warnings."""
        return len(self.warnings) > 0
    
    @property
    def has_errors(self) -> bool:
        """Check if result has errors."""
        return len(self.errors) > 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "data": self.data,
            "warnings": self.warnings,
            "errors": self.errors,
            "artifacts": [
                {
                    "name": a.name,
                    "path": a.path,
                    "content_type": a.content_type,
                }
                for a in self.artifacts
            ],
            "timing_ms": self.timing_ms,
            "cache_key": self.cache_key,
            "replayable": self.replayable,
            "status": self.status.value,
        }
    
    @classmethod
    def success(
        cls,
        tool_name: str,
        data: Any,
        **kwargs: Any,
    ) -> "ToolResult":
        """Create a successful result."""
        return cls(
            ok=True,
            tool_name=tool_name,
            data=data,
            status=ToolResultStatus.SUCCESS,
            **kwargs,
        )
    
    @classmethod
    def error(
        cls,
        tool_name: str,
        message: str,
        errors: list[str] | None = None,
        **kwargs: Any,
    ) -> "ToolResult":
        """Create an error result."""
        error_list = errors or [message]
        return cls(
            ok=False,
            tool_name=tool_name,
            data=None,
            errors=error_list,
            status=ToolResultStatus.ERROR,
            **kwargs,
        )
    
    @classmethod
    def not_found(
        cls,
        tool_name: str,
    ) -> "ToolResult":
        """Create a not-found result."""
        return cls(
            ok=False,
            tool_name=tool_name,
            data=None,
            errors=[f"Tool not found: {tool_name}"],
            status=ToolResultStatus.NOT_FOUND,
        )
    
    @classmethod
    def timeout(
        cls,
        tool_name: str,
        timeout_sec: int,
    ) -> "ToolResult":
        """Create a timeout result."""
        return cls(
            ok=False,
            tool_name=tool_name,
            data=None,
            errors=[f"Tool execution timed out after {timeout_sec}s"],
            status=ToolResultStatus.TIMEOUT,
            timing_ms=timeout_sec * 1000,
        )
    
    @classmethod
    def permission_denied(
        cls,
        tool_name: str,
        reason: str,
    ) -> "ToolResult":
        """Create a permission denied result."""
        return cls(
            ok=False,
            tool_name=tool_name,
            data=None,
            errors=[f"Permission denied: {reason}"],
            status=ToolResultStatus.PERMISSION_DENIED,
        )


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to an artifact produced by a tool."""
    
    name: str
    path: str | None = None
    content_type: str = "text/plain"
    size_bytes: int = 0
    checksum: str | None = None


@dataclass(frozen=True)
class AuditRef:
    """Reference to audit trail entry."""
    
    timestamp: datetime
    agent_id: str
    task_id: str
    run_id: str
    tool_name: str
    arguments_hash: str
    result_hash: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    """Context information for result attribution."""
    
    repo_path: str | None = None
    branch: str | None = None
    snapshot_id: str | None = None
    workspace_id: str | None = None


def wrap_result(
    ok: bool,
    tool_name: str,
    data: Any = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    timing_ms: int = 0,
) -> ToolResult:
    """Convenience wrapper for creating ToolResult."""
    return ToolResult(
        ok=ok,
        tool_name=tool_name,
        data=data,
        warnings=warnings or [],
        errors=errors or [],
        timing_ms=timing_ms,
    )
