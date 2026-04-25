"""Tool Permissions - Access control for tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionPolicy(Enum):
    """Policy levels for tool permissions."""
    
    ALLOW_ALL = "allow_all"           # Allow all tools by default
    DENY_ALL = "deny_all"             # Deny all tools by default
    WHITELIST = "whitelist"           # Only allow listed tools
    BLACKLIST = "blacklist"           # Allow all except listed tools


@dataclass
class ToolPermissions:
    """Permissions configuration for an agent or context.
    
    This defines what tools an agent can use and under what constraints.
    """
    
    policy: PermissionPolicy = PermissionPolicy.ALLOW_ALL
    
    # Tool name patterns (supports wildcards)
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    denied_tools: frozenset[str] = field(default_factory=frozenset)
    
    # Path restrictions
    allowed_paths: frozenset[str] = field(default_factory=frozenset)
    denied_paths: frozenset[str] = field(default_factory=frozenset)
    
    # Command restrictions (for shell tools)
    allowed_commands: frozenset[str] = field(default_factory=frozenset)
    denied_commands: frozenset[str] = field(default_factory=frozenset)
    
    # Risk level ceiling
    max_risk_level: str = "high"  # Tools above this risk level are denied
    
    # Execution limits
    max_concurrent: int = 5
    max_per_minute: int = 60
    
    # Elevated permissions
    can_write: bool = False
    can_delete: bool = False
    can_execute_shell: bool = False
    can_access_network: bool = False
    
    def tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed under this policy."""
        name_lower = tool_name.lower()
        
        # Check deny lists first
        if self._matches_pattern(name_lower, self.denied_tools):
            return False
        
        # Check allow lists based on policy
        match self.policy:
            case PermissionPolicy.DENY_ALL:
                return False
            case PermissionPolicy.WHITELIST:
                return self._matches_pattern(name_lower, self.allowed_tools)
            case PermissionPolicy.BLACKLIST:
                return True
            case PermissionPolicy.ALLOW_ALL:
                # Check if specifically denied
                if self.denied_tools:
                    return not self._matches_pattern(name_lower, self.denied_tools)
                return True
        
        return True
    
    def path_allowed(self, path: str) -> bool:
        """Check if a path is accessible."""
        # Check denied paths first
        if self._path_matches(path, self.denied_paths):
            return False
        
        # If no restrictions, allow
        if not self.allowed_paths:
            return True
        
        return self._path_matches(path, self.allowed_paths)
    
    def command_allowed(self, command: str) -> bool:
        """Check if a shell command is allowed."""
        if not self.can_execute_shell:
            return False
        
        # Check denied commands first
        if self._matches_pattern(command.lower(), self.denied_commands):
            return False
        
        # If no restrictions, allow
        if not self.allowed_commands:
            return True
        
        return self._matches_pattern(command.lower(), self.allowed_commands)
    
    @staticmethod
    def _matches_pattern(text: str, patterns: frozenset[str]) -> bool:
        """Check if text matches any pattern in set."""
        for pattern in patterns:
            if pattern == "*":
                return True
            if pattern.endswith("*"):
                if text.startswith(pattern[:-1]):
                    return True
            elif pattern.startswith("*"):
                if text.endswith(pattern[1:]):
                    return True
            elif text == pattern:
                return True
        return False
    
    @staticmethod
    def _path_matches(path: str, patterns: frozenset[str]) -> bool:
        """Check if path matches any path pattern."""
        import os
        
        # Normalize path
        try:
            normalized = os.path.normpath(os.path.abspath(path))
        except (ValueError, TypeError):
            return False
        
        for pattern in patterns:
            try:
                pattern_normalized = os.path.normpath(os.path.abspath(pattern))
                if normalized.startswith(pattern_normalized):
                    return True
            except (ValueError, TypeError):
                continue
        
        return False


@dataclass
class PermissionContext:
    """Runtime context for permission evaluation."""
    
    agent_id: str
    agent_role: str = "default"
    task_type: str = "general"
    
    # Current working context
    repo_path: str | None = None
    branch: str | None = None
    
    # Override settings
    elevated_permissions: bool = False
    bypass_confirmation: bool = False


def check_tool_permission(
    tool_name: str,
    permissions: ToolPermissions,
    context: PermissionContext | None = None,
) -> PermissionResult:
    """Check if a tool can be executed with given permissions.
    
    Args:
        tool_name: Name of the tool to check
        permissions: Permissions configuration
        context: Optional runtime context
        
    Returns:
        PermissionResult with allowed status and reason
    """
    # Elevated permissions bypass most checks
    if context is not None and context.elevated_permissions:
        return PermissionResult(allowed=True, reason="elevated_permissions")
    
    # Check tool allow/deny
    if not permissions.tool_allowed(tool_name):
        return PermissionResult(
            allowed=False,
            reason=f"Tool '{tool_name}' is not permitted by policy {permissions.policy.value}",
        )
    
    # Check risk level
    risk_hierarchy = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    tool_risk = "low"  # Default, should come from tool manifest
    
    if risk_hierarchy.get(tool_risk, 0) > risk_hierarchy.get(permissions.max_risk_level, 0):
        return PermissionResult(
            allowed=False,
            reason=f"Tool risk level '{tool_risk}' exceeds maximum '{permissions.max_risk_level}'",
        )
    
    return PermissionResult(allowed=True, reason="permitted")


@dataclass
class PermissionResult:
    """Result of a permission check."""
    
    allowed: bool
    reason: str
    
    @property
    def denied(self) -> bool:
        """Check if permission was denied."""
        return not self.allowed


def create_restricted_permissions(
    allowed_paths: list[str] | None = None,
    denied_paths: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    denied_tools: list[str] | None = None,
    read_only: bool = True,
) -> ToolPermissions:
    """Create a restricted permissions configuration.
    
    Useful for sandboxed or untrusted execution contexts.
    """
    return ToolPermissions(
        policy=PermissionPolicy.WHITELIST if allowed_tools else PermissionPolicy.BLACKLIST,
        allowed_tools=frozenset(allowed_tools) if allowed_tools else frozenset(),
        denied_tools=frozenset(denied_tools) if denied_tools else frozenset(),
        allowed_paths=frozenset(allowed_paths) if allowed_paths else frozenset(),
        denied_paths=frozenset(denied_paths) if denied_paths else frozenset(),
        can_write=not read_only,
        can_delete=False,
        can_execute_shell=not read_only,
    )


def create_developer_permissions() -> ToolPermissions:
    """Create permissions for a developer agent."""
    return ToolPermissions(
        policy=PermissionPolicy.ALLOW_ALL,
        allowed_tools=frozenset(),
        denied_tools=frozenset(),
        can_write=True,
        can_delete=False,  # Still requires confirmation
        can_execute_shell=True,
        can_access_network=True,
    )


def create_ci_permissions() -> ToolPermissions:
    """Create permissions for CI/CD execution context."""
    return ToolPermissions(
        policy=PermissionPolicy.BLACKLIST,
        denied_tools=frozenset({"delete_file", "rm", "rmdir"}),
        allowed_paths=frozenset(),
        denied_paths=frozenset(),
        max_risk_level="medium",
        can_write=True,
        can_delete=False,
        can_execute_shell=True,
        can_access_network=False,  # No network access in CI
    )
