"""Experimentation Module - A/B testing and benchmark execution framework."""

from .experiment import (
    Experiment,
    ExperimentResult,
    ExperimentManager,
    create_experiment,
    run_experiment,
)
from .benchmark import (
    Benchmark,
    BenchmarkResult,
    BenchmarkRunner,
    run_benchmark,
)
from .orchestrator_benchmarks import (
    BENCHMARK_TASKS,
    OrchestratorBenchmarkTask,
    list_orchestrator_benchmarks,
    run_orchestrator_benchmark,
)

__all__ = [
    # Experiments
    "Experiment",
    "ExperimentResult",
    "ExperimentManager",
    "create_experiment",
    "run_experiment",
    # Benchmarks
    "Benchmark",
    "BenchmarkResult",
    "BenchmarkRunner",
    "BENCHMARK_TASKS",
    "OrchestratorBenchmarkTask",
    "list_orchestrator_benchmarks",
    "run_benchmark",
    "run_orchestrator_benchmark",
]
