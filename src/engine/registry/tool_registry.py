"""Tool Registry - Central registry for all engine tools."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Iterator

from .tool_manifest import ToolCategory, ToolManifest


@dataclass
class ToolRegistry:
    """Thread-safe central registry for all engine tools.
    
    This is the source of truth for tool metadata. All tools must be
    registered before they can be dispatched.
    """
    
    _tools: dict[str, ToolManifest] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    
    def register(self, manifest: ToolManifest) -> None:
        """Register a tool manifest."""
        with self._lock:
            issues = manifest.validate()
            if issues:
                raise ValueError(f"Invalid tool manifest: {', '.join(issues)}")
            self._tools[manifest.name] = manifest
    
    def register_from_callable(
        self,
        name: str,
        category: ToolCategory,
        description: str,
        purpose: str,
    ) -> Callable:
        """Decorator to register a function as a tool."""
        def decorator(func: Callable) -> Callable:
            manifest = ToolManifest(
                name=name,
                category=category,
                description=description,
                purpose=purpose,
                implementation_module=func.__module__,
                implementation_function=func.__name__,
            )
            self.register(manifest)
            return func
        return decorator
    
    def get(self, name: str) -> ToolManifest | None:
        """Get a tool manifest by name."""
        with self._lock:
            return self._tools.get(name)
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                return True
            return False
    
    def list_all(self) -> list[ToolManifest]:
        """List all registered tools."""
        with self._lock:
            return list(self._tools.values())
    
    def list_by_category(self, category: ToolCategory) -> list[ToolManifest]:
        """List tools in a specific category."""
        with self._lock:
            return [
                tool for tool in self._tools.values()
                if tool.category == category
            ]
    
    def search(self, query: str, case_sensitive: bool = False) -> list[ToolManifest]:
        """Search tools by name, description, or purpose."""
        with self._lock:
            query_lower = query if case_sensitive else query.lower()
            return [
                tool for tool in self._tools.values()
                if (
                    query in tool.name if case_sensitive else query_lower in tool.name.lower()
                ) or (
                    query in tool.description if case_sensitive else query_lower in tool.description.lower()
                ) or (
                    query in tool.purpose if case_sensitive else query_lower in tool.purpose.lower()
                )
            ]
    
    def __iter__(self) -> Iterator[ToolManifest]:
        """Iterate over all tools."""
        with self._lock:
            return iter(list(self._tools.values()))
    
    def __len__(self) -> int:
        """Get count of registered tools."""
        with self._lock:
            return len(self._tools)


# Global registry instance
_global_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def get_global_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    with _registry_lock:
        if _global_registry is None:
            _global_registry = ToolRegistry()
            _register_core_tools(_global_registry)
        return _global_registry


def register_tool(manifest: ToolManifest) -> None:
    """Register a tool in the global registry."""
    get_global_registry().register(manifest)


def get_tool(name: str) -> ToolManifest | None:
    """Get a tool from the global registry."""
    return get_global_registry().get(name)


def list_tools() -> list[ToolManifest]:
    """List all tools in the global registry."""
    return get_global_registry().list_all()


def find_tools_by_category(category: ToolCategory) -> list[ToolManifest]:
    """Find tools by category in the global registry."""
    return get_global_registry().list_by_category(category)


def _register_core_tools(registry: ToolRegistry) -> None:
    """Register core engine tools."""
    from .tool_manifest import (
        SideEffectLevel, RiskLevel, ToolManifest, ToolCategory
    )

    # Orchestrator core tools
    registry.register(ToolManifest(
        name="read_file",
        category=ToolCategory.READ,
        description="Read a UTF-8 text file from the repository",
        purpose="Provide source context with path confinement and hashes",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "path": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"content": {"type": "string"}, "sha256": {"type": "string"}, "line_count": {"type": "integer"}}},
        side_effect=SideEffectLevel.READ,
        risk_level=RiskLevel.LOW,
        cacheable=False,
        tags=["core", "filesystem"],
    ))
    registry.register(ToolManifest(
        name="write_file",
        category=ToolCategory.MODIFY,
        description="Create a diff preview for a proposed file write",
        purpose="Require approval before mutating repository files",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}, "mode": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"id": {"type": "string"}, "unified_diff": {"type": "string"}, "status": {"type": "string"}}},
        side_effect=SideEffectLevel.WRITE,
        risk_level=RiskLevel.MEDIUM,
        cacheable=False,
        tags=["core", "filesystem", "diff-preview"],
    ))
    registry.register(ToolManifest(
        name="search_repo",
        category=ToolCategory.READ,
        description="Search repository files by text, glob, or symbol-like token",
        purpose="Find relevant code without mutating the workspace",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "query": {"type": "string"}, "kind": {"type": "string"}}},
        side_effect=SideEffectLevel.READ,
        risk_level=RiskLevel.LOW,
        cacheable=True,
        tags=["core", "search"],
    ))
    registry.register(ToolManifest(
        name="run_command",
        category=ToolCategory.EXECUTE,
        description="Run a guarded shell command inside the repository",
        purpose="Execute safe commands with destructive-operation blocking",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "command": {"type": "string"}}},
        side_effect=SideEffectLevel.READ,
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
        confirmation_reason="Shell commands may change local state",
        cacheable=False,
        tags=["core", "command"],
    ))
    registry.register(ToolManifest(
        name="run_tests",
        category=ToolCategory.EXECUTE,
        description="Run an allowlisted project test command",
        purpose="Verify code changes and store structured test results",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "command": {"type": "string"}}},
        side_effect=SideEffectLevel.READ,
        risk_level=RiskLevel.MEDIUM,
        cacheable=False,
        tags=["core", "tests"],
    ))
    registry.register(ToolManifest(
        name="git_diff",
        category=ToolCategory.READ,
        description="Inspect git diff for review and rollback context",
        purpose="Summarize repository changes without mutating files",
        input_schema={"type": "object", "properties": {"repo_path": {"type": "string"}, "base": {"type": "string"}, "paths": {"type": "array"}}},
        side_effect=SideEffectLevel.READ,
        risk_level=RiskLevel.LOW,
        cacheable=False,
        tags=["core", "git"],
    ))
    
    # Code State Model tools
    registry.register(ToolManifest(
        name="build_state_model",
        category=ToolCategory.ANALYZE,
        description="Build a complete software state model of the repository",
        purpose="Create an indexed representation of code structure, symbols, and dependencies",
        input_schema={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to repository root"},
                "force_refresh": {"type": "boolean", "default": False},
            },
            "required": ["repo_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "snapshot_id": {"type": "string"},
                "file_count": {"type": "integer"},
                "symbol_count": {"type": "integer"},
                "duration_ms": {"type": "integer"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["state-model", "indexing"],
    ))
    
    registry.register(ToolManifest(
        name="get_symbol_definition",
        category=ToolCategory.READ,
        description="Get detailed information about a symbol (function, class, constant)",
        purpose="Retrieve symbol metadata including location, signature, and visibility",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
                "file_path": {"type": "string", "optional": True},
            },
            "required": ["symbol_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "kind": {"type": "string"},
                "file_path": {"type": "string"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
                "signature": {"type": "string"},
                "visibility": {"type": "string"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["symbols", "code-intelligence"],
    ))
    
    registry.register(ToolManifest(
        name="find_references",
        category=ToolCategory.ANALYZE,
        description="Find all references to a symbol across the codebase",
        purpose="Locate all usages of a function, class, or variable",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
                "include_definitions": {"type": "boolean", "default": True},
            },
            "required": ["symbol_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "context": {"type": "string"},
                        },
                    },
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["symbols", "code-intelligence", "analysis"],
    ))
    
    registry.register(ToolManifest(
        name="get_callers",
        category=ToolCategory.ANALYZE,
        description="Find all functions that call the target function",
        purpose="Build upstream call graph to understand dependencies",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
                "max_depth": {"type": "integer", "default": 3},
            },
            "required": ["symbol_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "callers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "depth": {"type": "integer"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["call-graph", "analysis"],
    ))
    
    registry.register(ToolManifest(
        name="get_callees",
        category=ToolCategory.ANALYZE,
        description="Find all functions called by the target function",
        purpose="Build downstream call graph to understand impact",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
                "max_depth": {"type": "integer", "default": 3},
            },
            "required": ["symbol_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "callees": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "depth": {"type": "integer"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["call-graph", "analysis"],
    ))
    
    registry.register(ToolManifest(
        name="get_module_dependencies",
        category=ToolCategory.ANALYZE,
        description="Get all dependencies of a module",
        purpose="Understand what a module imports and depends on",
        input_schema={
            "type": "object",
            "properties": {
                "module_path": {"type": "string"},
            },
            "required": ["module_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "imports": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "dev_imports": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["dependencies", "analysis"],
    ))
    
    registry.register(ToolManifest(
        name="get_reverse_dependencies",
        category=ToolCategory.ANALYZE,
        description="Find all modules that import or depend on the target module",
        purpose="Understand what would break if this module changes",
        input_schema={
            "type": "object",
            "properties": {
                "module_path": {"type": "string"},
            },
            "required": ["module_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "dependents": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["dependencies", "analysis"],
    ))
    
    # Impact Analysis tools
    registry.register(ToolManifest(
        name="predict_edit_impact",
        category=ToolCategory.ANALYZE,
        description="Predict the impact of a proposed code change",
        purpose="Analyze what files, symbols, tests, and APIs would be affected",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File or symbol to change"},
                "change_description": {"type": "string"},
            },
            "required": ["target", "change_description"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "files_affected": {"type": "array", "items": {"type": "string"}},
                "symbols_affected": {"type": "array", "items": {"type": "string"}},
                "tests_affected": {"type": "array", "items": {"type": "string"}},
                "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
                "api_breaking": {"type": "boolean"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["impact-analysis", "change-planning"],
    ))
    
    registry.register(ToolManifest(
        name="find_tests_for_symbol",
        category=ToolCategory.ANALYZE,
        description="Find all tests that exercise a specific symbol",
        purpose="Map tests to code for targeted test selection",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
            },
            "required": ["symbol_name"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "tests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "file": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                    },
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["testing", "test-selection"],
    ))
    
    registry.register(ToolManifest(
        name="find_tests_for_change",
        category=ToolCategory.ANALYZE,
        description="Find tests relevant to a set of changed files",
        purpose="Select minimal test subset for a change",
        input_schema={
            "type": "object",
            "properties": {
                "files_changed": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["files_changed"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "tests_to_run": {"type": "array", "items": {"type": "string"}},
                "confidence_scores": {"type": "object"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["testing", "test-selection"],
    ))
    
    # Patch Safety tools
    registry.register(ToolManifest(
        name="validate_patch",
        category=ToolCategory.SIMULATE,
        description="Validate a patch before applying it",
        purpose="Pre-flight checks for syntax, imports, symbols, and API compatibility",
        input_schema={
            "type": "object",
            "properties": {
                "diff": {"type": "string", "description": "Patch/diff content"},
            },
            "required": ["diff"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["safe", "risky", "breaking"]},
                "risk_score": {"type": "number"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "required_followups": {"type": "array", "items": {"type": "string"}},
                "recommended_tests": {"type": "array", "items": {"type": "string"}},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        requires_confirmation=False,
        tags=["patch-safety", "validation"],
    ))
    
    registry.register(ToolManifest(
        name="simulate_patch",
        category=ToolCategory.SIMULATE,
        description="Simulate applying a patch and predict effects",
        purpose="Dry-run patch to see what would change before committing",
        input_schema={
            "type": "object",
            "properties": {
                "diff": {"type": "string"},
                "include_side_effects": {"type": "boolean", "default": True},
            },
            "required": ["diff"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "files_affected": {"type": "array", "items": {"type": "string"}},
                "dependency_breakage_probability": {"type": "number"},
                "test_coverage_impact": {"type": "number"},
                "rollback_plan": {"type": "string"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["patch-safety", "simulation"],
    ))
    
    # Coordination tools
    registry.register(ToolManifest(
        name="lock_file",
        category=ToolCategory.COORDINATE,
        description="Acquire exclusive write lock on a file",
        purpose="Prevent concurrent edits to the same file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "ttl_sec": {"type": "integer", "default": 900},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "locked": {"type": "boolean"},
                "lock_id": {"type": "string"},
                "expires_at": {"type": "string"},
            },
        },
        risk_level=RiskLevel.MEDIUM,
        side_effect=SideEffectLevel.WRITE,
        tags=["coordination", "locking"],
    ))
    
    registry.register(ToolManifest(
        name="release_file",
        category=ToolCategory.COORDINATE,
        description="Release a write lock on a file",
        purpose="Allow other agents to edit the file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "released": {"type": "boolean"},
            },
        },
        risk_level=RiskLevel.MEDIUM,
        side_effect=SideEffectLevel.WRITE,
        tags=["coordination", "locking"],
    ))
    
    # Runtime observation tools
    registry.register(ToolManifest(
        name="tail_logs",
        category=ToolCategory.OBSERVE,
        description="Tail application logs in real-time",
        purpose="Monitor log output during execution for debugging",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "optional": True},
                "lines": {"type": "integer", "default": 200},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "logs": {"type": "array", "items": {"type": "string"}},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.READ,
        tags=["runtime", "observation", "logging"],
    ))
    
    registry.register(ToolManifest(
        name="read_recent_exceptions",
        category=ToolCategory.OBSERVE,
        description="Read recent exception stack traces",
        purpose="Capture error context for debugging",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "optional": True},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "exceptions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "message": {"type": "string"},
                            "traceback": {"type": "string"},
                            "timestamp": {"type": "string"},
                        },
                    },
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.READ,
        tags=["runtime", "observation", "exceptions"],
    ))
    
    registry.register(ToolManifest(
        name="analyze_environment",
        category=ToolCategory.ANALYZE,
        description="Analyze the current system environment",
        purpose="Discover available runtimes, tools, and services",
        input_schema={
            "type": "object",
            "properties": {
                "include_gpu": {"type": "boolean", "default": False},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "os": {"type": "string"},
                "python_versions": {"type": "array", "items": {"type": "string"}},
                "node_versions": {"type": "array", "items": {"type": "string"}},
                "package_managers": {"type": "array", "items": {"type": "string"}},
                "installed_tools": {"type": "array", "items": {"type": "string"}},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["environment", "system-analysis"],
    ))
    
    # Dependency scanning
    registry.register(ToolManifest(
        name="scan_dependencies",
        category=ToolCategory.SECURITY,
        description="Scan project dependencies for issues",
        purpose="Check for outdated, insecure, or conflicting packages",
        input_schema={
            "type": "object",
            "properties": {
                "package_managers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "optional": True,
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "dependencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "current_version": {"type": "string"},
                            "latest_version": {"type": "string"},
                            "vulnerabilities": {"type": "array"},
                        },
                    },
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["security", "dependencies", "scanning"],
    ))
    
    # Failure memory
    registry.register(ToolManifest(
        name="record_failure_pattern",
        category=ToolCategory.MEMORY,
        description="Record a failure pattern and its resolution",
        purpose="Store institutional knowledge about fixes",
        input_schema={
            "type": "object",
            "properties": {
                "error_signature": {"type": "string"},
                "context": {"type": "object"},
                "resolution": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["error_signature", "resolution"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "pattern_id": {"type": "string"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.WRITE,
        tags=["memory", "failure-patterns"],
    ))
    
    registry.register(ToolManifest(
        name="search_failure_patterns",
        category=ToolCategory.MEMORY,
        description="Search failure pattern database",
        purpose="Find known fixes for similar errors",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "patterns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "error_signature": {"type": "string"},
                            "resolution": {"type": "string"},
                            "frequency": {"type": "integer"},
                        },
                    },
                },
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["memory", "failure-patterns"],
    ))
    
    # Cost optimization
    registry.register(ToolManifest(
        name="estimate_llm_cost",
        category=ToolCategory.ROUTING,
        description="Estimate LLM cost for a task",
        purpose="Predict token usage before executing",
        input_schema={
            "type": "object",
            "properties": {
                "task_description": {"type": "string"},
                "model": {"type": "string", "optional": True},
            },
            "required": ["task_description"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "estimated_tokens": {"type": "integer"},
                "estimated_cost": {"type": "number"},
                "recommended_model": {"type": "string"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["cost", "routing", "optimization"],
    ))
    
    registry.register(ToolManifest(
        name="recommend_model_for_stage",
        category=ToolCategory.ROUTING,
        description="Recommend optimal model for agent stage",
        purpose="Select best model based on task type and risk",
        input_schema={
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "enum": ["planner", "coder", "reviewer", "debugger"],
                },
                "task_type": {"type": "string"},
                "risk_level": {"type": "string"},
            },
            "required": ["stage"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "recommended_model": {"type": "string"},
                "fallback_model": {"type": "string"},
                "reasoning": {"type": "string"},
            },
        },
        risk_level=RiskLevel.LOW,
        side_effect=SideEffectLevel.NONE,
        tags=["cost", "routing", "optimization"],
    ))
