"""Tool Manifest Definition - Core data structures for tool metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ToolCategory(Enum):
    """Categories for tool classification."""
    
    READ = "read"           # File reading, glob, grep
    ANALYZE = "analyze"      # Code analysis, graph building
    SIMULATE = "simulate"    # Patch simulation, dry runs
    MODIFY = "modify"        # File editing, writing
    EXECUTE = "execute"      # Bash commands, test execution
    OBSERVE = "observe"      # Log tailing, process inspection
    COORDINATE = "coordinate" # File locking, task ownership
    MEMORY = "memory"        # Failure patterns, success registry
    SECURITY = "security"    # Vulnerability scanning, secret detection
    ROUTING = "routing"      # Model selection, cost estimation
    EXPERIMENT = "experiment" # Autonomous experimentation


class SideEffectLevel(Enum):
    """Level of side effects a tool can produce."""
    
    NONE = "none"           # Pure read-only operation
    READ = "read"           # Reads system state
    WRITE = "write"         # Modifies files/data
    DESTRUCTIVE = "destructive"  # Can delete or cause data loss


class RiskLevel(Enum):
    """Risk assessment for tool execution."""
    
    LOW = "low"             # Safe to execute, reversible
    MEDIUM = "medium"        # Moderate risk, may affect state
    HIGH = "high"           # Significant changes, requires confirmation
    CRITICAL = "critical"   # Potentially destructive, gated


@dataclass(frozen=True)
class Artifact:
    """Represents a file or data artifact produced by a tool."""
    
    name: str
    path: str | None = None
    content_type: str = "text/plain"
    size_bytes: int = 0
    checksum: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    """Audit trail entry for tool execution."""
    
    timestamp: datetime
    agent_id: str
    task_id: str
    run_id: str
    tool_name: str
    arguments_hash: str  # SHA256 of arguments for replay
    result_hash: str | None = None
    parent_run_id: str | None = None


@dataclass
class ToolManifest:
    """Complete manifest defining a tool's capabilities and constraints.
    
    This is the primary data structure for tool registration and dispatch.
    Every tool in the engine must have a valid manifest.
    """
    
    name: str
    category: ToolCategory
    description: str
    purpose: str
    
    # Schema definitions (JSON Schema compatible)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    
    # Execution constraints
    side_effect: SideEffectLevel = SideEffectLevel.NONE
    risk_level: RiskLevel = RiskLevel.LOW
    timeout_sec: int = 300
    
    # Access control
    allowed_paths: list[str] | None = None      # Paths the tool can access
    denied_paths: list[str] | None = None       # Explicitly denied paths
    allowed_commands: list[str] | None = None   # Allowed shell commands
    denied_commands: list[str] | None = None    # Explicitly denied commands
    
    # Confirmation requirements
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    
    # Dependencies
    required_tools: list[str] | None = None    # Tools that must be available
    required_commands: list[str] | None = None # System commands needed
    
    # Caching and replay
    cacheable: bool = True
    replayable: bool = True
    
    # Metadata
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    
    # Implementation reference
    implementation_module: str | None = None
    implementation_function: str | None = None
    
    def validate(self) -> list[str]:
        """Validate the manifest and return list of issues."""
        issues = []
        
        if not self.name:
            issues.append("Tool name is required")
        if not self.description:
            issues.append("Tool description is required")
        if not self.purpose:
            issues.append("Tool purpose is required")
        if self.timeout_sec <= 0:
            issues.append("Timeout must be positive")
        if self.side_effect == SideEffectLevel.DESTRUCTIVE and not self.requires_confirmation:
            issues.append("Destructive tools require confirmation")
            
        return issues
    
    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is allowed for this tool."""
        if self.allowed_paths is None:
            return True
        return any(
            path.startswith(allowed) 
            for allowed in self.allowed_paths
        )
    
    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is allowed for this tool."""
        if self.allowed_commands is None:
            return True
        return any(
            command.startswith(allowed)
            for allowed in self.allowed_commands
        )
