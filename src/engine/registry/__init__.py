"""Tool Registry Module - Manages tool manifests, categories, and metadata."""

from .tool_manifest import (
    ToolCategory,
    SideEffectLevel,
    RiskLevel,
    ToolManifest,
    AuditEntry,
    Artifact,
)
from .tool_registry import (
    ToolRegistry,
    get_global_registry,
    register_tool,
    get_tool,
    list_tools,
    find_tools_by_category,
)
from .dispatcher import invoke_tool, DispatchContext
from .result import ToolResult, ToolResultStatus
from .permissions import (
    ToolPermissions,
    PermissionPolicy,
    check_tool_permission,
)
from .categories import TOOL_CATEGORIES, get_category_tools

__all__ = [
    "ToolCategory",
    "SideEffectLevel",
    "RiskLevel",
    "ToolManifest",
    "AuditEntry",
    "Artifact",
    "ToolRegistry",
    "get_global_registry",
    "register_tool",
    "get_tool",
    "list_tools",
    "find_tools_by_category",
    "invoke_tool",
    "DispatchContext",
    "ToolResult",
    "ToolResultStatus",
    "ToolPermissions",
    "PermissionPolicy",
    "check_tool_permission",
    "TOOL_CATEGORIES",
    "get_category_tools",
]
