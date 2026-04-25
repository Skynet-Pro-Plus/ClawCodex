"""Patch Safety Engine - Validates patches before application."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PatchValidationResult:
    """Result of patch validation."""
    
    status: str = "safe"  # safe, risky, breaking
    risk_score: float = 0.0
    
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    required_followups: list[str] = field(default_factory=list)
    recommended_tests: list[str] = field(default_factory=list)
    
    files_affected: list[str] = field(default_factory=list)
    syntax_valid: bool = True
    imports_valid: bool = True
    symbols_valid: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "risk_score": self.risk_score,
            "issues": self.issues,
            "warnings": self.warnings,
            "required_followups": self.required_followups,
            "recommended_tests": self.recommended_tests,
            "files_affected": self.files_affected,
            "syntax_valid": self.syntax_valid,
            "imports_valid": self.imports_valid,
            "symbols_valid": self.symbols_valid,
        }


@dataclass
class SimulationResult:
    """Result of patch simulation."""
    
    status: str = "safe"
    risk_score: float = 0.0
    
    files_affected: list[str] = field(default_factory=list)
    dependency_breakage_probability: float = 0.0
    test_coverage_impact: float = 0.0
    
    rollback_plan: str = ""
    changes_summary: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "risk_score": self.risk_score,
            "files_affected": self.files_affected,
            "dependency_breakage_probability": self.dependency_breakage_probability,
            "test_coverage_impact": self.test_coverage_impact,
            "rollback_plan": self.rollback_plan,
            "changes_summary": self.changes_summary,
        }


class PatchSafetyEngine:
    """Validates patches before they are applied."""
    
    def __init__(self):
        self.issues = []
        self.warnings = []
    
    def validate(self, diff: str) -> PatchValidationResult:
        """Validate a patch before application.
        
        Args:
            diff: The patch/diff content
            
        Returns:
            PatchValidationResult with validation outcome
        """
        result = PatchValidationResult()
        
        # Parse diff
        result.files_affected = self._parse_files_from_diff(diff)
        
        # Check syntax
        result.syntax_valid = self._check_syntax(result.files_affected)
        if not result.syntax_valid:
            result.issues.append("Syntax errors detected in patched files")
            result.status = "risky"
        
        # Check imports
        result.imports_valid = self._check_imports(result.files_affected)
        if not result.imports_valid:
            result.warnings.append("Some imports may be unresolved")
        
        # Check symbols
        result.symbols_valid = self._check_symbols(result.files_affected)
        if not result.symbols_valid:
            result.warnings.append("Some symbol references may be broken")
        
        # Calculate overall risk
        result.risk_score = self._calculate_risk(result)
        
        # Determine status
        if result.issues:
            result.status = "breaking"
        elif result.warnings:
            result.status = "risky"
        else:
            result.status = "safe"
        
        # Generate followups
        result.required_followups = self._generate_followups(result)
        
        # Find recommended tests
        result.recommended_tests = self._find_recommended_tests(result.files_affected)
        
        return result
    
    def simulate(
        self,
        diff: str,
        include_side_effects: bool = True,
    ) -> SimulationResult:
        """Simulate applying a patch.
        
        Args:
            diff: The patch/diff content
            include_side_effects: Whether to analyze side effects
            
        Returns:
            SimulationResult with predicted effects
        """
        result = SimulationResult()
        
        # Parse files from diff
        files = self._parse_files_from_diff(diff)
        result.files_affected = files
        
        # Analyze side effects
        if include_side_effects:
            result.dependency_breakage_probability = self._analyze_dependency_impact(files)
            result.test_coverage_impact = self._analyze_test_coverage(files)
        
        # Generate rollback plan
        result.rollback_plan = self._generate_rollback_plan(files)
        
        # Summary
        result.changes_summary = self._summarize_changes(diff)
        
        # Calculate risk
        result.risk_score = self._calculate_simulation_risk(result)
        
        if result.risk_score > 0.7:
            result.status = "risky"
        elif result.risk_score > 0.3:
            result.status = "safe"
        
        return result
    
    def _parse_files_from_diff(self, diff: str) -> list[str]:
        """Extract file paths from a diff."""
        files = []
        
        # Match diff file headers
        patterns = [
            r'^diff --git a/(.+?) b/\1',
            r'^--- a/(.+)',
            r'^\+\+\+ b/(.+)',
        ]
        
        for line in diff.split('\n'):
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    path = match.group(1)
                    if path and path not in files:
                        files.append(path)
        
        return files
    
    def _check_syntax(self, files: list[str]) -> bool:
        """Check if files have valid Python syntax."""
        for file in files:
            if file.endswith('.py'):
                try:
                    with open(file, 'r') as f:
                        compile(f.read(), file, 'exec')
                except SyntaxError:
                    return False
                except FileNotFoundError:
                    pass
        return True
    
    def _check_imports(self, files: list[str]) -> bool:
        """Check if imports can be resolved."""
        # Simplified check - would need more sophisticated analysis
        return True
    
    def _check_symbols(self, files: list[str]) -> bool:
        """Check if symbol references are valid."""
        # Simplified check - would need more sophisticated analysis
        return True
    
    def _analyze_dependency_impact(self, files: list[str]) -> float:
        """Analyze probability of dependency breakage."""
        core_files = ['src/', 'lib/', 'core/']
        core_count = sum(1 for f in files if any(c in f for c in core_files))
        
        if core_count > 3:
            return 0.7
        elif core_count > 0:
            return 0.3
        return 0.1
    
    def _analyze_test_coverage(self, files: list[str]) -> float:
        """Analyze test coverage impact."""
        test_files = [f for f in files if 'test' in f.lower()]
        source_files = [f for f in files if not f.endswith('.py') or 'test' not in f.lower()]
        
        if not source_files:
            return 0.0
        
        # Rough estimate
        return len(test_files) / len(source_files) * 0.5
    
    def _generate_rollback_plan(self, files: list[str]) -> str:
        """Generate instructions for rolling back the patch."""
        lines = [
            "# Rollback Plan",
            "",
            "To rollback this patch:",
            "",
        ]
        
        for f in files[:5]:  # Limit to first 5 files
            lines.append(f"  git checkout HEAD -- {f}")
        
        if len(files) > 5:
            lines.append(f"  # ... and {len(files) - 5} more files")
        
        return '\n'.join(lines)
    
    def _summarize_changes(self, diff: str) -> str:
        """Summarize the changes in the diff."""
        lines_added = diff.count('\n+')
        lines_removed = diff.count('\n-')
        files_changed = len(self._parse_files_from_diff(diff))
        
        return f"{files_changed} files changed, {lines_added} insertions(+), {lines_removed} deletions(-)"
    
    def _calculate_risk(self, result: PatchValidationResult) -> float:
        """Calculate overall risk score."""
        score = 0.0
        
        if not result.syntax_valid:
            score += 0.5
        
        if not result.imports_valid:
            score += 0.2
        
        if not result.symbols_valid:
            score += 0.15
        
        if len(result.files_affected) > 5:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_simulation_risk(self, result: SimulationResult) -> float:
        """Calculate simulation risk score."""
        score = 0.0
        
        score += result.dependency_breakage_probability * 0.5
        
        if len(result.files_affected) > 10:
            score += 0.2
        
        return min(score, 1.0)
    
    def _generate_followups(self, result: PatchValidationResult) -> list[str]:
        """Generate required follow-up actions."""
        followups = []
        
        if not result.syntax_valid:
            followups.append("Fix syntax errors before applying")
        
        if not result.imports_valid:
            followups.append("Verify all imports can be resolved")
        
        result.api_breaking = any('api' in f.lower() for f in result.files_affected)
        if result.api_breaking:
            followups.append("Update API documentation")
        
        return followups
    
    def _find_recommended_tests(self, files: list[str]) -> list[str]:
        """Find tests that should be run for these files."""
        tests = []
        
        for f in files:
            if f.endswith('.py'):
                # Generate corresponding test file path
                test_path = f.replace('/src/', '/tests/').replace('.py', '_test.py')
                tests.append(test_path)
        
        return tests


def validate_patch(diff: str) -> PatchValidationResult:
    """Convenience function for patch validation."""
    engine = PatchSafetyEngine()
    return engine.validate(diff)


def simulate_patch(diff: str, include_side_effects: bool = True) -> SimulationResult:
    """Convenience function for patch simulation."""
    engine = PatchSafetyEngine()
    return engine.simulate(diff, include_side_effects)
