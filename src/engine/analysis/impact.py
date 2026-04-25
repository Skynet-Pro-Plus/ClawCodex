"""Impact Analysis Engine - Predicts code change impact."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..state_model import get_storage, find_tests_for_change, search_symbols


@dataclass
class ImpactReport:
    """Report predicting the impact of a code change."""
    
    target: str
    change_description: str
    
    files_affected: list[str] = field(default_factory=list)
    symbols_affected: list[str] = field(default_factory=list)
    tests_affected: list[str] = field(default_factory=list)
    
    config_impact: list[str] = field(default_factory=list)
    api_breaking: bool = False
    
    risk_score: float = 0.0
    risk_factors: list[str] = field(default_factory=list)
    
    estimated_blast_radius: str = "low"
    
    recommended_actions: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "change_description": self.change_description,
            "files_affected": self.files_affected,
            "symbols_affected": self.symbols_affected,
            "tests_affected": self.tests_affected,
            "config_impact": self.config_impact,
            "api_breaking": self.api_breaking,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "blast_radius": self.estimated_blast_radius,
            "recommended_actions": self.recommended_actions,
        }


class ImpactAnalyzer:
    """Analyzes the potential impact of code changes."""
    
    def __init__(self, storage=None):
        self.storage = storage or get_storage()
    
    def predict(
        self,
        target: str,
        change_description: str,
    ) -> ImpactReport:
        """Predict the impact of a proposed change.
        
        Args:
            target: File or symbol being changed
            change_description: Description of the change
            
        Returns:
            ImpactReport with predicted impact
        """
        report = ImpactReport(
            target=target,
            change_description=change_description,
        )
        
        # Analyze change description
        report.api_breaking = self._check_api_breaking(change_description)
        report.config_impact = self._check_config_impact(target, change_description)
        
        # Find affected symbols
        symbols = self._find_affected_symbols(target)
        report.symbols_affected = [s.qualified_name for s in symbols]
        
        # Find affected files
        report.files_affected = list(set(s.file_path for s in symbols))
        if target.endswith('.py'):
            report.files_affected.append(target)
        
        # Calculate risk score
        report.risk_score = self._calculate_risk_score(report)
        
        # Determine blast radius
        report.estimated_blast_radius = self._estimate_blast_radius(report)
        
        # Find affected tests
        test_selection = find_tests_for_change(report.files_affected)
        report.tests_affected = test_selection.to_dict()["tests_to_run"]
        
        # Generate recommendations
        report.recommended_actions = self._generate_recommendations(report)
        
        # Add risk factors
        report.risk_factors = self._identify_risk_factors(report)
        
        return report
    
    def _check_api_breaking(self, change_description: str) -> bool:
        """Check if the change is API-breaking."""
        breaking_patterns = [
            r'change.*signature',
            r'change.*parameter',
            r'remove.*parameter',
            r'add.*required.*param',
            r'change.*return.*type',
            r'change.*response',
        ]
        
        desc_lower = change_description.lower()
        return any(re.search(p, desc_lower) for p in breaking_patterns)
    
    def _check_config_impact(self, target: str, change_description: str) -> list[str]:
        """Check for configuration impact."""
        config_files = ['config', 'settings', '.env', 'pyproject.toml', 'setup.py']
        impacts = []
        
        for cf in config_files:
            if cf in target or cf in change_description:
                impacts.append(cf)
        
        return impacts
    
    def _find_affected_symbols(self, target: str) -> list:
        """Find symbols that might be affected."""
        symbols = []
        
        # Search by target name
        if target.endswith('.py'):
            name = target.split('/')[-1].replace('.py', '')
            symbols = search_symbols(name)
        else:
            # Assume it's a symbol name
            symbols = search_symbols(target)
        
        return symbols
    
    def _calculate_risk_score(self, report: ImpactReport) -> float:
        """Calculate risk score (0.0 - 1.0)."""
        score = 0.0
        
        # API breaking is high risk
        if report.api_breaking:
            score += 0.4
        
        # Many files affected
        if len(report.files_affected) > 5:
            score += 0.2
        elif len(report.files_affected) > 2:
            score += 0.1
        
        # Many tests affected
        if len(report.tests_affected) > 10:
            score += 0.15
        
        # Config changes
        if report.config_impact:
            score += 0.15
        
        # Core module changes (src/, lib/)
        core_files = [f for f in report.files_affected if f.startswith(('src/', 'lib/'))]
        if core_files:
            score += 0.1
        
        return min(score, 1.0)
    
    def _estimate_blast_radius(self, report: ImpactReport) -> str:
        """Estimate the blast radius of the change."""
        if report.risk_score < 0.2:
            return "low"
        elif report.risk_score < 0.5:
            return "medium"
        elif report.risk_score < 0.8:
            return "high"
        else:
            return "critical"
    
    def _generate_recommendations(self, report: ImpactReport) -> list[str]:
        """Generate recommended actions based on impact."""
        recommendations = []
        
        if report.api_breaking:
            recommendations.append("Update API documentation")
            recommendations.append("Check backward compatibility")
            recommendations.append("Update dependent services")
        
        if len(report.tests_affected) > 5:
            recommendations.append("Run targeted tests before committing")
        
        if report.config_impact:
            recommendations.append("Update configuration documentation")
            recommendations.append("Test in all environments")
        
        if report.risk_score > 0.5:
            recommendations.append("Consider breaking the change into smaller steps")
            recommendations.append("Get code review before merge")
        
        return recommendations
    
    def _identify_risk_factors(self, report: ImpactReport) -> list[str]:
        """Identify specific risk factors."""
        factors = []
        
        if report.api_breaking:
            factors.append("API signature change detected")
        
        if len(report.files_affected) > 3:
            factors.append(f"Multiple files affected ({len(report.files_affected)})")
        
        if len(report.tests_affected) == 0:
            factors.append("No tests found for affected code")
        
        return factors


def predict_edit_impact(
    target: str,
    change_description: str,
) -> ImpactReport:
    """Convenience function for impact prediction."""
    analyzer = ImpactAnalyzer()
    return analyzer.predict(target, change_description)


def analyze_change_plan(plan: str) -> dict[str, Any]:
    """Analyze a change plan for potential impacts.
    
    Args:
        plan: Markdown change plan
        
    Returns:
        Dict with impact analysis
    """
    analyzer = ImpactAnalyzer()
    
    # Extract targets from plan
    targets = re.findall(r'`([^`]+)`', plan)
    
    impacts = []
    for target in targets[:10]:  # Limit to first 10
        if target.endswith('.py') or '.' in target:
            report = analyzer.predict(target, plan)
            impacts.append(report.to_dict())
    
    return {
        "plan_summary": plan[:200],
        "target_count": len(targets),
        "impacts": impacts,
        "overall_risk": max((i["risk_score"] for i in impacts), default=0.0),
    }
