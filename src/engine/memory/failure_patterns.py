"""Failure Pattern Database - Persistent memory of failures and their fixes."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FailurePattern:
    """A recorded failure pattern with resolution.
    
    Attributes:
        id: Unique pattern identifier
        error_signature: Normalized error signature for matching
        exception_type: Type of exception
        error_message: Error message pattern
        top_frames: Top stack frames
        repo_snapshot: Repository state when failure occurred
        environment: Environment info
        resolution: How this was fixed
        evidence: Evidence of successful fix
        tags: Categorization tags
        frequency: How often this pattern has occurred
        first_seen: When first seen
        last_seen: When last seen
    """
    
    id: str
    error_signature: str
    exception_type: str
    error_message: str
    top_frames: list[str] = field(default_factory=list)
    repo_snapshot: str = ""
    environment: dict[str, Any] = field(default_factory=dict)
    resolution: str = ""
    evidence: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    frequency: int = 1
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "error_signature": self.error_signature,
            "exception_type": self.exception_type,
            "error_message": self.error_message,
            "top_frames": self.top_frames,
            "repo_snapshot": self.repo_snapshot,
            "environment": self.environment,
            "resolution": self.resolution,
            "evidence": self.evidence,
            "tags": self.tags,
            "frequency": self.frequency,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


class FailurePatternDB:
    """Database of failure patterns and their resolutions.
    
    This class provides persistent storage for failure patterns,
    enabling "I have seen this before" behavior.
    """
    
    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS failure_patterns (
            id TEXT PRIMARY KEY,
            error_signature TEXT NOT NULL,
            exception_type TEXT,
            error_message TEXT,
            top_frames TEXT,
            repo_snapshot TEXT,
            environment TEXT,
            resolution TEXT,
            evidence TEXT,
            tags TEXT,
            frequency INTEGER DEFAULT 1,
            first_seen TEXT,
            last_seen TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_error_signature ON failure_patterns(error_signature);
        CREATE INDEX IF NOT EXISTS idx_exception_type ON failure_patterns(exception_type);
    """
    
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            # Use a default location in the engine directory
            db_path = Path(__file__).parent.parent.parent / "memdir" / "failure_patterns.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database."""
        with self._lock:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.executescript(self._create_table_sql)
            self._conn.commit()
    
    def _ensure_connection(self) -> None:
        """Ensure database connection is active."""
        if self._conn is None:
            self._init_db()
    
    def insert(self, pattern: FailurePattern) -> str:
        """Insert a new failure pattern.
        
        Args:
            pattern: FailurePattern to insert
            
        Returns:
            Pattern ID
        """
        with self._lock:
            self._ensure_connection()
            
            self._conn.execute(
                """
                INSERT OR REPLACE INTO failure_patterns
                (id, error_signature, exception_type, error_message, top_frames,
                 repo_snapshot, environment, resolution, evidence, tags,
                 frequency, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern.id,
                    pattern.error_signature,
                    pattern.exception_type,
                    pattern.error_message,
                    json.dumps(pattern.top_frames),
                    pattern.repo_snapshot,
                    json.dumps(pattern.environment),
                    pattern.resolution,
                    json.dumps(pattern.evidence),
                    json.dumps(pattern.tags),
                    pattern.frequency,
                    pattern.first_seen.isoformat(),
                    pattern.last_seen.isoformat(),
                ),
            )
            self._conn.commit()
            
            return pattern.id
    
    def search(
        self,
        query: str | None = None,
        exception_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[FailurePattern]:
        """Search for failure patterns.
        
        Args:
            query: Text search query
            exception_type: Filter by exception type
            tags: Filter by tags
            limit: Maximum results
            
        Returns:
            List of matching FailurePattern objects
        """
        with self._lock:
            self._ensure_connection()
            
            conditions = []
            params: list[Any] = []
            
            if query:
                conditions.append("(error_signature LIKE ? OR error_message LIKE ? OR resolution LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])
            
            if exception_type:
                conditions.append("exception_type = ?")
                params.append(exception_type)
            
            if tags:
                for tag in tags:
                    conditions.append("tags LIKE ?")
                    params.append(f"%\"{tag}\"%")
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            cursor = self._conn.execute(
                f"""
                SELECT id, error_signature, exception_type, error_message, top_frames,
                       repo_snapshot, environment, resolution, evidence, tags,
                       frequency, first_seen, last_seen
                FROM failure_patterns
                {where_clause}
                ORDER BY frequency DESC, last_seen DESC
                LIMIT ?
                """,
                params + [limit],
            )
            
            patterns = []
            for row in cursor.fetchall():
                patterns.append(FailurePattern(
                    id=row[0],
                    error_signature=row[1],
                    exception_type=row[2] or "",
                    error_message=row[3] or "",
                    top_frames=json.loads(row[4]) if row[4] else [],
                    repo_snapshot=row[5] or "",
                    environment=json.loads(row[6]) if row[6] else {},
                    resolution=row[7] or "",
                    evidence=json.loads(row[8]) if row[8] else [],
                    tags=json.loads(row[9]) if row[9] else [],
                    frequency=row[10],
                    first_seen=datetime.fromisoformat(row[11]),
                    last_seen=datetime.fromisoformat(row[12]),
                ))
            
            return patterns
    
    def find_similar(
        self,
        error_signature: str,
        threshold: float = 0.8,
    ) -> list[FailurePattern]:
        """Find patterns with similar error signatures.
        
        Args:
            error_signature: Error signature to match
            threshold: Similarity threshold (0.0 - 1.0)
            
        Returns:
            List of similar FailurePattern objects
        """
        with self._lock:
            self._ensure_connection()
            
            # Simple exact prefix match for now
            # A more sophisticated implementation would use fuzzy matching
            cursor = self._conn.execute(
                """
                SELECT id, error_signature, exception_type, error_message, top_frames,
                       repo_snapshot, environment, resolution, evidence, tags,
                       frequency, first_seen, last_seen
                FROM failure_patterns
                WHERE error_signature LIKE ?
                ORDER BY frequency DESC
                LIMIT 20
                """,
                (f"{error_signature[:50]}%",),
            )
            
            patterns = []
            for row in cursor.fetchall():
                patterns.append(FailurePattern(
                    id=row[0],
                    error_signature=row[1],
                    exception_type=row[2] or "",
                    error_message=row[3] or "",
                    top_frames=json.loads(row[4]) if row[4] else [],
                    repo_snapshot=row[5] or "",
                    environment=json.loads(row[6]) if row[6] else {},
                    resolution=row[7] or "",
                    evidence=json.loads(row[8]) if row[8] else [],
                    tags=json.loads(row[9]) if row[9] else [],
                    frequency=row[10],
                    first_seen=datetime.fromisoformat(row[11]),
                    last_seen=datetime.fromisoformat(row[12]),
                ))
            
            return patterns
    
    def increment_frequency(self, pattern_id: str) -> None:
        """Increment the frequency count for a pattern.
        
        Args:
            pattern_id: Pattern to update
        """
        with self._lock:
            self._ensure_connection()
            
            self._conn.execute(
                """
                UPDATE failure_patterns
                SET frequency = frequency + 1, last_seen = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), pattern_id),
            )
            self._conn.commit()
    
    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


def extract_error_signature(
    exception_type: str,
    error_message: str,
    stack_frames: list[str],
) -> str:
    """Extract a normalized error signature.
    
    Args:
        exception_type: Type of exception
        error_message: Error message
        stack_frames: Top stack frames
        
    Returns:
        Normalized signature string
    """
    # Take first non-stdlib frame
    for frame in stack_frames:
        if not any(
            stdlib in frame
            for stdlib in ["site-packages", "python3", "lib/python", "\\lib\\"]
        ):
            return f"{exception_type}@{frame}"
    
    # Fallback to exception type + truncated message
    msg_hash = hashlib.md5(error_message[:200].encode()).hexdigest()[:8]
    return f"{exception_type}@{msg_hash}"


# Global pattern database
_pattern_db: FailurePatternDB | None = None
_db_lock = threading.Lock()


def get_pattern_db() -> FailurePatternDB:
    """Get or create the global pattern database."""
    global _pattern_db
    with _db_lock:
        if _pattern_db is None:
            _pattern_db = FailurePatternDB()
        return _pattern_db


def record_failure_pattern(
    error_signature: str,
    exception_type: str,
    error_message: str,
    stack_frames: list[str] | None = None,
    resolution: str = "",
    evidence: list[str] | None = None,
    tags: list[str] | None = None,
    repo_snapshot: str = "",
) -> dict[str, Any]:
    """Record a failure pattern.
    
    Args:
        error_signature: Normalized error signature
        exception_type: Type of exception
        error_message: Error message
        stack_frames: Stack frames from error
        resolution: How this was fixed
        evidence: Evidence of successful fix
        tags: Categorization tags
        repo_snapshot: Repository state
        
    Returns:
        Dict with pattern info
    """
    import uuid
    
    db = get_pattern_db()
    
    pattern = FailurePattern(
        id=uuid.uuid4().hex,
        error_signature=error_signature,
        exception_type=exception_type,
        error_message=error_message[:500],  # Truncate
        top_frames=stack_frames or [],
        resolution=resolution,
        evidence=evidence or [],
        tags=tags or [],
        repo_snapshot=repo_snapshot,
    )
    
    db.insert(pattern)
    
    return {
        "pattern_id": pattern.id,
        "error_signature": pattern.error_signature,
        "message": "Failure pattern recorded",
    }


def search_failure_patterns(query: str, limit: int = 20) -> dict[str, Any]:
    """Search the failure pattern database.
    
    Args:
        query: Search query
        limit: Maximum results
        
    Returns:
        Dict with matching patterns
    """
    db = get_pattern_db()
    patterns = db.search(query=query, limit=limit)
    
    return {
        "patterns": [p.to_dict() for p in patterns],
        "count": len(patterns),
    }


def suggest_known_fix(error_signature: str) -> dict[str, Any]:
    """Suggest a known fix for an error signature.
    
    Args:
        error_signature: Error signature to look up
        
    Returns:
        Dict with suggested fix or None
    """
    db = get_pattern_db()
    patterns = db.find_similar(error_signature)
    
    if patterns:
        # Return the most frequent matching pattern
        pattern = patterns[0]
        return {
            "found": True,
            "pattern": pattern.to_dict(),
            "confidence": min(1.0, pattern.frequency / 10.0),  # Higher frequency = higher confidence
            "suggestion": pattern.resolution if pattern.resolution else None,
        }
    
    return {
        "found": False,
        "pattern": None,
        "confidence": 0.0,
        "suggestion": None,
    }
