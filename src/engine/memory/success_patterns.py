"""Success Registry - Track successful repairs and solutions."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SuccessfulRepair:
    """A successful repair or solution.
    
    Attributes:
        id: Unique repair identifier
        change_summary: Summary of the change made
        files_changed: Files that were modified
        evidence: Evidence of success (test results, output)
        problem_signature: What problem this solved
        related_failures: Related failure pattern IDs
        created_at: When this was recorded
        verified: Whether verified with tests
    """
    
    id: str
    change_summary: str
    files_changed: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    problem_signature: str = ""
    related_failures: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    verified: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "change_summary": self.change_summary,
            "files_changed": self.files_changed,
            "evidence": self.evidence,
            "problem_signature": self.problem_signature,
            "related_failures": self.related_failures,
            "created_at": self.created_at.isoformat(),
            "verified": self.verified,
        }


class SuccessRegistry:
    """Registry of successful repairs and solutions.
    
    This class provides persistent storage for successful repairs,
    enabling reuse of proven solutions.
    """
    
    _create_table_sql = """
        CREATE TABLE IF NOT EXISTS successful_repairs (
            id TEXT PRIMARY KEY,
            change_summary TEXT NOT NULL,
            files_changed TEXT,
            evidence TEXT,
            problem_signature TEXT,
            related_failures TEXT,
            created_at TEXT,
            verified INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_problem_signature ON successful_repairs(problem_signature);
    """
    
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "memdir" / "success_registry.db"
        
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
    
    def insert(self, repair: SuccessfulRepair) -> str:
        """Insert a new successful repair.
        
        Args:
            repair: SuccessfulRepair to insert
            
        Returns:
            Repair ID
        """
        import json
        
        with self._lock:
            self._ensure_connection()
            
            self._conn.execute(
                """
                INSERT INTO successful_repairs
                (id, change_summary, files_changed, evidence, problem_signature,
                 related_failures, created_at, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repair.id,
                    repair.change_summary,
                    json.dumps(repair.files_changed),
                    json.dumps(repair.evidence),
                    repair.problem_signature,
                    json.dumps(repair.related_failures),
                    repair.created_at.isoformat(),
                    1 if repair.verified else 0,
                ),
            )
            self._conn.commit()
            
            return repair.id
    
    def search(
        self,
        query: str | None = None,
        problem_signature: str | None = None,
        limit: int = 50,
    ) -> list[SuccessfulRepair]:
        """Search for successful repairs.
        
        Args:
            query: Text search query
            problem_signature: Filter by problem signature
            limit: Maximum results
            
        Returns:
            List of matching SuccessfulRepair objects
        """
        import json
        
        with self._lock:
            self._ensure_connection()
            
            conditions = []
            params = []
            
            if query:
                conditions.append("(change_summary LIKE ? OR problem_signature LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            
            if problem_signature:
                conditions.append("problem_signature = ?")
                params.append(problem_signature)
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            cursor = self._conn.execute(
                f"""
                SELECT id, change_summary, files_changed, evidence, problem_signature,
                       related_failures, created_at, verified
                FROM successful_repairs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit],
            )
            
            repairs = []
            for row in cursor.fetchall():
                repairs.append(SuccessfulRepair(
                    id=row[0],
                    change_summary=row[1],
                    files_changed=json.loads(row[2]) if row[2] else [],
                    evidence=json.loads(row[3]) if row[3] else [],
                    problem_signature=row[4] or "",
                    related_failures=json.loads(row[5]) if row[5] else [],
                    created_at=datetime.fromisoformat(row[6]),
                    verified=bool(row[7]),
                ))
            
            return repairs
    
    def find_similar(
        self,
        problem_signature: str,
        files_changed: list[str] | None = None,
    ) -> list[SuccessfulRepair]:
        """Find repairs that solved similar problems.
        
        Args:
            problem_signature: Problem signature to match
            files_changed: Optional file list to match
            
        Returns:
            List of similar SuccessfulRepair objects
        """
        import json
        
        with self._lock:
            self._ensure_connection()
            
            cursor = self._conn.execute(
                """
                SELECT id, change_summary, files_changed, evidence, problem_signature,
                       related_failures, created_at, verified
                FROM successful_repairs
                WHERE problem_signature = ?
                ORDER BY verified DESC, created_at DESC
                LIMIT 10
                """,
                (problem_signature,),
            )
            
            repairs = []
            for row in cursor.fetchall():
                repair = SuccessfulRepair(
                    id=row[0],
                    change_summary=row[1],
                    files_changed=json.loads(row[2]) if row[2] else [],
                    evidence=json.loads(row[3]) if row[3] else [],
                    problem_signature=row[4] or "",
                    related_failures=json.loads(row[5]) if row[5] else [],
                    created_at=datetime.fromisoformat(row[6]),
                    verified=bool(row[7]),
                )
                
                # If files_changed provided, score by overlap
                if files_changed:
                    overlap = set(repair.files_changed) & set(files_changed)
                    if overlap:
                        repairs.append(repair)
                else:
                    repairs.append(repair)
            
            return repairs
    
    def mark_verified(self, repair_id: str) -> None:
        """Mark a repair as verified.
        
        Args:
            repair_id: Repair to mark as verified
        """
        with self._lock:
            self._ensure_connection()
            
            self._conn.execute(
                "UPDATE successful_repairs SET verified = 1 WHERE id = ?",
                (repair_id,),
            )
            self._conn.commit()
    
    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


# Global success registry
_success_registry: SuccessRegistry | None = None
_registry_lock = threading.Lock()


def get_success_registry() -> SuccessRegistry:
    """Get or create the global success registry."""
    global _success_registry
    with _registry_lock:
        if _success_registry is None:
            _success_registry = SuccessRegistry()
        return _success_registry


def record_successful_repair(
    change_summary: str,
    files_changed: list[str] | None = None,
    evidence: list[str] | None = None,
    problem_signature: str = "",
    related_failures: list[str] | None = None,
) -> dict[str, Any]:
    """Record a successful repair.
    
    Args:
        change_summary: Summary of the change made
        files_changed: Files that were modified
        evidence: Evidence of success
        problem_signature: What problem this solved
        related_failures: Related failure pattern IDs
        
    Returns:
        Dict with repair info
    """
    registry = get_success_registry()
    
    repair = SuccessfulRepair(
        id=uuid.uuid4().hex,
        change_summary=change_summary,
        files_changed=files_changed or [],
        evidence=evidence or [],
        problem_signature=problem_signature,
        related_failures=related_failures or [],
    )
    
    registry.insert(repair)
    
    return {
        "repair_id": repair.id,
        "change_summary": repair.change_summary,
        "message": "Successful repair recorded",
    }


def get_successful_patterns(
    query: str | None = None,
    problem_signature: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search for successful repair patterns.
    
    Args:
        query: Search query
        problem_signature: Filter by problem signature
        limit: Maximum results
        
    Returns:
        Dict with matching repairs
    """
    registry = get_success_registry()
    repairs = registry.search(
        query=query,
        problem_signature=problem_signature,
        limit=limit,
    )
    
    return {
        "repairs": [r.to_dict() for r in repairs],
        "count": len(repairs),
    }
