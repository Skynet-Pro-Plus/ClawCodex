"""Software State Model - Code intelligence and symbol tracking.

This module provides the core intelligence layer for the Claw Code engine.
It builds and maintains a continuously updated model of the software system.

Key Components:
- StateModelIndex: Main indexer that builds the software model
- Storage: SQLite-backed storage for code metadata
- Parsers: Language-specific parsers for symbol extraction
- GraphQueries: Call graph, dependency analysis, symbol references
- TestMapper: Maps tests to code symbols for targeted testing
"""

from .indexer import StateModelIndex, build_state_model, refresh_state_model
from .storage import StateModelStorage, get_storage
from .models import (
    Symbol,
    SymbolKind,
    FileInfo,
    Import,
    CallEdge,
    InheritanceEdge,
    TestMapping,
    APIContract,
    Dependency,
    SnapshotInfo,
)
from .graph_queries import (
    get_callers,
    get_callees,
    get_call_graph,
    get_symbol_references,
    get_module_dependencies,
    get_reverse_dependencies,
    find_dead_code,
    search_symbols,
)
from .test_mapper import (
    find_tests_for_symbol,
    find_tests_for_file,
    find_tests_for_change,
    rank_tests_by_relevance,
)

__all__ = [
    # Main classes
    "StateModelIndex",
    "StateModelStorage",
    # Build functions
    "build_state_model",
    "refresh_state_model",
    "get_storage",
    # Data models
    "Symbol",
    "SymbolKind",
    "FileInfo",
    "Import",
    "CallEdge",
    "InheritanceEdge",
    "TestMapping",
    "APIContract",
    "Dependency",
    "SnapshotInfo",
    # Graph queries
    "get_callers",
    "get_callees",
    "get_call_graph",
    "get_symbol_references",
    "get_module_dependencies",
    "get_reverse_dependencies",
    "find_dead_code",
    "search_symbols",
    # Test mapping
    "find_tests_for_symbol",
    "find_tests_for_file",
    "find_tests_for_change",
    "rank_tests_by_relevance",
]
