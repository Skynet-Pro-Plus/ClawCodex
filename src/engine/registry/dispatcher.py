"""Tool Dispatcher - Unified invocation point for all engine tools."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from .tool_manifest import AuditEntry, ToolManifest
from .tool_registry import get_global_registry
from .result import ToolResult, ToolResultStatus


@dataclass
class DispatchContext:
    """Context for tool dispatch operations.
    
    Contains all metadata needed for tool execution including
    agent identification, permissions, and tracing.
    """
    
    agent_id: str
    task_id: str
    run_id: str = field(default_factory=lambda: uuid4().hex)
    parent_run_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Execution options
    timeout_sec: int | None = None
    skip_cache: bool = False
    dry_run: bool = False
    
    # Permissions
    allowed_paths: list[str] | None = None
    denied_paths: list[str] | None = None
    elevated_permissions: bool = False


@dataclass
class ToolExecutor:
    """Executor for a specific tool implementation."""
    
    manifest: ToolManifest
    handler: Callable[..., Any]
    
    def execute(self, arguments: dict[str, Any], context: DispatchContext) -> ToolResult:
        """Execute the tool with given arguments."""
        start_time = time.perf_counter()
        
        try:
            result_data = self.handler(**arguments)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            return ToolResult(
                ok=True,
                tool_name=self.manifest.name,
                data=result_data,
                warnings=[],
                errors=[],
                artifacts=[],
                timing_ms=elapsed_ms,
                cache_key=self._compute_cache_key(arguments),
                replayable=self.manifest.replayable,
                audit_trail=self._create_audit_entry(
                    context, arguments, result_data
                ),
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                ok=False,
                tool_name=self.manifest.name,
                data=None,
                warnings=[],
                errors=[str(e)],
                artifacts=[],
                timing_ms=elapsed_ms,
                cache_key="",
                replayable=False,
                audit_trail=self._create_audit_entry(context, arguments, None),
                status=ToolResultStatus.ERROR,
            )
    
    def _compute_cache_key(self, arguments: dict[str, Any]) -> str:
        """Compute cache key for tool result."""
        content = json.dumps(arguments, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _create_audit_entry(
        self,
        context: DispatchContext,
        arguments: dict[str, Any],
        result: Any,
    ) -> AuditEntry:
        """Create audit trail entry."""
        args_hash = self._compute_cache_key(arguments)
        result_str = json.dumps(result, sort_keys=True, default=str)
        result_hash = hashlib.sha256(result_str.encode()).hexdigest()[:16]
        
        return AuditEntry(
            timestamp=context.timestamp,
            agent_id=context.agent_id,
            task_id=context.task_id,
            run_id=context.run_id,
            tool_name=self.manifest.name,
            arguments_hash=args_hash,
            result_hash=result_hash,
            parent_run_id=context.parent_run_id,
        )


class Dispatcher:
    """Central dispatcher for all tool invocations.
    
    This is the single entry point for ALL tool execution in the engine.
    It handles:
    - Tool lookup and validation
    - Permission checking
    - Path/command restrictions
    - Timeout enforcement
    - Result caching
    - Audit logging
    """
    
    def __init__(self):
        self._executors: dict[str, ToolExecutor] = {}
        self._cache: dict[str, tuple[ToolResult, float]] = {}
        self._cache_ttl_sec: float = 300  # 5 minutes default
        self._lock = threading.RLock()
        self._implementations: dict[str, Callable] = {}
    
    def register_implementation(
        self,
        tool_name: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register a tool implementation handler."""
        with self._lock:
            self._implementations[tool_name] = handler
    
    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: DispatchContext,
    ) -> ToolResult:
        """Invoke a tool by name with given arguments."""
        registry = get_global_registry()
        manifest = registry.get(tool_name)
        
        if manifest is None:
            return ToolResult(
                ok=False,
                tool_name=tool_name,
                data=None,
                warnings=[],
                errors=[f"Tool not found: {tool_name}"],
                artifacts=[],
                timing_ms=0,
                cache_key="",
                replayable=False,
                status=ToolResultStatus.NOT_FOUND,
            )
        
        # Check permissions
        permission_result = self._check_permissions(manifest, arguments, context)
        if not permission_result.ok:
            return permission_result
        
        # Check confirmation requirement
        if manifest.requires_confirmation and not context.elevated_permissions:
            return ToolResult(
                ok=False,
                tool_name=tool_name,
                data=None,
                warnings=[],
                errors=[f"Tool requires confirmation: {manifest.confirmation_reason or 'User confirmation needed'}"],
                artifacts=[],
                timing_ms=0,
                cache_key="",
                replayable=False,
                status=ToolResultStatus.REQUIRES_CONFIRMATION,
            )
        
        # Check cache
        if not context.skip_cache and manifest.cacheable:
            cached = self._get_from_cache(tool_name, arguments)
            if cached is not None:
                return cached
        
        # Get or create executor
        executor = self._get_executor(manifest)
        
        # Execute with timeout
        result = self._execute_with_timeout(
            executor, arguments, context,
            manifest.timeout_sec if context.timeout_sec is None else context.timeout_sec
        )
        
        # Cache result
        if result.ok and manifest.cacheable and not context.skip_cache:
            self._put_in_cache(tool_name, arguments, result)
        
        return result
    
    def _get_executor(self, manifest: ToolManifest) -> ToolExecutor:
        """Get or create executor for tool."""
        with self._lock:
            if manifest.name not in self._executors:
                handler = self._implementations.get(manifest.name)
                if handler is None:
                    handler = self._default_handler
                
                self._executors[manifest.name] = ToolExecutor(manifest, handler)
            
            return self._executors[manifest.name]
    
    def _execute_with_timeout(
        self,
        executor: ToolExecutor,
        arguments: dict[str, Any],
        context: DispatchContext,
        timeout_sec: int,
    ) -> ToolResult:
        """Execute tool with timeout enforcement."""
        result_holder = [None]
        exception_holder = [None]
        
        def execute():
            try:
                result_holder[0] = executor.execute(arguments, context)
            except Exception as e:
                exception_holder[0] = e
        
        thread = threading.Thread(target=execute)
        thread.start()
        thread.join(timeout=timeout_sec)
        
        if thread.is_alive():
            return ToolResult(
                ok=False,
                tool_name=executor.manifest.name,
                data=None,
                warnings=[],
                errors=[f"Tool execution timed out after {timeout_sec}s"],
                artifacts=[],
                timing_ms=timeout_sec * 1000,
                cache_key="",
                replayable=False,
                status=ToolResultStatus.TIMEOUT,
            )
        
        if exception_holder[0] is not None:
            return ToolResult(
                ok=False,
                tool_name=executor.manifest.name,
                data=None,
                warnings=[],
                errors=[f"Execution error: {str(exception_holder[0])}"],
                artifacts=[],
                timing_ms=0,
                cache_key="",
                replayable=False,
                status=ToolResultStatus.ERROR,
            )
        
        return result_holder[0]
    
    def _default_handler(self, **kwargs: Any) -> Any:
        """Default handler when no implementation is registered."""
        return {"status": "not_implemented", "arguments": kwargs}
    
    def _check_permissions(
        self,
        manifest: ToolManifest,
        arguments: dict[str, Any],
        context: DispatchContext,
    ) -> ToolResult:
        """Check if tool execution is permitted."""
        # Check tool-level restrictions
        if manifest.allowed_paths and context.allowed_paths:
            combined = set(manifest.allowed_paths) & set(context.allowed_paths)
            if not combined:
                return ToolResult(
                    ok=False,
                    tool_name=manifest.name,
                    data=None,
                    warnings=[],
                    errors=["No allowed paths in common"],
                    artifacts=[],
                    timing_ms=0,
                    cache_key="",
                    replayable=False,
                    status=ToolResultStatus.PERMISSION_DENIED,
                )
        
        # Check denied paths
        if manifest.denied_paths:
            for path in context.allowed_paths or []:
                for denied in manifest.denied_paths:
                    if path.startswith(denied):
                        return ToolResult(
                            ok=False,
                            tool_name=manifest.name,
                            data=None,
                            warnings=[],
                            errors=[f"Path {path} is denied"],
                            artifacts=[],
                            timing_ms=0,
                            cache_key="",
                            replayable=False,
                            status=ToolResultStatus.PERMISSION_DENIED,
                        )
        
        return ToolResult(
            ok=True,
            tool_name=manifest.name,
            data=None,
            warnings=[],
            errors=[],
            artifacts=[],
            timing_ms=0,
            cache_key="",
            replayable=True,
        )
    
    def _get_from_cache(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
        """Get cached result if available and not expired."""
        with self._lock:
            cache_key = self._compute_key(tool_name, arguments)
            if cache_key in self._cache:
                result, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self._cache_ttl_sec:
                    return result
                else:
                    del self._cache[cache_key]
            return None
    
    def _put_in_cache(self, tool_name: str, arguments: dict[str, Any], result: ToolResult) -> None:
        """Cache a successful result."""
        with self._lock:
            cache_key = self._compute_key(tool_name, arguments)
            self._cache[cache_key] = (result, time.time())
    
    def _compute_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Compute cache key."""
        content = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


# Global dispatcher instance
_global_dispatcher: Dispatcher | None = None
_dispatcher_lock = threading.Lock()


def get_dispatcher() -> Dispatcher:
    """Get or create the global dispatcher."""
    global _global_dispatcher
    with _dispatcher_lock:
        if _global_dispatcher is None:
            _global_dispatcher = Dispatcher()
            _register_default_implementations(_global_dispatcher)
        return _global_dispatcher


def invoke_tool(
    tool_name: str,
    arguments: dict[str, Any],
    agent_id: str,
    task_id: str,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """Invoke a tool with standard context.
    
    This is the main entry point for tool invocation.
    
    Args:
        tool_name: Name of the tool to invoke
        arguments: Tool-specific arguments
        agent_id: ID of the agent invoking the tool
        task_id: ID of the current task
        run_id: Unique ID for this execution run
        parent_run_id: ID of parent execution for tracing
        **kwargs: Additional context options
        
    Returns:
        ToolResult with execution outcome
    """
    context = DispatchContext(
        agent_id=agent_id,
        task_id=task_id,
        run_id=run_id or uuid4().hex,
        parent_run_id=parent_run_id,
        **kwargs,
    )
    return get_dispatcher().invoke(tool_name, arguments, context)


def _register_default_implementations(dispatcher: Dispatcher) -> None:
    """Register default tool implementations."""
    from ..state_model import StateModelIndex
    
    # Register a placeholder for state model build
    # Real implementations will be in state_model module
    pass
