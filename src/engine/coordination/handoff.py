"""Agent Handoff - Context transfer between agents."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HandoffContext:
    """Context passed during agent handoff.
    
    Attributes:
        handoff_id: Unique handoff identifier
        task_id: Task being handed off
        from_agent: Agent handing off
        to_agent: Agent receiving
        timestamp: When handoff occurred
        state: State to transfer
        notes: Additional notes
        completed: Whether handoff was completed
    """
    
    handoff_id: str
    task_id: str
    from_agent: str
    to_agent: str
    timestamp: datetime = field(default_factory=datetime.now)
    state: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    completed: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "notes": self.notes,
            "completed": self.completed,
        }


class HandoffManager:
    """Manages agent handoffs with context transfer.
    
    This class tracks handoffs between agents, ensuring smooth
    transition of work with full context preservation.
    """
    
    def __init__(self):
        self._handoffs: dict[str, HandoffContext] = {}
        self._pending: dict[str, list[HandoffContext]] = {}  # agent_id -> pending handoffs
        self._lock = threading.RLock()
    
    def create(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        state: dict[str, Any] | None = None,
        notes: str = "",
    ) -> HandoffContext:
        """Create a new handoff.
        
        Args:
            task_id: Task being handed off
            from_agent: Agent handing off
            to_agent: Agent receiving
            state: State to transfer
            notes: Additional notes
            
        Returns:
            The created HandoffContext
        """
        with self._lock:
            handoff = HandoffContext(
                handoff_id=uuid.uuid4().hex,
                task_id=task_id,
                from_agent=from_agent,
                to_agent=to_agent,
                state=state or {},
                notes=notes,
            )
            
            self._handoffs[handoff.handoff_id] = handoff
            
            # Add to pending for receiving agent
            if to_agent not in self._pending:
                self._pending[to_agent] = []
            self._pending[to_agent].append(handoff)
            
            return handoff
    
    def receive(self, agent_id: str) -> list[HandoffContext]:
        """Get pending handoffs for an agent.
        
        Args:
            agent_id: Agent to get handoffs for
            
        Returns:
            List of pending HandoffContext objects
        """
        with self._lock:
            handoffs = self._pending.get(agent_id, []).copy()
            return handoffs
    
    def accept(
        self,
        handoff_id: str,
        agent_id: str,
    ) -> bool:
        """Accept a handoff.
        
        Args:
            handoff_id: Handoff to accept
            agent_id: Agent accepting
            
        Returns:
            True if accepted, False if not found or wrong agent
        """
        with self._lock:
            handoff = self._handoffs.get(handoff_id)
            
            if not handoff:
                return False
            
            if handoff.to_agent != agent_id:
                return False
            
            # Mark as completed
            handoff.completed = True
            
            # Remove from pending
            if agent_id in self._pending:
                self._pending[agent_id] = [
                    h for h in self._pending[agent_id]
                    if h.handoff_id != handoff_id
                ]
            
            return True
    
    def reject(
        self,
        handoff_id: str,
        agent_id: str,
        reason: str = "",
    ) -> bool:
        """Reject a handoff.
        
        Args:
            handoff_id: Handoff to reject
            agent_id: Agent rejecting
            reason: Rejection reason
            
        Returns:
            True if rejected, False otherwise
        """
        with self._lock:
            handoff = self._handoffs.get(handoff_id)
            
            if not handoff:
                return False
            
            if handoff.to_agent != agent_id:
                return False
            
            # Remove from pending
            if agent_id in self._pending:
                self._pending[agent_id] = [
                    h for h in self._pending[agent_id]
                    if h.handoff_id != handoff_id
                ]
            
            return True
    
    def get(self, handoff_id: str) -> HandoffContext | None:
        """Get handoff by ID.
        
        Args:
            handoff_id: Handoff to retrieve
            
        Returns:
            HandoffContext if found, None otherwise
        """
        with self._lock:
            return self._handoffs.get(handoff_id)
    
    def get_history(
        self,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[HandoffContext]:
        """Get handoff history.
        
        Args:
            agent_id: Optional agent to filter by
            limit: Maximum number to return
            
        Returns:
            List of HandoffContext objects
        """
        with self._lock:
            handoffs = list(self._handoffs.values())
            
            # Filter by agent if specified
            if agent_id:
                handoffs = [
                    h for h in handoffs
                    if h.from_agent == agent_id or h.to_agent == agent_id
                ]
            
            # Sort by timestamp (most recent first)
            handoffs.sort(key=lambda h: h.timestamp, reverse=True)
            
            return handoffs[:limit]


# Global handoff manager
_handoff_manager: HandoffManager | None = None
_handoff_lock = threading.Lock()


def get_handoff_manager() -> HandoffManager:
    """Get or create the global handoff manager."""
    global _handoff_manager
    with _handoff_lock:
        if _handoff_manager is None:
            _handoff_manager = HandoffManager()
        return _handoff_manager


def create_handoff(
    task_id: str,
    from_agent: str,
    to_agent: str,
    state: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Create a handoff between agents.
    
    Args:
        task_id: Task being handed off
        from_agent: Agent handing off
        to_agent: Agent receiving
        state: State to transfer
        notes: Additional notes
        
    Returns:
        Dict with handoff result
    """
    manager = get_handoff_manager()
    handoff = manager.create(
        task_id=task_id,
        from_agent=from_agent,
        to_agent=to_agent,
        state=state,
        notes=notes,
    )
    
    return {
        "success": True,
        "handoff": handoff.to_dict(),
        "message": f"Handoff created for task {task_id}",
    }


def receive_handoff(agent_id: str) -> dict[str, Any]:
    """Get pending handoffs for an agent.
    
    Args:
        agent_id: Agent to get handoffs for
        
    Returns:
        Dict with pending handoffs
    """
    manager = get_handoff_manager()
    handoffs = manager.receive(agent_id)
    
    return {
        "handoffs": [h.to_dict() for h in handoffs],
        "count": len(handoffs),
    }


def accept_handoff(
    handoff_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Accept a handoff.
    
    Args:
        handoff_id: Handoff to accept
        agent_id: Agent accepting
        
    Returns:
        Dict with acceptance result
    """
    manager = get_handoff_manager()
    success = manager.accept(handoff_id, agent_id)
    
    if success:
        handoff = manager.get(handoff_id)
        return {
            "success": True,
            "handoff": handoff.to_dict() if handoff else None,
            "message": f"Handoff {handoff_id} accepted",
        }
    else:
        return {
            "success": False,
            "message": f"Cannot accept handoff {handoff_id}",
        }


def reject_handoff(
    handoff_id: str,
    agent_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Reject a handoff.
    
    Args:
        handoff_id: Handoff to reject
        agent_id: Agent rejecting
        reason: Rejection reason
        
    Returns:
        Dict with rejection result
    """
    manager = get_handoff_manager()
    success = manager.reject(handoff_id, agent_id, reason)
    
    if success:
        return {
            "success": True,
            "message": f"Handoff {handoff_id} rejected: {reason}",
        }
    else:
        return {
            "success": False,
            "message": f"Cannot reject handoff {handoff_id}",
        }
