"""Data Models for Software State Model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SymbolKind(Enum):
    """Kind of symbol."""
    
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    PROPERTY = "property"
    CONSTANT = "constant"
    VARIABLE = "variable"
    MODULE = "module"
    PARAMETER = "parameter"
    TYPE = "type"
    INTERFACE = "interface"
    ENUM = "enum"


class Visibility(Enum):
    """Symbol visibility."""
    
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


class PackageManager(Enum):
    """Package manager types."""
    
    PIP = "pip"
    NPM = "npm"
    CARGO = "cargo"
    GO = "go"
    MAVEN = "maven"
    GRADLE = "gradle"
    COMPOSER = "composer"


@dataclass(frozen=True)
class Symbol:
    """Represents a code symbol (function, class, constant, etc.)."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    name: str = ""
    kind: SymbolKind = SymbolKind.FUNCTION
    visibility: Visibility = Visibility.PUBLIC
    
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    
    signature: str = ""
    docstring: str = ""
    
    # For classes: base class names
    bases: tuple[str, ...] = ()
    
    # Decorators/annotations
    decorators: tuple[str, ...] = ()
    
    # Namespace/path
    module_path: str = ""
    qualified_name: str = ""
    
    # Metadata
    is_async: bool = False
    is_override: bool = False
    is_test: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "visibility": self.visibility.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "signature": self.signature,
            "qualified_name": self.qualified_name,
            "is_async": self.is_async,
            "is_test": self.is_test,
        }


@dataclass(frozen=True)
class FileInfo:
    """Information about a source file."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    path: str = ""
    hash: str = ""
    language: str = ""
    line_count: int = 0
    
    last_modified: datetime | None = None
    size_bytes: int = 0
    
    # Extracted metadata
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()  # Symbol qualified names
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "language": self.language,
            "line_count": self.line_count,
            "import_count": len(self.imports),
            "symbol_count": len(self.symbols),
        }


@dataclass(frozen=True)
class Import:
    """An import statement."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    file_id: int = 0
    file_path: str = ""
    
    module_path: str = ""
    imported_names: tuple[str, ...] = ()
    alias: str | None = None
    
    is_wildcard: bool = False
    is_relative: bool = False
    level: int = 0  # 0 for absolute, 1+ for relative
    
    line: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "module_path": self.module_path,
            "imported_names": list(self.imported_names),
            "is_wildcard": self.is_wildcard,
            "is_relative": self.is_relative,
        }


@dataclass(frozen=True)
class CallEdge:
    """An edge in the call graph."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    caller_id: int = 0
    caller_name: str = ""
    caller_path: str = ""
    
    callee_id: int = 0
    callee_name: str = ""
    callee_path: str = ""
    
    call_type: str = "direct"  # direct, dynamic, indirect
    line: int = 0


@dataclass(frozen=True)
class InheritanceEdge:
    """An inheritance relationship."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    child_id: int = 0
    child_name: str = ""
    child_path: str = ""
    
    parent_id: int = 0
    parent_name: str = ""
    parent_path: str = ""


@dataclass(frozen=True)
class TestMapping:
    """Maps a test to the code it tests."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    test_file_path: str = ""
    test_name: str = ""
    
    target_symbol_id: int | None = None
    target_symbol_name: str = ""
    target_file_path: str = ""
    
    mapping_method: str = "naming"  # naming, coverage, import, heuristic
    confidence: float = 0.0
    
    # For heuristic matching
    related_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class APIContract:
    """API endpoint contract."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    file_path: str = ""
    handler_symbol: str = ""
    
    method: str = ""
    path: str = ""
    
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    
    auth_required: bool = False
    middleware: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dependency:
    """A package dependency."""
    
    id: int | None = None
    repo_snapshot_id: str = ""
    
    package_manager: PackageManager = PackageManager.PIP
    
    package_name: str = ""
    version_spec: str = ""  # e.g., ">=1.0.0,<2.0.0"
    installed_version: str = ""
    latest_version: str = ""
    
    is_dev: bool = False
    is_optional: bool = False
    
    file_path: str | None = None
    
    # Vulnerability info
    has_vulnerabilities: bool = False
    vulnerabilities: tuple[str, ...] = ()


@dataclass
class SnapshotInfo:
    """Information about a state model snapshot."""
    
    snapshot_id: str
    repo_path: str
    created_at: datetime
    
    file_count: int = 0
    symbol_count: int = 0
    import_count: int = 0
    call_edge_count: int = 0
    test_mapping_count: int = 0
    
    languages: tuple[str, ...] = ()
    
    is_current: bool = True
    parent_snapshot_id: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "repo_path": self.repo_path,
            "created_at": self.created_at.isoformat(),
            "file_count": self.file_count,
            "symbol_count": self.symbol_count,
            "languages": list(self.languages),
            "is_current": self.is_current,
        }


@dataclass
class ImpactReport:
    """Report predicting the impact of a change."""
    
    target: str
    change_description: str
    
    files_affected: list[str] = field(default_factory=list)
    symbols_affected: list[str] = field(default_factory=list)
    tests_affected: list[str] = field(default_factory=list)
    
    config_impact: list[str] = field(default_factory=list)
    api_breaking: bool = False
    
    risk_score: float = 0.0
    risk_factors: list[str] = field(default_factory=list)
    
    estimated_blast_radius: str = "low"
    
    recommended_actions: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "files_affected": self.files_affected,
            "symbols_affected": self.symbols_affected,
            "tests_affected": self.tests_affected,
            "risk_score": self.risk_score,
            "api_breaking": self.api_breaking,
            "recommended_actions": self.recommended_actions,
        }
