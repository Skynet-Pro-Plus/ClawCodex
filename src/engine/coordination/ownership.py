"""Task Ownership - Track task and agent ownership for multi-agent workflows."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskOwnership:
    """Ownership information for a task.
    
    Attributes:
        task_id: Unique task identifier
        assigned_agent: ID of the agent assigned to this task
        status: Current task status
        priority: Task priority (1-5, higher is more important)
        created_at: When the task was created
        updated_at: When the task was last updated
        deadline: Optional deadline for the task
        blocked_by: List of task IDs this task is blocked by
        blocks: List of task IDs this task blocks
    """
    
    task_id: str
    assigned_agent: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    deadline: datetime | None = None
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    description: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "assigned_agent": self.assigned_agent,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "description": self.description,
        }


@dataclass
class AgentOwnership:
    """Ownership information for an agent's current activities.
    
    Attributes:
        agent_id: Unique agent identifier
        current_task_id: Task the agent is currently working on
        locked_files: List of files the agent has locked
        workspace: Agent's workspace path
        started_at: When the agent started this task
        check_in: Last time the agent checked in
    """
    
    agent_id: str
    current_task_id: str | None = None
    locked_files: list[str] = field(default_factory=list)
    workspace: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    check_in: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_task_id": self.current_task_id,
            "locked_files": self.locked_files,
            "workspace": self.workspace,
            "started_at": self.started_at.isoformat(),
            "check_in": self.check_in.isoformat(),
        }


class OwnershipManager:
    """Manages task and agent ownership.
    
    This class provides thread-safe tracking of who owns which
    tasks and files in a multi-agent system.
    """
    
    def __init__(self):
        self._tasks: dict[str, TaskOwnership] = {}
        self._agents: dict[str, AgentOwnership] = {}
        self._lock = threading.RLock()
    
    # Task management
    def create_task(
        self,
        task_id: str,
        description: str = "",
        priority: int = 3,
        deadline: datetime | None = None,
    ) -> TaskOwnership:
        """Create a new task.
        
        Args:
            task_id: Unique task identifier
            description: Task description
            priority: Task priority (1-5)
            deadline: Optional deadline
            
        Returns:
            The created TaskOwnership
        """
        with self._lock:
            task = TaskOwnership(
                task_id=task_id,
                description=description,
                priority=priority,
                deadline=deadline,
            )
            self._tasks[task_id] = task
            return task
    
    def assign_task(
        self,
        task_id: str,
        agent_id: str,
    ) -> bool:
        """Assign a task to an agent.
        
        Args:
            task_id: Task to assign
            agent_id: Agent to assign to
            
        Returns:
            True if successful, False if task doesn't exist
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            task.assigned_agent = agent_id
            task.status = TaskStatus.IN_PROGRESS
            task.updated_at = datetime.now()
            
            # Update agent's current task
            if agent_id in self._agents:
                self._agents[agent_id].current_task_id = task_id
            
            return True
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> bool:
        """Update a task's status.
        
        Args:
            task_id: Task to update
            status: New status
            
        Returns:
            True if successful, False if task doesn't exist
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            task.status = status
            task.updated_at = datetime.now()
            
            # If completed, clear agent's current task
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.assigned_agent and task.assigned_agent in self._agents:
                    self._agents[task.assigned_agent].current_task_id = None
            
            return True
    
    def get_task(self, task_id: str) -> TaskOwnership | None:
        """Get task ownership information.
        
        Args:
            task_id: Task to retrieve
            
        Returns:
            TaskOwnership if found, None otherwise
        """
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_tasks_for_agent(self, agent_id: str) -> list[TaskOwnership]:
        """Get all tasks assigned to an agent.
        
        Args:
            agent_id: Agent to query
            
        Returns:
            List of TaskOwnership objects
        """
        with self._lock:
            return [
                task for task in self._tasks.values()
                if task.assigned_agent == agent_id
            ]
    
    def get_blocked_tasks(self, agent_id: str) -> list[TaskOwnership]:
        """Get tasks blocked by other tasks.
        
        Args:
            agent_id: Agent to check for
            
        Returns:
            List of blocked TaskOwnership objects
        """
        with self._lock:
            agent_tasks = self.get_tasks_for_agent(agent_id)
            return [
                task for task in agent_tasks
                if task.status == TaskStatus.BLOCKED or task.blocked_by
            ]
    
    def add_blocker(
        self,
        task_id: str,
        blocked_by: str,
    ) -> bool:
        """Add a blocking dependency.
        
        Args:
            task_id: Task that will be blocked
            blocked_by: Task ID that blocks this task
            
        Returns:
            True if successful
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if blocked_by not in task.blocked_by:
                task.blocked_by.append(blocked_by)
            
            # Update blocked task's status
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.BLOCKED
            
            return True
    
    # Agent management
    def register_agent(
        self,
        agent_id: str,
        workspace: str | None = None,
    ) -> AgentOwnership:
        """Register an agent with the system.
        
        Args:
            agent_id: Unique agent identifier
            workspace: Agent's workspace path
            
        Returns:
            The created AgentOwnership
        """
        with self._lock:
            agent = AgentOwnership(
                agent_id=agent_id,
                workspace=workspace,
            )
            self._agents[agent_id] = agent
            return agent
    
    def get_agent(self, agent_id: str) -> AgentOwnership | None:
        """Get agent ownership information.
        
        Args:
            agent_id: Agent to retrieve
            
        Returns:
            AgentOwnership if found, None otherwise
        """
        with self._lock:
            return self._agents.get(agent_id)
    
    def check_in_agent(self, agent_id: str) -> bool:
        """Update agent's check-in time.
        
        Args:
            agent_id: Agent checking in
            
        Returns:
            True if successful, False if agent not registered
        """
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            
            agent.check_in = datetime.now()
            return True
    
    def get_all_agents(self) -> list[AgentOwnership]:
        """Get all registered agents.
        
        Returns:
            List of all AgentOwnership objects
        """
        with self._lock:
            return list(self._agents.values())


# Global ownership manager
_ownership_manager: OwnershipManager | None = None
_ownership_lock = threading.Lock()


def get_ownership_manager() -> OwnershipManager:
    """Get or create the global ownership manager."""
    global _ownership_manager
    with _ownership_lock:
        if _ownership_manager is None:
            _ownership_manager = OwnershipManager()
        return _ownership_manager


def get_task_owner(task_id: str) -> dict[str, Any]:
    """Get the owner of a task.
    
    Args:
        task_id: Task to query
        
    Returns:
        Dict with task ownership info
    """
    manager = get_ownership_manager()
    task = manager.get_task(task_id)
    
    if task:
        return task.to_dict()
    else:
        return {
            "task_id": task_id,
            "assigned_agent": None,
            "status": None,
            "message": "Task not found",
        }


def reserve_change_set(
    paths: list[str],
    agent_id: str,
) -> dict[str, Any]:
    """Reserve a set of files for an agent.
    
    Args:
        paths: List of file paths to reserve
        agent_id: Agent reserving the files
        
    Returns:
        Dict with reservation result
    """
    from .locks import lock_file
    
    results = []
    reserved = []
    failed = []
    
    for path in paths:
        result = lock_file(path, agent_id)
        if result.get("locked"):
            reserved.append(path)
        else:
            failed.append({"path": path, "reason": result.get("message")})
    
    return {
        "agent_id": agent_id,
        "reserved": reserved,
        "failed": failed,
        "success": len(failed) == 0,
        "message": f"Reserved {len(reserved)} of {len(paths)} files",
    }


def handoff_task(
    task_id: str,
    from_agent: str,
    to_agent: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hand off a task from one agent to another.
    
    Args:
        task_id: Task to hand off
        from_agent: Current agent
        to_agent: Target agent
        context: Optional context to pass
        
    Returns:
        Dict with handoff result
    """
    manager = get_ownership_manager()
    
    task = manager.get_task(task_id)
    if not task:
        return {
            "success": False,
            "message": f"Task {task_id} not found",
        }
    
    if task.assigned_agent != from_agent:
        return {
            "success": False,
            "message": f"Task {task_id} is not assigned to {from_agent}",
        }
    
    # Update task assignment
    manager.assign_task(task_id, to_agent)
    
    # Create handoff record
    handoff_record = {
        "task_id": task_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "timestamp": datetime.now().isoformat(),
        "context": context or {},
    }
    
    return {
        "success": True,
        "handoff": handoff_record,
        "message": f"Task {task_id} handed off from {from_agent} to {to_agent}",
    }
