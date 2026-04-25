"""Tool Categories - Predefined category taxonomies for tool organization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_manifest import ToolCategory


@dataclass
class ToolCategoryInfo:
    """Metadata for a tool category."""
    
    category: ToolCategory
    name: str
    description: str
    icon: str
    color: str
    tools: list[str]


# Tool category definitions with metadata
TOOL_CATEGORIES: dict[ToolCategory, ToolCategoryInfo] = {
    ToolCategory.READ: ToolCategoryInfo(
        category=ToolCategory.READ,
        name="Read Tools",
        description="File reading, globbing, searching, and data retrieval",
        icon="📖",
        color="#4CAF50",
        tools=[
            "get_symbol_definition",
            "find_references",
            "read_file",
            "read_logs",
        ],
    ),
    ToolCategory.ANALYZE: ToolCategoryInfo(
        category=ToolCategory.ANALYZE,
        name="Analysis Tools",
        description="Code analysis, state modeling, and dependency tracking",
        icon="🔍",
        color="#2196F3",
        tools=[
            "build_state_model",
            "get_callers",
            "get_callees",
            "get_module_dependencies",
            "get_reverse_dependencies",
            "predict_edit_impact",
            "find_tests_for_symbol",
            "find_tests_for_change",
            "analyze_environment",
        ],
    ),
    ToolCategory.SIMULATE: ToolCategoryInfo(
        category=ToolCategory.SIMULATE,
        name="Simulation Tools",
        description="Patch simulation, dry runs, and predictive analysis",
        icon="🎭",
        color="#9C27B0",
        tools=[
            "validate_patch",
            "simulate_patch",
            "estimate_risk",
        ],
    ),
    ToolCategory.MODIFY: ToolCategoryInfo(
        category=ToolCategory.MODIFY,
        name="Modification Tools",
        description="File editing, creation, and content modification",
        icon="✏️",
        color="#FF9800",
        tools=[
            "edit_file",
            "write_file",
            "create_file",
            "apply_patch",
        ],
    ),
    ToolCategory.EXECUTE: ToolCategoryInfo(
        category=ToolCategory.EXECUTE,
        name="Execution Tools",
        description="Command execution, test running, and process management",
        icon="⚡",
        color="#F44336",
        tools=[
            "run_command",
            "run_tests",
            "run_targeted_tests",
            "install_dependencies",
        ],
    ),
    ToolCategory.OBSERVE: ToolCategoryInfo(
        category=ToolCategory.OBSERVE,
        name="Observation Tools",
        description="Runtime inspection, log monitoring, and process watching",
        icon="👁️",
        color="#00BCD4",
        tools=[
            "tail_logs",
            "watch_process",
            "read_recent_exceptions",
            "observe_http_traffic",
            "inspect_open_ports",
        ],
    ),
    ToolCategory.COORDINATE: ToolCategoryInfo(
        category=ToolCategory.COORDINATE,
        name="Coordination Tools",
        description="File locking, task ownership, and multi-agent coordination",
        icon="🔒",
        color="#795548",
        tools=[
            "lock_file",
            "release_file",
            "get_file_lock",
            "reserve_change_set",
            "handoff_task",
            "get_task_owner",
        ],
    ),
    ToolCategory.MEMORY: ToolCategoryInfo(
        category=ToolCategory.MEMORY,
        name="Memory Tools",
        description="Failure pattern storage, success registry, and institutional memory",
        icon="🧠",
        color="#607D8B",
        tools=[
            "record_failure_pattern",
            "search_failure_patterns",
            "suggest_known_fix",
            "record_successful_repair",
        ],
    ),
    ToolCategory.SECURITY: ToolCategoryInfo(
        category=ToolCategory.SECURITY,
        name="Security Tools",
        description="Vulnerability scanning, secret detection, and dependency analysis",
        icon="🛡️",
        color="#E91E63",
        tools=[
            "scan_dependencies",
            "scan_vulnerabilities",
            "scan_secrets",
            "scan_licenses",
        ],
    ),
    ToolCategory.ROUTING: ToolCategoryInfo(
        category=ToolCategory.ROUTING,
        name="Routing Tools",
        description="Model selection, cost estimation, and resource optimization",
        icon="🎯",
        color="#673AB7",
        tools=[
            "estimate_llm_cost",
            "recommend_model_for_stage",
            "track_token_usage",
            "summarize_model_efficiency",
        ],
    ),
    ToolCategory.EXPERIMENT: ToolCategoryInfo(
        category=ToolCategory.EXPERIMENT,
        name="Experimentation Tools",
        description="Autonomous experimentation, A/B testing, and benchmark execution",
        icon="🧪",
        color="#3F51B5",
        tools=[
            "create_experiment",
            "run_experiment",
            "compare_experiment_results",
            "promote_experiment_patch",
            "discard_experiment_patch",
        ],
    ),
}


def get_category_tools(category: ToolCategory) -> list[str]:
    """Get list of tool names in a category."""
    info = TOOL_CATEGORIES.get(category)
    return info.tools if info else []


def get_category_info(category: ToolCategory) -> ToolCategoryInfo | None:
    """Get category metadata."""
    return TOOL_CATEGORIES.get(category)


def list_categories() -> list[ToolCategoryInfo]:
    """List all category information."""
    return list(TOOL_CATEGORIES.values())


def get_category_by_tool(tool_name: str) -> ToolCategory | None:
    """Find the category a tool belongs to."""
    for category, info in TOOL_CATEGORIES.items():
        if tool_name in info.tools:
            return category
    return None


def get_tools_by_categories(categories: list[ToolCategory]) -> list[str]:
    """Get all tool names for multiple categories."""
    tools = []
    for category in categories:
        tools.extend(get_category_tools(category))
    return tools


def format_category_markdown(category: ToolCategory) -> str:
    """Format category as markdown string."""
    info = TOOL_CATEGORIES.get(category)
    if not info:
        return "Unknown category"
    
    lines = [
        f"## {info.icon} {info.name}",
        "",
        info.description,
        "",
        "Tools:",
    ]
    for tool in info.tools:
        lines.append(f"- `{tool}`")
    
    return "\n".join(lines)


def format_all_categories_markdown() -> str:
    """Format all categories as markdown."""
    lines = ["# Tool Categories", ""]
    
    for category in ToolCategory:
        lines.append(format_category_markdown(category))
        lines.append("")
    
    return "\n".join(lines)
