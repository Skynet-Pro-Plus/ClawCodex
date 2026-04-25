"""Worktree Management - Git worktree isolation for parallel agent work."""

from __future__ import annotations

import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class WorktreeInfo:
    """Information about a git worktree.
    
    Attributes:
        name: Worktree name
        path: Path to the worktree
        branch: Branch checked out in this worktree
        head: Current HEAD commit
        created_at: When the worktree was created
        agent_id: Agent using this worktree
        task_id: Task associated with this worktree
    """
    
    name: str
    path: str
    branch: str
    head: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    agent_id: str | None = None
    task_id: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "branch": self.branch,
            "head": self.head,
            "created_at": self.created_at.isoformat(),
            "agent_id": self.agent_id,
            "task_id": self.task_id,
        }


class WorktreeManager:
    """Manages git worktrees for parallel agent work.
    
    This class provides isolation between agents by creating
    separate git worktrees, preventing file conflicts.
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).absolute()
        self._worktrees: dict[str, WorktreeInfo] = {}
        self._lock = threading.RLock()
        self._base_worktree_path = self.repo_path.parent / f"{self.repo_path.name}-worktrees"
    
    def _run_git(self, args: list[str], cwd: str | Path | None = None) -> tuple[int, str, str]:
        """Run a git command.
        
        Args:
            args: Git command arguments
            cwd: Working directory
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)
    
    def create(
        self,
        name: str | None = None,
        branch: str | None = None,
        start_point: str = "HEAD",
        agent_id: str | None = None,
        task_id: str | None = None,
        create_branch: bool = True,
    ) -> WorktreeInfo | None:
        """Create a new worktree.
        
        Args:
            name: Optional name for the worktree
            branch: Branch name (creates new if create_branch=True)
            start_point: Starting point for new branch
            agent_id: Agent using this worktree
            task_id: Task using this worktree
            create_branch: Whether to create a new branch
            
        Returns:
            WorktreeInfo if successful, None otherwise
        """
        with self._lock:
            # Generate name if not provided
            if name is None:
                name = f"agent-{agent_id or 'work'}-{uuid.uuid4().hex[:8]}"
            
            # Generate branch name
            if branch is None:
                branch = f"worktree/{name}"
            
            # Ensure worktree directory exists
            self._base_worktree_path.mkdir(parents=True, exist_ok=True)
            
            worktree_path = self._base_worktree_path / name
            
            if worktree_path.exists():
                return None  # Already exists
            
            # Create the worktree
            if create_branch:
                args = ["worktree", "add", "-b", branch, str(worktree_path), start_point]
            else:
                args = ["worktree", "add", str(worktree_path), branch]
            
            code, stdout, stderr = self._run_git(args)
            
            if code != 0:
                return None
            
            # Get current HEAD
            code, head, _ = self._run_git(["rev-parse", "HEAD"], cwd=worktree_path)
            head = head.strip() if code == 0 else ""
            
            # Create worktree info
            info = WorktreeInfo(
                name=name,
                path=str(worktree_path),
                branch=branch,
                head=head,
                agent_id=agent_id,
                task_id=task_id,
            )
            
            self._worktrees[name] = info
            
            return info
    
    def list(self) -> list[WorktreeInfo]:
        """List all worktrees.
        
        Returns:
            List of WorktreeInfo objects
        """
        with self._lock:
            # Refresh from git
            self._refresh_from_git()
            return list(self._worktrees.values())
    
    def _refresh_from_git(self) -> None:
        """Refresh worktree list from git."""
        code, stdout, _ = self._run_git(["worktree", "list", "--porcelain"])
        
        if code != 0:
            return
        
        # Parse output
        current_name = None
        current_info: dict[str, Any] = {}
        
        for line in stdout.split('\n'):
            line = line.strip()
            
            if line.startswith('worktree '):
                if current_name and current_info:
                    self._worktrees[current_name] = WorktreeInfo(
                        name=current_name,
                        **current_info
                    )
                current_name = line[9:]
                current_info = {}
            
            elif line.startswith('branch '):
                current_info['branch'] = line[8:]
            
            elif line.startswith('HEAD '):
                current_info['head'] = line[5:]
            
            elif line.startswith('path '):
                current_info['path'] = line[5:]
        
        if current_name and current_info:
            self._worktrees[current_name] = WorktreeInfo(
                name=current_name,
                **current_info
            )
    
    def remove(self, name: str, force: bool = False) -> bool:
        """Remove a worktree.
        
        Args:
            name: Worktree name
            force: Force removal even with uncommitted changes
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if name not in self._worktrees:
                return False
            
            worktree = self._worktrees[name]
            
            # Remove via git
            if force:
                code, _, _ = self._run_git(["worktree", "remove", worktree.path, "--force"])
            else:
                code, _, _ = self._run_git(["worktree", "prune"])
                if code == 0:
                    # Try to remove if clean
                    code, _, _ = self._run_git(["worktree", "remove", worktree.path])
            
            if code == 0:
                del self._worktrees[name]
                return True
            
            return False
    
    def get(self, name: str) -> WorktreeInfo | None:
        """Get worktree information.
        
        Args:
            name: Worktree name
            
        Returns:
            WorktreeInfo if found, None otherwise
        """
        with self._lock:
            self._refresh_from_git()
            return self._worktrees.get(name)
    
    def prune(self) -> list[str]:
        """Prune stale worktree references.
        
        Returns:
            List of pruned worktree names
        """
        with self._lock:
            code, _, _ = self._run_git(["worktree", "prune"])
            
            if code == 0:
                # Clear and rebuild
                self._worktrees.clear()
                self._refresh_from_git()
            
            return []
    
    def cleanup_old_worktrees(self, max_age_hours: int = 24) -> list[str]:
        """Clean up worktrees older than specified age.
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            List of removed worktree names
        """
        with self._lock:
            self._refresh_from_git()
            
            removed = []
            cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
            
            for name, worktree in list(self._worktrees.items()):
                if worktree.created_at.timestamp() < cutoff:
                    if self.remove(name, force=True):
                        removed.append(name)
            
            return removed


# Global worktree managers by repo
_worktree_managers: dict[str, WorktreeManager] = {}
_manager_lock = threading.Lock()


def get_worktree_manager(repo_path: str | None = None) -> WorktreeManager:
    """Get or create a worktree manager for a repo.
    
    Args:
        repo_path: Path to the git repository
        
    Returns:
        WorktreeManager instance
    """
    if repo_path is None:
        repo_path = os.getcwd()
    
    repo_path = str(Path(repo_path).absolute())
    
    with _manager_lock:
        if repo_path not in _worktree_managers:
            _worktree_managers[repo_path] = WorktreeManager(repo_path)
        return _worktree_managers[repo_path]


def create_worktree(
    repo_path: str | None = None,
    name: str | None = None,
    branch: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create a new git worktree for parallel work.
    
    Args:
        repo_path: Path to the git repository
        name: Optional name for the worktree
        branch: Optional branch name
        agent_id: Agent using this worktree
        task_id: Task using this worktree
        
    Returns:
        Dict with worktree creation result
    """
    manager = get_worktree_manager(repo_path)
    worktree = manager.create(
        name=name,
        branch=branch,
        agent_id=agent_id,
        task_id=task_id,
    )
    
    if worktree:
        return {
            "success": True,
            "worktree": worktree.to_dict(),
            "message": f"Created worktree at {worktree.path}",
        }
    else:
        return {
            "success": False,
            "worktree": None,
            "message": "Failed to create worktree",
        }


def list_worktrees(repo_path: str | None = None) -> dict[str, Any]:
    """List all worktrees for a repository.
    
    Args:
        repo_path: Path to the git repository
        
    Returns:
        Dict with list of worktrees
    """
    manager = get_worktree_manager(repo_path)
    worktrees = manager.list()
    
    return {
        "worktrees": [w.to_dict() for w in worktrees],
        "count": len(worktrees),
    }


def cleanup_worktree(
    name: str,
    repo_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Remove a worktree.
    
    Args:
        name: Worktree name to remove
        repo_path: Path to the git repository
        force: Force removal even with uncommitted changes
        
    Returns:
        Dict with removal result
    """
    manager = get_worktree_manager(repo_path)
    success = manager.remove(name, force=force)
    
    return {
        "success": success,
        "name": name,
        "message": f"Removed worktree {name}" if success else f"Failed to remove {name}",
    }
