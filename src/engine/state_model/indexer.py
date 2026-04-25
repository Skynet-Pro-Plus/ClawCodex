"""State Model Indexer - Main orchestrator for building the software state model."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    CallEdge,
    FileInfo,
    Import,
    SnapshotInfo,
    Symbol,
    SymbolKind,
    Visibility,
)
from .parsers import BaseParser, GenericParser, PythonParser
from .parsers.base import ParseResult, ParsedImport, ParsedSymbol
from .storage import StateModelStorage, get_storage


@dataclass
class IndexerConfig:
    """Configuration for the indexer."""
    
    # File patterns to include/exclude
    include_patterns: tuple[str, ...] = ("*.py", "*.pyi", "*.pyw")
    exclude_patterns: tuple[str, ...] = (
        "__pycache__",
        ".git",
        ".pytest_cache",
        "node_modules",
        "venv",
        ".venv",
        ".env",
        "*.pyc",
        ".tox",
        "dist",
        "build",
    )
    
    # Parallel processing
    max_workers: int = 4
    
    # Cache settings
    use_file_hash: bool = True
    
    # Language-specific parsers
    parsers: dict[str, type[BaseParser]] | None = None


class StateModelIndex:
    """Main indexer for building and maintaining the software state model.
    
    This class orchestrates the parsing of source files and building
    the code knowledge graph in SQLite storage.
    """
    
    def __init__(
        self,
        storage: StateModelStorage | None = None,
        config: IndexerConfig | None = None,
    ):
        self.storage = storage or get_storage()
        self.config = config or IndexerConfig()
        
        # Register default parsers
        self._parsers: dict[str, type[BaseParser]] = {
            ".py": PythonParser,
            ".pyi": PythonParser,
            ".pyw": PythonParser,
        }
        if self.config.parsers:
            self._parsers.update(self.config.parsers)
    
    def build(
        self,
        repo_path: str | Path,
        force_refresh: bool = False,
    ) -> SnapshotInfo:
        """Build a complete state model for the repository.
        
        Args:
            repo_path: Path to the repository root
            force_refresh: If True, rebuild even if model is current
            
        Returns:
            SnapshotInfo with metadata about the built snapshot
        """
        start_time = time.perf_counter()
        repo_path = Path(repo_path)
        
        # Check for existing current snapshot
        if not force_refresh:
            existing = self.storage.get_current_snapshot(str(repo_path))
            if existing:
                return existing
        
        # Create new snapshot
        parent = self.storage.get_current_snapshot(str(repo_path))
        snapshot_id = self.storage.create_snapshot(
            str(repo_path),
            parent_id=parent.snapshot_id if parent else None,
        )
        
        # Collect all source files
        files = self._collect_files(repo_path)
        
        # Parse files and build model
        all_symbols: list[ParsedSymbol] = []
        all_imports: list[tuple[str, ParsedImport]] = []  # (file_path, import)
        file_info_map: dict[str, FileInfo] = {}
        
        for file_path in files:
            result = self._parse_file(file_path)
            
            if result.errors and not result.symbols:
                # Skip files with only errors
                continue
            
            # Store file info
            file_hash = self._compute_file_hash(file_path)
            file_info = FileInfo(
                repo_snapshot_id=snapshot_id,
                path=str(file_path),
                hash=file_hash,
                language=result.language,
                line_count=len(result.content.split('\n')) if hasattr(result, 'content') else 0,
                imports=tuple(imp.module_path for imp in result.imports),
                exports=tuple(result.exports),
                symbols=tuple(s.qualified_name for s in result.symbols if s.qualified_name),
            )
            file_info_map[str(file_path)] = file_info
            self.storage.insert_file(file_info)
            
            # Collect symbols
            all_symbols.extend(result.symbols)
            
            # Collect imports
            for imp in result.imports:
                all_imports.append((str(file_path), imp))
        
        # Insert symbols
        symbol_id_map: dict[str, int] = {}  # qualified_name -> id
        for symbol in all_symbols:
            db_symbol = self._parsed_to_symbol(symbol, snapshot_id)
            symbol_id = self.storage.insert_symbol(db_symbol)
            if db_symbol.qualified_name:
                symbol_id_map[db_symbol.qualified_name] = symbol_id
        
        # Build call graph
        for symbol in all_symbols:
            for called_name in symbol.calls:
                # Find the called symbol
                callee = self._find_symbol_by_name(called_name, all_symbols)
                if callee:
                    caller_symbol = self._find_symbol_by_name(
                        symbol.qualified_name.split('.')[-1] if symbol.qualified_name else symbol.name,
                        all_symbols,
                    )
                    if caller_symbol and callee:
                        edge = CallEdge(
                            repo_snapshot_id=snapshot_id,
                            caller_id=symbol_id_map.get(symbol.qualified_name, 0),
                            caller_name=symbol.name,
                            caller_path=symbol.file_path,
                            callee_id=symbol_id_map.get(callee.qualified_name, 0),
                            callee_name=callee.name,
                            callee_path=callee.file_path,
                            call_type="direct",
                            line=0,
                        )
                        self.storage.insert_call_edge(edge)
        
        # Build test mappings
        for symbol in all_symbols:
            if symbol.is_test:
                # Find the symbol being tested
                test_name = symbol.name
                target_name = self._infer_test_target(test_name)
                if target_name:
                    target_symbol = self._find_symbol_by_name(target_name, all_symbols)
                    if target_symbol:
                        from .models import TestMapping
                        mapping = TestMapping(
                            repo_snapshot_id=snapshot_id,
                            test_file_path=symbol.file_path,
                            test_name=symbol.name,
                            target_symbol_name=target_symbol.name,
                            target_file_path=target_symbol.file_path,
                            mapping_method="naming",
                            confidence=0.8,
                        )
                        self.storage.insert_test_mapping(mapping)
        
        # Update snapshot stats
        self.storage.update_snapshot_stats(snapshot_id)
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Get final snapshot info
        return self.storage.get_current_snapshot(str(repo_path))
    
    def refresh(
        self,
        repo_path: str | Path,
        changed_files: list[str] | None = None,
    ) -> SnapshotInfo:
        """Refresh the state model for changed files.
        
        Args:
            repo_path: Path to the repository
            changed_files: Optional list of specific files that changed
            
        Returns:
            Updated SnapshotInfo
        """
        return self.build(repo_path, force_refresh=True)
    
    def _collect_files(self, repo_path: Path) -> list[Path]:
        """Collect all source files in the repository."""
        files = []
        
        for pattern in self.config.include_patterns:
            files.extend(repo_path.rglob(pattern))
        
        # Filter by exclude patterns
        filtered = []
        for f in files:
            path_str = str(f)
            if not any(excl in path_str for excl in self.config.exclude_patterns):
                filtered.append(f)
        
        return sorted(filtered)
    
    def _parse_file(self, file_path: Path) -> ParseResult:
        """Parse a single file using the appropriate parser."""
        ext = file_path.suffix.lower()
        
        parser_class = self._parsers.get(ext, GenericParser)
        parser = parser_class()
        
        try:
            return parser.parse(file_path)
        except Exception as e:
            return ParseResult(
                file_path=str(file_path),
                language="unknown",
                errors=[f"Parse error: {e}"],
            )
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        if not self.config.use_file_hash:
            return ""
        
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    
    def _parsed_to_symbol(
        self,
        parsed: ParsedSymbol,
        snapshot_id: str,
    ) -> Symbol:
        """Convert a ParsedSymbol to a database Symbol."""
        kind = SymbolKind.FUNCTION
        if parsed.kind == "class":
            kind = SymbolKind.CLASS
        elif parsed.kind == "method":
            kind = SymbolKind.METHOD
        elif parsed.kind == "constant":
            kind = SymbolKind.CONSTANT
        
        visibility = Visibility.PUBLIC
        if parsed.name.startswith('_'):
            visibility = Visibility.PRIVATE
        
        return Symbol(
            repo_snapshot_id=snapshot_id,
            name=parsed.name,
            kind=kind,
            visibility=visibility,
            file_path=parsed.file_path,
            line_start=parsed.line_start,
            line_end=parsed.line_end,
            signature=parsed.signature,
            docstring=parsed.docstring,
            bases=tuple(parsed.bases),
            decorators=tuple(parsed.decorators),
            module_path=parsed.module_path,
            qualified_name=parsed.qualified_name,
            is_async=parsed.is_async,
            is_override=parsed.is_override,
            is_test=parsed.is_test,
        )
    
    @staticmethod
    def _find_symbol_by_name(
        name: str,
        symbols: list[ParsedSymbol],
    ) -> ParsedSymbol | None:
        """Find a symbol by name."""
        name_lower = name.lower()
        for s in symbols:
            if s.name.lower() == name_lower:
                return s
            if s.qualified_name and s.qualified_name.lower().endswith(name_lower):
                return s
        return None
    
    @staticmethod
    def _infer_test_target(test_name: str) -> str | None:
        """Infer the target symbol from a test name."""
        # test_module_class_method -> module.class.method
        # test_class_method -> class.method
        # test_function -> function
        
        name = test_name
        
        # Remove test_ prefix
        if name.startswith('test_'):
            name = name[5:]
        elif name.startswith('Test'):
            name = name[4:]
        
        # Handle snake_case to PascalCase conversion
        parts = name.split('_')
        if len(parts) > 1:
            # Try to find original name
            return parts[-1]  # Last part is typically the method being tested
        
        return name if name else None


def build_state_model(
    repo_path: str | Path,
    force_refresh: bool = False,
) -> SnapshotInfo:
    """Convenience function to build a state model."""
    indexer = StateModelIndex()
    return indexer.build(repo_path, force_refresh=force_refresh)


def refresh_state_model(
    repo_path: str | Path,
    changed_files: list[str] | None = None,
) -> SnapshotInfo:
    """Convenience function to refresh a state model."""
    indexer = StateModelIndex()
    return indexer.refresh(repo_path, changed_files=changed_files)
