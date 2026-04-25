"""Cost Estimator - Track and estimate LLM token usage and costs."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class CostEstimate:
    """An estimated or actual cost for a task.
    
    Attributes:
        task_id: Task identifier
        model: Model used
        estimated_tokens: Estimated token count
        estimated_input_tokens: Estimated input tokens
        estimated_output_tokens: Estimated output tokens
        estimated_cost: Estimated cost in USD
        actual_tokens: Actual token count (if completed)
        actual_cost: Actual cost in USD
        created_at: When estimate was created
        completed_at: When task completed
    """
    
    task_id: str
    model: str
    estimated_tokens: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float = 0.0
    actual_tokens: int | None = None
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    actual_cost: float | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "model": self.model,
            "estimated_tokens": self.estimated_tokens,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_cost": self.estimated_cost,
            "actual_tokens": self.actual_tokens,
            "actual_input_tokens": self.actual_input_tokens,
            "actual_output_tokens": self.actual_output_tokens,
            "actual_cost": self.actual_cost,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class TokenUsage:
    """Recorded token usage for a run.
    
    Attributes:
        run_id: Unique run identifier
        task_id: Task this run belongs to
        agent_id: Agent that ran
        model: Model used
        input_tokens: Input tokens consumed
        output_tokens: Output tokens consumed
        total_tokens: Total tokens
        cost: Total cost in USD
        timestamp: When usage was recorded
        duration_ms: How long the run took
    """
    
    run_id: str
    task_id: str
    agent_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }


# Model pricing (per 1k tokens)
MODEL_PRICING = {
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "o1-preview": {"input": 0.015, "output": 0.06},
    "o1-mini": {"input": 0.003, "output": 0.012},
}


class CostEstimator:
    """Estimates and tracks LLM costs.
    
    This class provides token estimation before runs
    and cost tracking after completion.
    """
    
    def __init__(self):
        self._estimates: dict[str, CostEstimate] = {}
        self._usage: list[TokenUsage] = []
        self._lock = threading.Lock()
    
    def estimate(
        self,
        task_id: str,
        model: str,
        input_text: str,
        expected_output_tokens: int | None = None,
    ) -> CostEstimate:
        """Estimate cost for a task.
        
        Args:
            task_id: Task identifier
            model: Model to use
            input_text: Input text to estimate tokens for
            expected_output_tokens: Expected output token count
            
        Returns:
            CostEstimate
        """
        # Rough token estimation (1 token ≈ 4 chars for English)
        input_tokens = len(input_text) // 4
        output_tokens = expected_output_tokens or (input_tokens // 2)
        
        # Get pricing
        pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
        
        # Calculate cost
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        estimate = CostEstimate(
            task_id=task_id,
            model=model,
            estimated_tokens=input_tokens + output_tokens,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_cost=total_cost,
        )
        
        with self._lock:
            self._estimates[task_id] = estimate
        
        return estimate
    
    def record_usage(
        self,
        run_id: str,
        task_id: str,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int = 0,
    ) -> TokenUsage:
        """Record actual token usage.
        
        Args:
            run_id: Unique run identifier
            task_id: Task this run belongs to
            agent_id: Agent that ran
            model: Model used
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
            duration_ms: How long the run took
            
        Returns:
            TokenUsage record
        """
        pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
        total_tokens = input_tokens + output_tokens
        cost = (
            (input_tokens / 1000) * pricing["input"] +
            (output_tokens / 1000) * pricing["output"]
        )
        
        usage = TokenUsage(
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            duration_ms=duration_ms,
        )
        
        with self._lock:
            self._usage.append(usage)
            
            # Update estimate if exists
            if task_id in self._estimates:
                estimate = self._estimates[task_id]
                estimate.actual_tokens = total_tokens
                estimate.actual_input_tokens = input_tokens
                estimate.actual_output_tokens = output_tokens
                estimate.actual_cost = cost
                estimate.completed_at = datetime.now()
        
        return usage
    
    def get_usage_for_task(self, task_id: str) -> list[TokenUsage]:
        """Get all usage records for a task.
        
        Args:
            task_id: Task to query
            
        Returns:
            List of TokenUsage records
        """
        with self._lock:
            return [u for u in self._usage if u.task_id == task_id]
    
    def get_usage_for_agent(self, agent_id: str) -> list[TokenUsage]:
        """Get all usage records for an agent.
        
        Args:
            agent_id: Agent to query
            
        Returns:
            List of TokenUsage records
        """
        with self._lock:
            return [u for u in self._usage if u.agent_id == agent_id]
    
    def get_total_cost(
        self,
        since: datetime | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Get total cost statistics.
        
        Args:
            since: Only count usage since this time
            agent_id: Filter by agent
            
        Returns:
            Dict with cost statistics
        """
        with self._lock:
            usage = self._usage.copy()
        
        if since:
            usage = [u for u in usage if u.timestamp >= since]
        
        if agent_id:
            usage = [u for u in usage if u.agent_id == agent_id]
        
        if not usage:
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "run_count": 0,
            }
        
        return {
            "total_cost": sum(u.cost for u in usage),
            "total_tokens": sum(u.total_tokens for u in usage),
            "total_input_tokens": sum(u.input_tokens for u in usage),
            "total_output_tokens": sum(u.output_tokens for u in usage),
            "run_count": len(usage),
            "avg_cost_per_run": sum(u.cost for u in usage) / len(usage),
            "avg_tokens_per_run": sum(u.total_tokens for u in usage) / len(usage),
        }
    
    def get_efficiency_summary(self, window_days: int = 7) -> dict[str, Any]:
        """Get efficiency summary for a time window.
        
        Args:
            window_days: Number of days to look back
            
        Returns:
            Dict with efficiency metrics
        """
        since = datetime.now() - timedelta(days=window_days)
        
        with self._lock:
            usage = [u for u in self._usage if u.timestamp >= since]
        
        if not usage:
            return {
                "window_days": window_days,
                "total_runs": 0,
                "total_cost": 0.0,
                "cost_per_day": 0.0,
            }
        
        # Group by model
        by_model: dict[str, dict] = {}
        for u in usage:
            if u.model not in by_model:
                by_model[u.model] = {"runs": 0, "cost": 0.0, "tokens": 0}
            by_model[u.model]["runs"] += 1
            by_model[u.model]["cost"] += u.cost
            by_model[u.model]["tokens"] += u.total_tokens
        
        # Calculate days in window
        days = max(1, (datetime.now() - usage[-1].timestamp).days + 1)
        
        return {
            "window_days": window,
            "total_runs": len(usage),
            "total_cost": sum(u.cost for u in usage),
            "cost_per_day": sum(u.cost for u in usage) / days,
            "total_tokens": sum(u.total_tokens for u in usage),
            "by_model": by_model,
        }


# Global cost estimator
_cost_estimator: CostEstimator | None = None
_estimator_lock = threading.Lock()


def get_cost_estimator() -> CostEstimator:
    """Get or create the global cost estimator."""
    global _cost_estimator
    with _estimator_lock:
        if _cost_estimator is None:
            _cost_estimator = CostEstimator()
        return _cost_estimator


def estimate_llm_cost(
    task_description: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Estimate LLM cost for a task.
    
    Args:
        task_description: Description of the task
        model: Optional model name
        
    Returns:
        Dict with cost estimate
    """
    import uuid
    
    task_id = uuid.uuid4().hex
    
    estimator = get_cost_estimator()
    estimate = estimator.estimate(
        task_id=task_id,
        model=model or "gpt-4o",
        input_text=task_description,
    )
    
    return {
        "task_id": task_id,
        "model": estimate.model,
        "estimated_tokens": estimate.estimated_tokens,
        "estimated_cost": estimate.estimated_cost,
        "breakdown": {
            "input_tokens": estimate.estimated_input_tokens,
            "output_tokens": estimate.estimated_output_tokens,
            "input_cost": (estimate.estimated_input_tokens / 1000) * MODEL_PRICING.get(estimate.model, {}).get("input", 0.001),
            "output_cost": (estimate.estimated_output_tokens / 1000) * MODEL_PRICING.get(estimate.model, {}).get("output", 0.002),
        },
    }


def track_token_usage(
    task_id: str,
    agent_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Track actual token usage for a run.
    
    Args:
        task_id: Task identifier
        agent_id: Agent identifier
        model: Model used
        input_tokens: Input tokens consumed
        output_tokens: Output tokens consumed
        duration_ms: Run duration in milliseconds
        
    Returns:
        Dict with usage record
    """
    import uuid
    
    run_id = uuid.uuid4().hex
    
    estimator = get_cost_estimator()
    usage = estimator.record_usage(
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )
    
    return usage.to_dict()
