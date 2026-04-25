"""Graph Queries - Call graph, dependency analysis, and symbol reference queries."""

from __future__ import annotations

from typing import Any

from .models import CallEdge, Symbol
from .storage import StateModelStorage, get_storage


def get_callers(
    symbol_name: str,
    file_path: str | None = None,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[dict[str, Any]]:
    """Find all functions that call the target function.
    
    Args:
        symbol_name: Name of the function to find callers for
        file_path: Optional file path to narrow the search
        snapshot_id: Optional snapshot ID (uses current if None)
        storage: Optional storage instance
        
    Returns:
        List of caller information dicts
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        # Find most recent snapshot - would need repo_path
        snapshot_id = ""
    
    callers = store.get_callers(symbol_name, file_path or "", snapshot_id)
    
    return [
        {
            "name": c.caller_name,
            "file_path": c.caller_path,
            "line": c.line,
            "call_type": c.call_type,
        }
        for c in callers
    ]


def get_callees(
    symbol_name: str,
    file_path: str | None = None,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[dict[str, Any]]:
    """Find all functions called by the target function.
    
    Args:
        symbol_name: Name of the function to find callees for
        file_path: Optional file path to narrow the search
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        List of callee information dicts
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    callees = store.get_callees(symbol_name, file_path or "", snapshot_id)
    
    return [
        {
            "name": c.callee_name,
            "file_path": c.callee_path,
            "line": c.line,
            "call_type": c.call_type,
        }
        for c in callees
    ]


def get_call_graph(
    root_symbol: str,
    max_depth: int = 3,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> dict[str, Any]:
    """Build a call graph starting from a root symbol.
    
    Args:
        root_symbol: Starting symbol name
        max_depth: Maximum traversal depth
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        Dict with nodes and edges representing the call graph
    """
    store = storage or get_storage()
    visited: set[str] = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    
    def traverse(symbol: str, depth: int = 0):
        if depth >= max_depth:
            return
        if symbol in visited:
            return
        visited.add(symbol)
        
        # Add node
        nodes.append({
            "name": symbol,
            "depth": depth,
        })
        
        # Get callees
        callees = store.get_callees(symbol, "", snapshot_id or "")
        for callee in callees:
            edges.append({
                "from": symbol,
                "to": callee.callee_name,
                "file": callee.callee_path,
            })
            traverse(callee.callee_name, depth + 1)
    
    traverse(root_symbol)
    
    return {
        "root": root_symbol,
        "max_depth": max_depth,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def get_symbol_references(
    symbol_name: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[dict[str, Any]]:
    """Find all references to a symbol across the codebase.
    
    Args:
        symbol_name: Name of the symbol to find references for
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        List of reference location dicts
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    # Search by partial match
    symbols = store.find_symbols(symbol_name, snapshot_id)
    
    references = []
    for sym in symbols:
        # Find callers as references
        callers = store.get_callers(sym.name, sym.file_path, snapshot_id)
        for caller in callers:
            references.append({
                "type": "call",
                "file_path": caller.caller_path,
                "line": caller.line,
                "symbol": caller.caller_name,
            })
    
    return references


def get_module_dependencies(
    module_path: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> dict[str, Any]:
    """Get all dependencies of a module.
    
    Args:
        module_path: Module path (e.g., 'src.models.user')
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        Dict with imports and dev_imports
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    # Find files that match this module
    imports = store.get_imports_for_file(module_path, snapshot_id)
    
    return {
        "module": module_path,
        "imports": [i.module_path for i in imports],
        "import_count": len(imports),
    }


def get_reverse_dependencies(
    module_path: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> dict[str, Any]:
    """Find all modules that import or depend on the target module.
    
    Args:
        module_path: Module path to find dependents for
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        Dict with dependent modules
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    dependent_files = store.get_modules_importing(module_path, snapshot_id)
    
    return {
        "module": module_path,
        "dependents": dependent_files,
        "dependent_count": len(dependent_files),
    }


def find_dead_code(
    scope: str | None = None,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[dict[str, Any]]:
    """Find potentially dead code (unused symbols).
    
    Args:
        scope: Optional file path to limit scope
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        List of potentially dead code items
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    # This is a simplified implementation
    # A full implementation would track all symbol usages
    
    if scope:
        symbols = store.get_symbols_in_file(scope, snapshot_id)
    else:
        # Would need to iterate all files - simplified for now
        return []
    
    dead_code = []
    
    for sym in symbols:
        if sym.kind == "function" or sym.kind == "method":
            # Check if symbol has callers
            callers = store.get_callers(sym.name, sym.file_path, snapshot_id)
            if not callers and not sym.name.startswith('_'):
                dead_code.append({
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "file_path": sym.file_path,
                    "line": sym.line_start,
                    "kind": sym.kind,
                })
    
    return dead_code


def find_symbols_in_file(
    file_path: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[Symbol]:
    """Get all symbols defined in a file."""
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    return store.get_symbols_in_file(file_path, snapshot_id)


def search_symbols(
    pattern: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> list[Symbol]:
    """Search for symbols matching a pattern."""
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    return store.find_symbols(pattern, snapshot_id)
