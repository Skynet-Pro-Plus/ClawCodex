"""Experiment Framework - A/B testing and experimental feature management."""

from __future__ import annotations

import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class ExperimentStatus(Enum):
    """Status of an experiment."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Experiment:
    """An experimental feature or change.
    
    Attributes:
        id: Unique experiment identifier
        name: Experiment name
        description: What this experiment tests
        hypothesis: The hypothesis being tested
        success_metric: How success is measured
        control_patch: Patch for control group
        treatment_patch: Patch for treatment group
        status: Current status
        created_at: When experiment was created
        started_at: When experiment started
        completed_at: When experiment completed
        metrics: Collected metrics
    """
    
    id: str
    name: str
    description: str
    hypothesis: str
    success_metric: str
    control_patch: str = ""
    treatment_patch: str = ""
    status: ExperimentStatus = ExperimentStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    branch: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "success_metric": self.success_metric,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metrics": self.metrics,
        }


@dataclass
class ExperimentResult:
    """Result of an experiment run.
    
    Attributes:
        experiment_id: Parent experiment
        variant: control or treatment
        success: Whether the run succeeded
        metric_values: Measured metric values
        duration_ms: How long the run took
        timestamp: When this result was recorded
        artifacts: Paths to output artifacts
    """
    
    experiment_id: str
    variant: str
    success: bool
    metric_values: dict[str, float] = field(default_factory=dict)
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    artifacts: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "variant": self.variant,
            "success": self.success,
            "metric_values": self.metric_values,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "artifacts": self.artifacts,
        }


class ExperimentManager:
    """Manages experiments and A/B tests.
    
    This class provides isolation and tracking for experimental
    changes, enabling data-driven decision making.
    """
    
    def __init__(self, repo_path: str | None = None):
        self.repo_path = Path(repo_path or "")
        self._experiments: dict[str, Experiment] = {}
        self._results: dict[str, list[ExperimentResult]] = {}
        self._lock = threading.Lock()
    
    def create(
        self,
        name: str,
        hypothesis: str,
        success_metric: str,
        description: str = "",
        control_patch: str = "",
        treatment_patch: str = "",
    ) -> Experiment:
        """Create a new experiment.
        
        Args:
            name: Experiment name
            hypothesis: The hypothesis being tested
            success_metric: How success is measured
            description: What this experiment tests
            control_patch: Patch for control group
            treatment_patch: Patch for treatment group
            
        Returns:
            The created Experiment
        """
        with self._lock:
            experiment = Experiment(
                id=uuid.uuid4().hex,
                name=name,
                hypothesis=hypothesis,
                success_metric=success_metric,
                description=description,
                control_patch=control_patch,
                treatment_patch=treatment_patch,
            )
            
            self._experiments[experiment.id] = experiment
            self._results[experiment.id] = []
            
            return experiment
    
    def start(self, experiment_id: str) -> bool:
        """Start an experiment.
        
        Args:
            experiment_id: Experiment to start
            
        Returns:
            True if started successfully
        """
        with self._lock:
            experiment = self._experiments.get(experiment_id)
            
            if not experiment:
                return False
            
            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = datetime.now()
            
            # Create experiment branches
            if self.repo_path.exists():
                self._create_branches(experiment)
            
            return True
    
    def _create_branches(self, experiment: Experiment) -> None:
        """Create git branches for experiment variants."""
        # This is a simplified version - real implementation would
        # use git worktrees or branches
        
        experiment.branch = f"experiment/{experiment.id[:8]}"
    
    def record_result(
        self,
        experiment_id: str,
        variant: str,
        success: bool,
        metric_values: dict[str, float],
        duration_ms: int = 0,
        artifacts: list[str] | None = None,
    ) -> ExperimentResult:
        """Record a result for an experiment.
        
        Args:
            experiment_id: Parent experiment
            variant: control or treatment
            success: Whether run succeeded
            metric_values: Measured metrics
            duration_ms: Run duration
            artifacts: Output artifacts
            
        Returns:
            The recorded ExperimentResult
        """
        with self._lock:
            result = ExperimentResult(
                experiment_id=experiment_id,
                variant=variant,
                success=success,
                metric_values=metric_values,
                duration_ms=duration_ms,
                artifacts=artifacts or [],
            )
            
            if experiment_id in self._results:
                self._results[experiment_id].append(result)
            
            return result
    
    def complete(self, experiment_id: str) -> dict[str, Any]:
        """Mark an experiment as completed and compute results.
        
        Args:
            experiment_id: Experiment to complete
            
        Returns:
            Dict with experiment summary and statistical analysis
        """
        with self._lock:
            experiment = self._experiments.get(experiment_id)
            
            if not experiment:
                return {"error": "Experiment not found"}
            
            experiment.status = ExperimentStatus.COMPLETED
            experiment.completed_at = datetime.now()
            
            # Compute summary
            results = self._results.get(experiment_id, [])
            control_results = [r for r in results if r.variant == "control"]
            treatment_results = [r for r in results if r.variant == "treatment"]
            
            # Calculate averages
            control_avg = self._calculate_avg_metrics(control_results)
            treatment_avg = self._calculate_avg_metrics(treatment_results)
            
            # Determine winner
            improvement = {}
            for metric in treatment_avg:
                if metric in control_avg and control_avg[metric] > 0:
                    pct = ((treatment_avg[metric] - control_avg[metric]) / control_avg[metric]) * 100
                    improvement[metric] = pct
            
            experiment.metrics = {
                "control_avg": control_avg,
                "treatment_avg": treatment_avg,
                "improvement_pct": improvement,
                "control_runs": len(control_results),
                "treatment_runs": len(treatment_results),
                "total_runs": len(results),
            }
            
            return {
                "experiment": experiment.to_dict(),
                "summary": experiment.metrics,
                "winner": self._determine_winner(improvement),
            }
    
    def _calculate_avg_metrics(
        self,
        results: list[ExperimentResult],
    ) -> dict[str, float]:
        """Calculate average metric values."""
        if not results:
            return {}
        
        metrics: dict[str, list[float]] = {}
        
        for result in results:
            for metric, value in result.metric_values.items():
                if metric not in metrics:
                    metrics[metric] = []
                metrics[metric].append(value)
        
        return {
            metric: sum(values) / len(values)
            for metric, values in metrics.items()
        }
    
    def _determine_winner(
        self,
        improvement: dict[str, float],
    ) -> str:
        """Determine which variant won."""
        if not improvement:
            return "inconclusive"
        
        # For success rate, higher is better
        # For duration, lower is better
        total = sum(improvement.values())
        
        if abs(total) < 5:  # Less than 5% difference
            return "inconclusive"
        
        return "treatment" if total > 0 else "control"
    
    def promote_patch(self, experiment_id: str) -> dict[str, Any]:
        """Promote the winning patch from an experiment.
        
        Args:
            experiment_id: Experiment to promote
            
        Returns:
            Dict with promotion result
        """
        with self._lock:
            experiment = self._experiments.get(experiment_id)
            
            if not experiment:
                return {"success": False, "error": "Experiment not found"}
            
            if experiment.status != ExperimentStatus.COMPLETED:
                return {"success": False, "error": "Experiment not completed"}
            
            winner = self._determine_winner(experiment.metrics.get("improvement_pct", {}))
            
            if winner == "inconclusive":
                return {"success": False, "error": "No clear winner"}
            
            # Return the patch to apply
            patch = experiment.treatment_patch if winner == "treatment" else experiment.control_patch
            
            return {
                "success": True,
                "winner": winner,
                "patch": patch,
                "experiment": experiment.to_dict(),
            }
    
    def discard(self, experiment_id: str) -> dict[str, Any]:
        """Discard an experiment and clean up.
        
        Args:
            experiment_id: Experiment to discard
            
        Returns:
            Dict with discard result
        """
        with self._lock:
            if experiment_id in self._experiments:
                experiment = self._experiments[experiment_id]
                experiment.status = ExperimentStatus.CANCELLED
                
                # Clean up branches if we created them
                # (simplified - would do actual git cleanup)
                
                return {
                    "success": True,
                    "experiment_id": experiment_id,
                    "message": f"Experiment {experiment_id} discarded",
                }
            
            return {"success": False, "error": "Experiment not found"}
    
    def get(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        with self._lock:
            return self._experiments.get(experiment_id)
    
    def list(self) -> list[Experiment]:
        """List all experiments."""
        with self._lock:
            return list(self._experiments.values())


def create_experiment(
    name: str,
    hypothesis: str,
    success_metric: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a new experiment.
    
    Args:
        name: Experiment name
        hypothesis: The hypothesis being tested
        success_metric: How success is measured
        description: What this experiment tests
        
    Returns:
        Dict with experiment info
    """
    manager = ExperimentManager()
    experiment = manager.create(
        name=name,
        hypothesis=hypothesis,
        success_metric=success_metric,
        description=description,
    )
    
    return {
        "success": True,
        "experiment": experiment.to_dict(),
        "message": f"Created experiment: {name}",
    }


def run_experiment(
    experiment_id: str,
    variant: str = "treatment",
) -> dict[str, Any]:
    """Run an experiment variant.
    
    Args:
        experiment_id: Experiment to run
        variant: Which variant (control or treatment)
        
    Returns:
        Dict with run result
    """
    manager = ExperimentManager()
    experiment = manager.get(experiment_id)
    
    if not experiment:
        return {"success": False, "error": "Experiment not found"}
    
    manager.start(experiment_id)
    
    # In a real implementation, this would apply the patch and run tests
    # For now, return instructions
    return {
        "success": True,
        "experiment_id": experiment_id,
        "variant": variant,
        "patch": experiment.treatment_patch if variant == "treatment" else experiment.control_patch,
        "message": f"Run {variant} variant of experiment {experiment_id}",
    }
