"""Test Mapper - Maps tests to code symbols for targeted test selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import TestMapping
from .storage import StateModelStorage, get_storage


@dataclass
class TestSelection:
    """Represents a selected test set for a change."""
    
    tests: list[dict[str, Any]]
    confidence_scores: dict[str, float]
    total_tests: int
    confidence: float
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "tests_to_run": [t["name"] for t in self.tests],
            "test_files": list(set(t["file"] for t in self.tests)),
            "total_tests": self.total_tests,
            "confidence": self.confidence,
            "confidence_scores": self.confidence_scores,
        }


def find_tests_for_symbol(
    symbol_name: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> TestSelection:
    """Find all tests that exercise a specific symbol.
    
    Args:
        symbol_name: Name of the symbol
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        TestSelection with matched tests
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    mappings = store.get_tests_for_symbol(symbol_name, snapshot_id)
    
    tests = []
    confidence_scores = {}
    
    for mapping in mappings:
        tests.append({
            "name": mapping.test_name,
            "file": mapping.test_file_path,
            "method": mapping.mapping_method,
            "confidence": mapping.confidence,
        })
        confidence_scores[mapping.test_name] = mapping.confidence
    
    avg_confidence = sum(m.confidence for m in mappings) / len(mappings) if mappings else 0.0
    
    return TestSelection(
        tests=tests,
        confidence_scores=confidence_scores,
        total_tests=len(tests),
        confidence=avg_confidence,
    )


def find_tests_for_file(
    file_path: str,
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> TestSelection:
    """Find tests that test code in a specific file.
    
    Args:
        file_path: Path to the source file
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        TestSelection with matched tests
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    # Get symbols in the file
    symbols = store.get_symbols_in_file(file_path, snapshot_id)
    
    # Collect tests for all symbols
    all_tests: dict[str, dict[str, Any]] = {}
    confidence_scores: dict[str, float] = {}
    
    for symbol in symbols:
        mappings = store.get_tests_for_symbol(symbol.name, snapshot_id)
        for mapping in mappings:
            test_key = f"{mapping.test_file_path}::{mapping.test_name}"
            if test_key not in all_tests:
                all_tests[test_key] = {
                    "name": mapping.test_name,
                    "file": mapping.test_file_path,
                    "targets": [],
                    "method": mapping.mapping_method,
                    "confidence": mapping.confidence,
                }
                confidence_scores[mapping.test_name] = mapping.confidence
            
            all_tests[test_key]["targets"].append(symbol.name)
    
    tests = list(all_tests.values())
    
    return TestSelection(
        tests=tests,
        confidence_scores=confidence_scores,
        total_tests=len(tests),
        confidence=0.7,  # Estimated based on file-level match
    )


def find_tests_for_change(
    files_changed: list[str],
    snapshot_id: str | None = None,
    storage: StateModelStorage | None = None,
) -> TestSelection:
    """Find tests relevant to a set of changed files.
    
    This is the primary function for targeted test selection.
    It finds all tests that could be affected by the changes.
    
    Args:
        files_changed: List of file paths that changed
        snapshot_id: Optional snapshot ID
        storage: Optional storage instance
        
    Returns:
        TestSelection with tests to run
    """
    store = storage or get_storage()
    
    if snapshot_id is None:
        snapshot_id = ""
    
    all_tests: dict[str, dict[str, Any]] = {}
    confidence_scores: dict[str, float] = {}
    
    for file_path in files_changed:
        # Get tests for this file
        file_tests = find_tests_for_file(file_path, snapshot_id, store)
        
        for test in file_tests.tests:
            test_key = f"{test['file']}::{test['name']}"
            if test_key not in all_tests:
                all_tests[test_key] = test.copy()
                all_tests[test_key]["affected_files"] = []
                confidence_scores[test["name"]] = test.get("confidence", 0.5)
            
            all_tests[test_key]["affected_files"].append(file_path)
    
    tests = list(all_tests.values())
    
    # Calculate overall confidence
    if tests:
        avg_confidence = sum(t.get("confidence", 0.5) for t in tests) / len(tests)
    else:
        avg_confidence = 0.0
    
    return TestSelection(
        tests=tests,
        confidence_scores=confidence_scores,
        total_tests=len(tests),
        confidence=avg_confidence,
    )


def rank_tests_by_relevance(
    tests: list[dict[str, Any]],
    change_set: list[str],
) -> list[dict[str, Any]]:
    """Rank tests by relevance to a change set.
    
    Args:
        tests: List of test dicts
        change_set: List of changed files
        
    Returns:
        Tests sorted by relevance
    """
    ranked = []
    
    for test in tests:
        score = 0.0
        
        # Check if test's affected files overlap with change set
        affected = test.get("affected_files", [])
        for f in affected:
            if f in change_set:
                score += 1.0
        
        # Boost by confidence
        score += test.get("confidence", 0.5) * 0.5
        
        ranked.append((score, test))
    
    # Sort by score descending
    ranked.sort(key=lambda x: -x[0])
    
    return [t for _, t in ranked]


def infer_test_target_from_name(
    test_name: str,
) -> str | None:
    """Infer the target symbol name from a test name.
    
    Args:
        test_name: Name of the test function
        
    Returns:
        Inferred target symbol name or None
    """
    import re
    
    # Remove common test prefixes
    name = test_name
    
    patterns = [
        (r'^test_', ''),
        (r'^Test', ''),
        (r'_test$', ''),
        (r'Test$', ''),
    ]
    
    for pattern, replacement in patterns:
        name = re.sub(pattern, replacement, name)
    
    # Convert snake_case to potential symbol name
    # e.g., test_user_authentication -> test_user_authentication -> user_authentication
    parts = name.split('_')
    
    # Try to find a meaningful target
    if len(parts) > 1:
        # Return the last meaningful part (method being tested)
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] and len(parts[i]) > 2:
                return parts[i]
    
    return name if name else None
