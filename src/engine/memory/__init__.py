"""Failure Memory Module - Persistent debug memory and institutional learning."""

from .failure_patterns import (
    FailurePattern,
    FailurePatternDB,
    record_failure_pattern,
    search_failure_patterns,
    suggest_known_fix,
)
from .success_patterns import (
    SuccessfulRepair,
    SuccessRegistry,
    record_successful_repair,
    get_successful_patterns,
)

__all__ = [
    # Failure patterns
    "FailurePattern",
    "FailurePatternDB",
    "record_failure_pattern",
    "search_failure_patterns",
    "suggest_known_fix",
    # Success patterns
    "SuccessfulRepair",
    "SuccessRegistry",
    "record_successful_repair",
    "get_successful_patterns",
]
