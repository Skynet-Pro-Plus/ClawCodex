"""Multi-Agent Coordination Module - File locking, task ownership, and worktree management."""

from .locks import (
    FileLock,
    FileLockManager,
    lock_file,
    release_file,
    get_file_lock,
)
from .ownership import (
    TaskOwnership,
    AgentOwnership,
    reserve_change_set,
    get_task_owner,
    handoff_task,
)
from .worktrees import (
    WorktreeManager,
    create_worktree,
    list_worktrees,
    cleanup_worktree,
)
from .handoff import (
    HandoffContext,
    create_handoff,
    receive_handoff,
)

__all__ = [
    # Locks
    "FileLock",
    "FileLockManager",
    "lock_file",
    "release_file",
    "get_file_lock",
    # Ownership
    "TaskOwnership",
    "AgentOwnership",
    "reserve_change_set",
    "get_task_owner",
    "handoff_task",
    # Worktrees
    "WorktreeManager",
    "create_worktree",
    "list_worktrees",
    "cleanup_worktree",
    # Handoff
    "HandoffContext",
    "create_handoff",
    "receive_handoff",
]
