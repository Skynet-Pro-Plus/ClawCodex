"""Storage - SQLite-backed storage for software state model."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Iterator

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
    PackageManager,
    SnapshotInfo,
)


class StateModelStorage:
    """SQLite-backed storage for software state model.
    
    Provides thread-safe access to the code knowledge graph.
    """
    
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path or self._default_db_path()
        self._local = threading.local()
        self._init_db()
    
    @staticmethod
    def _default_db_path() -> Path:
        """Get default database path."""
        return Path.home() / ".claw-engine" / "state_model.db"
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            schema = schema_path.read_text()
        else:
            schema = self._get_inline_schema()
        
        with self.transaction() as conn:
            conn.executescript(schema)
    
    @staticmethod
    def _get_inline_schema() -> str:
        """Inline schema as fallback."""
        return """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT UNIQUE NOT NULL,
            repo_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_count INTEGER DEFAULT 0,
            symbol_count INTEGER DEFAULT 0,
            import_count INTEGER DEFAULT 0,
            call_edge_count INTEGER DEFAULT 0,
            test_mapping_count INTEGER DEFAULT 0,
            languages TEXT,
            is_current BOOLEAN DEFAULT 1,
            parent_snapshot_id TEXT
        );
        
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_snapshot_id TEXT NOT NULL,
            path TEXT NOT NULL,
            hash TEXT NOT NULL,
            language TEXT,
            line_count INTEGER DEFAULT 0,
            last_modified TIMESTAMP,
            size_bytes INTEGER DEFAULT 0,
            imports TEXT,
            exports TEXT,
            symbols TEXT
        );
        
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_snapshot_id TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            visibility TEXT DEFAULT 'public',
            file_path TEXT NOT NULL,
            line_start INTEGER,
            line_end INTEGER,
            signature TEXT,
            docstring TEXT,
            bases TEXT,
            decorators TEXT,
            module_path TEXT,
            qualified_name TEXT,
            is_async BOOLEAN DEFAULT 0,
            is_override BOOLEAN DEFAULT 0,
            is_test BOOLEAN DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_snapshot_id TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            module_path TEXT NOT NULL,
            imported_names TEXT,
            alias TEXT,
            is_wildcard BOOLEAN DEFAULT 0,
            is_relative BOOLEAN DEFAULT 0,
            level INTEGER DEFAULT 0,
            line INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_snapshot_id TEXT NOT NULL,
            caller_id INTEGER NOT NULL,
            caller_name TEXT NOT NULL,
            caller_path TEXT NOT NULL,
            callee_id INTEGER NOT NULL,
            callee_name TEXT NOT NULL,
            callee_path TEXT NOT NULL,
            call_type TEXT DEFAULT 'direct',
            line INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS test_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_snapshot_id TEXT NOT NULL,
            test_file_path TEXT NOT NULL,
            test_name TEXT NOT NULL,
            target_symbol_id INTEGER,
            target_symbol_name TEXT,
            target_file_path TEXT,
            mapping_method TEXT DEFAULT 'naming',
            confidence REAL DEFAULT 0.0,
            related_symbols TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
        CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
        CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_name, caller_path);
        CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_name, callee_path);
        """
    
    # Snapshot operations
    
    def create_snapshot(self, repo_path: str, parent_id: str | None = None) -> str:
        """Create a new snapshot."""
        import uuid
        snapshot_id = uuid.uuid4().hex
        
        with self.transaction() as conn:
            # Mark previous snapshots as not current
            conn.execute(
                "UPDATE snapshots SET is_current = 0 WHERE repo_path = ?",
                (repo_path,)
            )
            
            conn.execute("""
                INSERT INTO snapshots (snapshot_id, repo_path, parent_snapshot_id)
                VALUES (?, ?, ?)
            """, (snapshot_id, repo_path, parent_id))
        
        return snapshot_id
    
    def get_current_snapshot(self, repo_path: str) -> SnapshotInfo | None:
        """Get the current snapshot for a repo."""
        with self.transaction() as conn:
            row = conn.execute("""
                SELECT * FROM snapshots 
                WHERE repo_path = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
            """, (repo_path,)).fetchone()
        
        if row:
            return self._row_to_snapshot(row)
        return None
    
    # Symbol operations
    
    def insert_symbol(self, symbol: Symbol) -> int:
        """Insert a symbol and return its ID."""
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO symbols (
                    repo_snapshot_id, file_id, name, kind, visibility,
                    file_path, line_start, line_end, signature, docstring,
                    bases, decorators, module_path, qualified_name,
                    is_async, is_override, is_test
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol.repo_snapshot_id,
                symbol.file_path,  # file_id is file_path for now
                symbol.name,
                symbol.kind.value,
                symbol.visibility.value,
                symbol.file_path,
                symbol.line_start,
                symbol.line_end,
                symbol.signature,
                symbol.docstring,
                json.dumps(list(symbol.bases)),
                json.dumps(list(symbol.decorators)),
                symbol.module_path,
                symbol.qualified_name,
                symbol.is_async,
                symbol.is_override,
                symbol.is_test,
            ))
            return cursor.lastrowid
    
    def get_symbol(self, qualified_name: str, snapshot_id: str) -> Symbol | None:
        """Get a symbol by qualified name."""
        with self.transaction() as conn:
            row = conn.execute("""
                SELECT * FROM symbols 
                WHERE qualified_name = ? AND repo_snapshot_id = ?
                LIMIT 1
            """, (qualified_name, snapshot_id)).fetchone()
        
        if row:
            return self._row_to_symbol(row)
        return None
    
    def find_symbols(self, pattern: str, snapshot_id: str) -> list[Symbol]:
        """Find symbols matching a pattern."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM symbols 
                WHERE repo_snapshot_id = ? AND (
                    name LIKE ? OR qualified_name LIKE ?
                )
            """, (snapshot_id, f"%{pattern}%", f"%{pattern}%"))
        
        return [self._row_to_symbol(row) for row in rows]
    
    def get_symbols_in_file(self, file_path: str, snapshot_id: str) -> list[Symbol]:
        """Get all symbols in a file."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM symbols 
                WHERE file_path = ? AND repo_snapshot_id = ?
                ORDER BY line_start
            """, (file_path, snapshot_id))
        
        return [self._row_to_symbol(row) for row in rows]
    
    # Call graph operations
    
    def insert_call_edge(self, edge: CallEdge) -> int:
        """Insert a call edge."""
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO calls (
                    repo_snapshot_id, caller_id, caller_name, caller_path,
                    callee_id, callee_name, callee_path, call_type, line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                edge.repo_snapshot_id,
                edge.caller_id,
                edge.caller_name,
                edge.caller_path,
                edge.callee_id,
                edge.callee_name,
                edge.callee_path,
                edge.call_type,
                edge.line,
            ))
            return cursor.lastrowid
    
    def get_callers(self, symbol_name: str, file_path: str, snapshot_id: str) -> list[CallEdge]:
        """Get all callers of a symbol."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM calls 
                WHERE callee_name = ? AND callee_path = ? AND repo_snapshot_id = ?
            """, (symbol_name, file_path, snapshot_id))
        
        return [self._row_to_call_edge(row) for row in rows]
    
    def get_callees(self, symbol_name: str, file_path: str, snapshot_id: str) -> list[CallEdge]:
        """Get all callees of a symbol."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM calls 
                WHERE caller_name = ? AND caller_path = ? AND repo_snapshot_id = ?
            """, (symbol_name, file_path, snapshot_id))
        
        return [self._row_to_call_edge(row) for row in rows]
    
    # Test mapping operations
    
    def insert_test_mapping(self, mapping: TestMapping) -> int:
        """Insert a test mapping."""
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO test_mappings (
                    repo_snapshot_id, test_file_path, test_name,
                    target_symbol_id, target_symbol_name, target_file_path,
                    mapping_method, confidence, related_symbols
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mapping.repo_snapshot_id,
                mapping.test_file_path,
                mapping.test_name,
                mapping.target_symbol_id,
                mapping.target_symbol_name,
                mapping.target_file_path,
                mapping.mapping_method,
                mapping.confidence,
                json.dumps(list(mapping.related_symbols)),
            ))
            return cursor.lastrowid
    
    def get_tests_for_symbol(self, symbol_name: str, snapshot_id: str) -> list[TestMapping]:
        """Get tests that test a symbol."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM test_mappings 
                WHERE target_symbol_name = ? AND repo_snapshot_id = ?
                ORDER BY confidence DESC
            """, (symbol_name, snapshot_id))
        
        return [self._row_to_test_mapping(row) for row in rows]
    
    # File operations
    
    def insert_file(self, file_info: FileInfo) -> int:
        """Insert a file."""
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO files (
                    repo_snapshot_id, path, hash, language, line_count,
                    last_modified, size_bytes, imports, exports, symbols
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.repo_snapshot_id,
                file_info.path,
                file_info.hash,
                file_info.language,
                file_info.line_count,
                file_info.last_modified,
                file_info.size_bytes,
                json.dumps(list(file_info.imports)),
                json.dumps(list(file_info.exports)),
                json.dumps(list(file_info.symbols)),
            ))
            return cursor.lastrowid
    
    # Import operations
    
    def insert_import(self, imp: Import) -> int:
        """Insert an import."""
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO imports (
                    repo_snapshot_id, file_id, file_path, module_path,
                    imported_names, alias, is_wildcard, is_relative, level, line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                imp.repo_snapshot_id,
                imp.file_id,
                imp.file_path,
                imp.module_path,
                json.dumps(list(imp.imported_names)),
                imp.alias,
                imp.is_wildcard,
                imp.is_relative,
                imp.level,
                imp.line,
            ))
            return cursor.lastrowid
    
    def get_imports_for_file(self, file_path: str, snapshot_id: str) -> list[Import]:
        """Get imports for a file."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM imports 
                WHERE file_path = ? AND repo_snapshot_id = ?
            """, (file_path, snapshot_id))
        
        return [self._row_to_import(row) for row in rows]
    
    def get_modules_importing(self, module_path: str, snapshot_id: str) -> list[str]:
        """Get files that import a module."""
        with self.transaction() as conn:
            rows = conn.execute("""
                SELECT DISTINCT file_path FROM imports 
                WHERE module_path = ? AND repo_snapshot_id = ?
            """, (module_path, snapshot_id))
        
        return [row['file_path'] for row in rows]
    
    # Update snapshot stats
    
    def update_snapshot_stats(self, snapshot_id: str) -> None:
        """Update snapshot statistics."""
        with self.transaction() as conn:
            stats = conn.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM files WHERE repo_snapshot_id = ?) as file_count,
                    (SELECT COUNT(*) FROM symbols WHERE repo_snapshot_id = ?) as symbol_count,
                    (SELECT COUNT(*) FROM imports WHERE repo_snapshot_id = ?) as import_count,
                    (SELECT COUNT(*) FROM calls WHERE repo_snapshot_id = ?) as call_edge_count,
                    (SELECT COUNT(*) FROM test_mappings WHERE repo_snapshot_id = ?) as test_mapping_count
            """, (snapshot_id, snapshot_id, snapshot_id, snapshot_id, snapshot_id)).fetchone()
            
            languages = conn.execute("""
                SELECT DISTINCT language FROM files 
                WHERE repo_snapshot_id = ?
            """, (snapshot_id,)).fetchall()
            
            conn.execute("""
                UPDATE snapshots SET
                    file_count = ?,
                    symbol_count = ?,
                    import_count = ?,
                    call_edge_count = ?,
                    test_mapping_count = ?,
                    languages = ?
                WHERE snapshot_id = ?
            """, (
                stats['file_count'],
                stats['symbol_count'],
                stats['import_count'],
                stats['call_edge_count'],
                stats['test_mapping_count'],
                json.dumps([r['language'] for r in languages if r['language']]),
                snapshot_id,
            ))
    
    # Row conversion helpers
    
    def _row_to_snapshot(self, row: sqlite3.Row) -> SnapshotInfo:
        return SnapshotInfo(
            snapshot_id=row['snapshot_id'],
            repo_path=row['repo_path'],
            created_at=datetime.fromisoformat(row['created_at']),
            file_count=row['file_count'],
            symbol_count=row['symbol_count'],
            import_count=row['import_count'],
            call_edge_count=row['call_edge_count'],
            test_mapping_count=row['test_mapping_count'],
            languages=json.loads(row['languages'] or '[]'),
            is_current=bool(row['is_current']),
            parent_snapshot_id=row['parent_snapshot_id'],
        )
    
    def _row_to_symbol(self, row: sqlite3.Row) -> Symbol:
        return Symbol(
            id=row['id'],
            repo_snapshot_id=row['repo_snapshot_id'],
            name=row['name'],
            kind=SymbolKind(row['kind']),
            visibility=row['visibility'],
            file_path=row['file_path'],
            line_start=row['line_start'],
            line_end=row['line_end'],
            signature=row['signature'] or '',
            docstring=row['docstring'] or '',
            bases=tuple(json.loads(row['bases'] or '[]')),
            decorators=tuple(json.loads(row['decorators'] or '[]')),
            module_path=row['module_path'] or '',
            qualified_name=row['qualified_name'],
            is_async=bool(row['is_async']),
            is_override=bool(row['is_override']),
            is_test=bool(row['is_test']),
        )
    
    def _row_to_call_edge(self, row: sqlite3.Row) -> CallEdge:
        return CallEdge(
            id=row['id'],
            repo_snapshot_id=row['repo_snapshot_id'],
            caller_id=row['caller_id'],
            caller_name=row['caller_name'],
            caller_path=row['caller_path'],
            callee_id=row['callee_id'],
            callee_name=row['callee_name'],
            callee_path=row['callee_path'],
            call_type=row['call_type'],
            line=row['line'],
        )
    
    def _row_to_test_mapping(self, row: sqlite3.Row) -> TestMapping:
        return TestMapping(
            id=row['id'],
            repo_snapshot_id=row['repo_snapshot_id'],
            test_file_path=row['test_file_path'],
            test_name=row['test_name'],
            target_symbol_id=row['target_symbol_id'],
            target_symbol_name=row['target_symbol_name'],
            target_file_path=row['target_file_path'],
            mapping_method=row['mapping_method'],
            confidence=row['confidence'],
            related_symbols=tuple(json.loads(row['related_symbols'] or '[]')),
        )
    
    def _row_to_import(self, row: sqlite3.Row) -> Import:
        return Import(
            id=row['id'],
            repo_snapshot_id=row['repo_snapshot_id'],
            file_id=row['file_id'],
            file_path=row['file_path'],
            module_path=row['module_path'],
            imported_names=tuple(json.loads(row['imported_names'] or '[]')),
            alias=row['alias'],
            is_wildcard=bool(row['is_wildcard']),
            is_relative=bool(row['is_relative']),
            level=row['level'],
            line=row['line'],
        )


# Global storage instance
_global_storage: StateModelStorage | None = None
_storage_lock = threading.Lock()


def get_storage() -> StateModelStorage:
    """Get or create the global storage instance."""
    global _global_storage
    with _storage_lock:
        if _global_storage is None:
            _global_storage = StateModelStorage()
        return _global_storage
