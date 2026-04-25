"""Benchmark Runner - Execute and track performance benchmarks."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class BenchmarkStatus(Enum):
    """Status of a benchmark run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Benchmark:
    """A benchmark specification.
    
    Attributes:
        id: Unique benchmark identifier
        name: Benchmark name
        description: What this benchmark measures
        command: Command to execute
        iterations: Number of iterations
        timeout_sec: Maximum execution time
        warmup_runs: Number of warmup runs
        created_at: When benchmark was created
    """
    
    id: str
    name: str
    description: str
    command: str
    iterations: int = 5
    timeout_sec: int = 300
    warmup_runs: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "iterations": self.iterations,
            "timeout_sec": self.timeout_sec,
            "warmup_runs": self.warmup_runs,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BenchmarkResult:
    """Result of a benchmark run.
    
    Attributes:
        benchmark_id: Parent benchmark
        run_id: Unique run identifier
        status: Run status
        duration_ms: Total duration
        iterations: Number of iterations completed
        iteration_times: Time for each iteration (ms)
        avg_time: Average iteration time
        min_time: Minimum iteration time
        max_time: Maximum iteration time
        std_dev: Standard deviation
        stdout: Command output
        stderr: Error output
        timestamp: When run started
    """
    
    benchmark_id: str
    run_id: str
    status: BenchmarkStatus
    duration_ms: int = 0
    iterations: int = 0
    iteration_times: list[float] = field(default_factory=list)
    avg_time: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    std_dev: float = 0.0
    stdout: str = ""
    stderr: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "iterations": self.iterations,
            "iteration_times": self.iteration_times,
            "avg_time": self.avg_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "std_dev": self.std_dev,
            "timestamp": self.timestamp.isoformat(),
        }


class BenchmarkRunner:
    """Runs and tracks performance benchmarks.
    
    This class executes benchmark commands multiple times,
    collects timing data, and computes statistics.
    """
    
    def __init__(self, working_dir: str | None = None):
        self.working_dir = Path(working_dir or "")
        self._benchmarks: dict[str, Benchmark] = {}
        self._results: dict[str, list[BenchmarkResult]] = {}
        self._lock = threading.Lock()
    
    def register(
        self,
        name: str,
        command: str,
        description: str = "",
        iterations: int = 5,
        warmup_runs: int = 1,
        timeout_sec: int = 300,
    ) -> Benchmark:
        """Register a new benchmark.
        
        Args:
            name: Benchmark name
            command: Command to execute
            description: What this measures
            iterations: Number of iterations
            warmup_runs: Warmup runs before timing
            timeout_sec: Maximum execution time
            
        Returns:
            The created Benchmark
        """
        benchmark = Benchmark(
            id=uuid.uuid4().hex,
            name=name,
            description=description,
            command=command,
            iterations=iterations,
            warmup_runs=warmup_runs,
            timeout_sec=timeout_sec,
        )
        
        with self._lock:
            self._benchmarks[benchmark.id] = benchmark
            self._results[benchmark.id] = []
        
        return benchmark
    
    def run(self, benchmark_id: str) -> BenchmarkResult:
        """Run a benchmark.
        
        Args:
            benchmark_id: Benchmark to run
            
        Returns:
            BenchmarkResult with timing data
        """
        with self._lock:
            benchmark = self._benchmarks.get(benchmark_id)
        
        if not benchmark:
            return BenchmarkResult(
                benchmark_id=benchmark_id,
                run_id=uuid.uuid4().hex,
                status=BenchmarkStatus.FAILED,
                stderr="Benchmark not found",
            )
        
        return self._execute(benchmark)
    
    def _execute(self, benchmark: Benchmark) -> BenchmarkResult:
        """Execute a benchmark."""
        result = BenchmarkResult(
            benchmark_id=benchmark.id,
            run_id=uuid.uuid4().hex,
            status=BenchmarkStatus.RUNNING,
        )
        
        start_time = time.perf_counter()
        
        # Warmup runs
        for _ in range(benchmark.warmup_runs):
            self._run_command(benchmark.command)
        
        # Timed iterations
        iteration_times = []
        all_stdout = []
        all_stderr = []
        
        for i in range(benchmark.iterations):
            iter_start = time.perf_counter()
            
            stdout, stderr, success = self._run_command(benchmark.command)
            
            iter_duration = (time.perf_counter() - iter_start) * 1000  # ms
            iteration_times.append(iter_duration)
            
            all_stdout.append(stdout)
            all_stderr.append(stderr)
            
            if not success:
                result.status = BenchmarkStatus.FAILED
                result.stderr = stderr
                result.duration_ms = int((time.perf_counter() - start_time) * 1000)
                return result
        
        # Calculate statistics
        result.status = BenchmarkStatus.COMPLETED
        result.iterations = len(iteration_times)
        result.iteration_times = iteration_times
        result.avg_time = sum(iteration_times) / len(iteration_times) if iteration_times else 0
        result.min_time = min(iteration_times) if iteration_times else 0
        result.max_time = max(iteration_times) if iteration_times else 0
        result.std_dev = self._calculate_std_dev(iteration_times)
        result.stdout = "\n".join(all_stdout[:3])  # First 3 outputs
        result.duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Store result
        with self._lock:
            self._results[benchmark.id].append(result)
        
        return result
    
    def _run_command(
        self,
        command: str,
    ) -> tuple[str, str, bool]:
        """Run a benchmark command.
        
        Returns:
            Tuple of (stdout, stderr, success)
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir) if self.working_dir.exists() else None,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.stdout, result.stderr, result.returncode == 0
        except subprocess.TimeoutExpired:
            return "", "Command timed out", False
        except Exception as e:
            return "", str(e), False
    
    def _calculate_std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def get_results(
        self,
        benchmark_id: str,
        limit: int = 10,
    ) -> list[BenchmarkResult]:
        """Get results for a benchmark.
        
        Args:
            benchmark_id: Benchmark to query
            limit: Maximum results to return
            
        Returns:
            List of BenchmarkResult objects
        """
        with self._lock:
            results = self._results.get(benchmark_id, [])
            return sorted(results, key=lambda r: r.timestamp, reverse=True)[:limit]
    
    def compare(
        self,
        benchmark_id: str,
        time_window_hours: int = 24,
    ) -> dict[str, Any]:
        """Compare recent results for a benchmark.
        
        Args:
            benchmark_id: Benchmark to analyze
            time_window_hours: Hours to look back
            
        Returns:
            Dict with comparison statistics
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(hours=time_window_hours)
        
        with self._lock:
            results = [
                r for r in self._results.get(benchmark_id, [])
                if r.timestamp >= cutoff and r.status == BenchmarkStatus.COMPLETED
            ]
        
        if not results:
            return {
                "count": 0,
                "message": "No results in time window",
            }
        
        all_avg = [r.avg_time for r in results]
        all_min = [r.min_time for r in results]
        
        return {
            "count": len(results),
            "avg_time_avg": sum(all_avg) / len(all_avg),
            "avg_time_min": min(all_min),
            "avg_time_max": max(all_avg),
            "latest": results[0].to_dict() if results else None,
            "trend": "stable",  # Could compute actual trend
        }


def run_benchmark(
    name: str,
    command: str,
    description: str = "",
    iterations: int = 5,
) -> dict[str, Any]:
    """Run a benchmark and return results.
    
    Args:
        name: Benchmark name
        command: Command to execute
        description: What this measures
        iterations: Number of iterations
        
    Returns:
        Dict with benchmark results
    """
    runner = BenchmarkRunner()
    benchmark = runner.register(
        name=name,
        command=command,
        description=description,
        iterations=iterations,
    )
    
    result = runner.run(benchmark.id)
    
    return {
        "benchmark": benchmark.to_dict(),
        "result": result.to_dict(),
    }
