"""File Locking - Distributed file locking for multi-agent coordination."""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class FileLock:
    """A lock on a file.
    
    Attributes:
        path: The locked file path
        lock_id: Unique identifier for this lock
        agent_id: ID of the agent holding the lock
        acquired_at: When the lock was acquired
        expires_at: When the lock expires
        ttl_sec: Time-to-live in seconds
    """
    
    path: str
    lock_id: str
    agent_id: str
    acquired_at: datetime
    expires_at: datetime
    ttl_sec: int = 900  # 15 minutes default
    
    def is_expired(self) -> bool:
        """Check if the lock has expired."""
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "lock_id": self.lock_id,
            "agent_id": self.agent_id,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "ttl_sec": self.ttl_sec,
            "is_expired": self.is_expired(),
        }


class FileLockManager:
    """Manages file locks for multi-agent coordination.
    
    This class provides a thread-safe, in-memory lock manager.
    For distributed systems, this should be backed by a distributed
    store like Redis or etcd.
    """
    
    def __init__(self):
        self._locks: dict[str, FileLock] = {}
        self._lock = threading.RLock()
        self._callbacks: list[callable] = []
    
    def acquire(
        self,
        path: str,
        agent_id: str,
        ttl_sec: int = 900,
    ) -> FileLock | None:
        """Acquire a lock on a file.
        
        Args:
            path: Path to the file to lock
            agent_id: ID of the agent requesting the lock
            ttl_sec: Lock time-to-live in seconds
            
        Returns:
            FileLock if successful, None if already locked
        """
        # Normalize path
        path = os.path.abspath(path)
        
        with self._lock:
            # Check for existing lock
            existing = self._locks.get(path)
            
            if existing:
                # Check if expired
                if existing.is_expired():
                    del self._locks[path]
                elif existing.agent_id != agent_id:
                    # Someone else holds the lock
                    return None
                else:
                    # Same agent, extend the lock
                    existing.expires_at = datetime.now() + timedelta(seconds=ttl_sec)
                    return existing
            
            # Create new lock
            now = datetime.now()
            file_lock = FileLock(
                path=path,
                lock_id=uuid.uuid4().hex,
                agent_id=agent_id,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl_sec),
                ttl_sec=ttl_sec,
            )
            
            self._locks[path] = file_lock
            
            # Notify callbacks
            self._on_lock_acquired(file_lock)
            
            return file_lock
    
    def release(
        self,
        path: str,
        agent_id: str,
    ) -> bool:
        """Release a lock on a file.
        
        Args:
            path: Path to the file to unlock
            agent_id: ID of the agent releasing the lock
            
        Returns:
            True if released, False if not held by this agent
        """
        path = os.path.abspath(path)
        
        with self._lock:
            existing = self._locks.get(path)
            
            if not existing:
                return True  # Already released
            
            if existing.agent_id != agent_id:
                return False  # Can't release someone else's lock
            
            del self._locks[path]
            
            # Notify callbacks
            self._on_lock_released(existing)
            
            return True
    
    def get_lock(self, path: str) -> FileLock | None:
        """Get information about a lock.
        
        Args:
            path: Path to check
            
        Returns:
            FileLock if locked and not expired, None otherwise
        """
        path = os.path.abspath(path)
        
        with self._lock:
            existing = self._locks.get(path)
            
            if existing and existing.is_expired():
                del self._locks[path]
                return None
            
            return existing
    
    def get_locks_for_agent(self, agent_id: str) -> list[FileLock]:
        """Get all locks held by an agent.
        
        Args:
            agent_id: Agent ID to query
            
        Returns:
            List of FileLock objects
        """
        with self._lock:
            return [
                lock for lock in self._locks.values()
                if lock.agent_id == agent_id and not lock.is_expired()
            ]
    
    def release_expired(self) -> list[str]:
        """Release all expired locks.
        
        Returns:
            List of released file paths
        """
        with self._lock:
            expired_paths = [
                path for path, lock in self._locks.items()
                if lock.is_expired()
            ]
            
            for path in expired_paths:
                del self._locks[path]
            
            return expired_paths
    
    def get_all_locks(self) -> list[FileLock]:
        """Get all active locks.
        
        Returns:
            List of all non-expired FileLock objects
        """
        with self._lock:
            # Clean up expired first
            self.release_expired()
            
            return list(self._locks.values())
    
    def add_callback(self, callback: callable) -> None:
        """Add a callback for lock events.
        
        Args:
            callback: Function to call with (event, lock) args
        """
        self._callbacks.append(callback)
    
    def _on_lock_acquired(self, file_lock: FileLock) -> None:
        """Notify callbacks of lock acquisition."""
        for callback in self._callbacks:
            try:
                callback("acquired", file_lock)
            except Exception:
                pass
    
    def _on_lock_released(self, file_lock: FileLock) -> None:
        """Notify callbacks of lock release."""
        for callback in self._callbacks:
            try:
                callback("released", file_lock)
            except Exception:
                pass


# Global lock manager
_lock_manager: FileLockManager | None = None
_manager_lock = threading.Lock()


def get_lock_manager() -> FileLockManager:
    """Get or create the global lock manager."""
    global _lock_manager
    with _manager_lock:
        if _lock_manager is None:
            _lock_manager = FileLockManager()
        return _lock_manager


def lock_file(
    path: str,
    agent_id: str,
    ttl_sec: int = 900,
) -> dict[str, Any]:
    """Acquire exclusive write lock on a file.
    
    Args:
        path: Path to the file to lock
        agent_id: ID of the agent requesting the lock
        ttl_sec: Lock time-to-live in seconds
        
    Returns:
        Dict with lock result
    """
    manager = get_lock_manager()
    file_lock = manager.acquire(path, agent_id, ttl_sec)
    
    if file_lock:
        return {
            "locked": True,
            "lock_id": file_lock.lock_id,
            "path": file_lock.path,
            "expires_at": file_lock.expires_at.isoformat(),
            "message": f"Lock acquired on {path}",
        }
    else:
        existing = manager.get_lock(path)
        return {
            "locked": False,
            "lock_id": None,
            "path": path,
            "locked_by": existing.agent_id if existing else None,
            "expires_at": existing.expires_at.isoformat() if existing else None,
            "message": f"File {path} is locked by another agent",
        }


def release_file(
    path: str,
    agent_id: str,
) -> dict[str, Any]:
    """Release a write lock on a file.
    
    Args:
        path: Path to the file to unlock
        agent_id: ID of the agent releasing the lock
        
    Returns:
        Dict with release result
    """
    manager = get_lock_manager()
    released = manager.release(path, agent_id)
    
    if released:
        return {
            "released": True,
            "path": path,
            "message": f"Lock released on {path}",
        }
    else:
        return {
            "released": False,
            "path": path,
            "message": f"Cannot release lock on {path} - not held by this agent",
        }


def get_file_lock(path: str) -> dict[str, Any]:
    """Get information about a file lock.
    
    Args:
        path: Path to check
        
    Returns:
        Dict with lock information
    """
    manager = get_lock_manager()
    file_lock = manager.get_lock(path)
    
    if file_lock:
        return {
            "locked": True,
            "lock": file_lock.to_dict(),
        }
    else:
        return {
            "locked": False,
            "lock": None,
        }
