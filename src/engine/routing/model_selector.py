"""Model Selector - Recommends optimal LLM models for agent stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Available models with their capabilities and costs
MODELS = {
    # High reasoning models
    "claude-opus-4": {
        "provider": "anthropic",
        "context_window": 200000,
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.075,
        "strengths": ["reasoning", "analysis", "code", "writing"],
        "max_output": 4096,
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "context_window": 200000,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "strengths": ["reasoning", "analysis", "code", "writing"],
        "max_output": 4096,
    },
    "claude-3-5-sonnet": {
        "provider": "anthropic",
        "context_window": 200000,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "strengths": ["reasoning", "analysis", "code", "writing"],
        "max_output": 8192,
    },
    "claude-3-haiku": {
        "provider": "anthropic",
        "context_window": 200000,
        "cost_per_1k_input": 0.00025,
        "cost_per_1k_output": 0.00125,
        "strengths": ["fast", "coding", "efficient"],
        "max_output": 4096,
    },
    # OpenAI models
    "gpt-4o": {
        "provider": "openai",
        "context_window": 128000,
        "cost_per_1k_input": 0.005,
        "cost_per_1k_output": 0.015,
        "strengths": ["reasoning", "code", "analysis", "multimodal"],
        "max_output": 4096,
    },
    "gpt-4-turbo": {
        "provider": "openai",
        "context_window": 128000,
        "cost_per_1k_input": 0.01,
        "cost_per_1k_output": 0.03,
        "strengths": ["reasoning", "code", "analysis"],
        "max_output": 4096,
    },
    "gpt-3.5-turbo": {
        "provider": "openai",
        "context_window": 16385,
        "cost_per_1k_input": 0.0005,
        "cost_per_1k_output": 0.0015,
        "strengths": ["fast", "cheap", "coding"],
        "max_output": 4096,
    },
    # O1 models
    "o1-preview": {
        "provider": "openai",
        "context_window": 128000,
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.06,
        "strengths": ["reasoning", "complex tasks"],
        "max_output": 32768,
    },
    "o1-mini": {
        "provider": "openai",
        "context_window": 128000,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.012,
        "strengths": ["reasoning", "code", "fast"],
        "max_output": 32768,
    },
    # Local/cheaper options
    "gpt-4o-mini": {
        "provider": "openai",
        "context_window": 128000,
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
        "strengths": ["fast", "cheap", "coding"],
        "max_output": 4096,
    },
}


@dataclass
class ModelRecommendation:
    """A model recommendation.
    
    Attributes:
        model: Recommended model name
        fallback_model: Fallback model if primary unavailable
        reasoning: Why this model was recommended
        estimated_cost: Estimated cost per 1k tokens
        strengths: Model strengths
    """
    
    model: str
    fallback_model: str
    reasoning: str
    estimated_cost: float
    strengths: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_model": self.model,
            "fallback_model": self.fallback_model,
            "reasoning": self.reasoning,
            "estimated_cost_per_1k_tokens": self.estimated_cost,
            "strengths": self.strengths,
        }


class ModelSelector:
    """Selects optimal LLM models for tasks.
    
    This class provides intelligent model selection based on
    task type, complexity, and cost constraints.
    """
    
    # Stage-specific requirements
    STAGE_REQUIREMENTS = {
        "planner": {
            "required_strengths": ["reasoning", "analysis"],
            "preferred_reasoning": True,
            "max_cost_tolerance": 0.02,
        },
        "coder": {
            "required_strengths": ["code"],
            "preferred_reasoning": True,
            "max_cost_tolerance": 0.01,
        },
        "reviewer": {
            "required_strengths": ["reasoning", "analysis"],
            "preferred_reasoning": True,
            "strict": True,
            "max_cost_tolerance": 0.015,
        },
        "debugger": {
            "required_strengths": ["reasoning"],
            "preferred_reasoning": True,
            "max_cost_tolerance": 0.02,
        },
        "tester": {
            "required_strengths": ["code"],
            "preferred_reasoning": False,
            "max_cost_tolerance": 0.005,
        },
        "writer": {
            "required_strengths": ["writing"],
            "preferred_reasoning": False,
            "max_cost_tolerance": 0.01,
        },
    }
    
    # Task type mappings
    TASK_TYPE_MAPPINGS = {
        "refactoring": "coder",
        "bug_fix": "debugger",
        "feature": "coder",
        "review": "reviewer",
        "testing": "tester",
        "planning": "planner",
        "documentation": "writer",
        "formatting": "tester",
    }
    
    def __init__(self, prefer_cheap: bool = False):
        self.prefer_cheap = prefer_cheap
    
    def recommend(
        self,
        stage: str,
        task_type: str | None = None,
        risk_level: str = "medium",
        repo_size: str = "medium",
    ) -> ModelRecommendation:
        """Recommend a model for a task.
        
        Args:
            stage: Agent stage (planner, coder, reviewer, debugger, tester)
            task_type: Type of task being performed
            risk_level: Risk level (low, medium, high)
            repo_size: Repository size (small, medium, large)
            
        Returns:
            ModelRecommendation
        """
        # Map task type to stage if needed
        if task_type and stage == "coder":
            mapped = self.TASK_TYPE_MAPPINGS.get(task_type.lower())
            if mapped:
                stage = mapped
        
        # Get requirements for stage
        requirements = self.STAGE_REQUIREMENTS.get(stage, {})
        
        # Find suitable models
        candidates = []
        
        for model_name, model_info in MODELS.items():
            score = self._score_model(
                model_name,
                model_info,
                requirements,
                risk_level,
                repo_size,
            )
            
            if score > 0:
                candidates.append((model_name, model_info, score))
        
        # Sort by score
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        if not candidates:
            # Fallback to cheapest option
            return ModelRecommendation(
                model="gpt-3.5-turbo",
                fallback_model="gpt-4o-mini",
                reasoning="No suitable model found, using fallback",
                estimated_cost=0.002,
                strengths=["fast", "cheap"],
            )
        
        primary = candidates[0]
        primary_model = primary[0]
        primary_info = primary[1]
        
        # Select fallback
        if len(candidates) > 1:
            fallback = candidates[1][0]
        else:
            fallback = self._get_fallback(primary_model)
        
        # Build reasoning
        reasoning = self._build_reasoning(
            primary_model,
            primary_info,
            requirements,
            risk_level,
        )
        
        estimated_cost = (
            primary_info["cost_per_1k_input"] +
            primary_info["cost_per_1k_output"]
        )
        
        return ModelRecommendation(
            model=primary_model,
            fallback_model=fallback,
            reasoning=reasoning,
            estimated_cost=estimated_cost,
            strengths=primary_info["strengths"],
        )
    
    def _score_model(
        self,
        model_name: str,
        model_info: dict[str, Any],
        requirements: dict[str, Any],
        risk_level: str,
        repo_size: str,
    ) -> float:
        """Score a model for fitness."""
        score = 0.0
        
        # Check required strengths
        required_strengths = requirements.get("required_strengths", [])
        model_strengths = model_info.get("strengths", [])
        
        if required_strengths:
            # At least half of required strengths must match
            matches = sum(1 for s in required_strengths if s in model_strengths)
            if matches == 0:
                return 0.0
            score += matches / len(required_strengths) * 50
        
        # Reasoning preference
        if requirements.get("preferred_reasoning"):
            if "reasoning" in model_strengths:
                score += 20
        
        # Cost tolerance
        max_cost = requirements.get("max_cost_tolerance", 0.02)
        model_cost = model_info["cost_per_1k_input"] + model_info["cost_per_1k_output"]
        
        if model_cost <= max_cost:
            score += 20 * (1 - model_cost / max_cost)
        else:
            score -= 50  # Penalize over-budget
        
        # Cheap preference
        if self.prefer_cheap:
            score -= model_cost * 500
        
        # Risk adjustment
        if risk_level == "high":
            # Prefer stronger models for high risk
            if "reasoning" in model_strengths:
                score += 10
        elif risk_level == "low":
            # Prefer cheaper models for low risk
            score -= model_cost * 200
        
        return score
    
    def _get_fallback(self, primary: str) -> str:
        """Get a fallback model."""
        fallbacks = {
            "claude-opus-4": "claude-sonnet-4",
            "claude-sonnet-4": "claude-3-5-sonnet",
            "claude-3-5-sonnet": "gpt-4o",
            "gpt-4o": "gpt-4-turbo",
            "gpt-4-turbo": "gpt-3.5-turbo",
            "o1-preview": "o1-mini",
            "o1-mini": "gpt-4o-mini",
            "gpt-4o-mini": "gpt-3.5-turbo",
        }
        return fallbacks.get(primary, "gpt-3.5-turbo")
    
    def _build_reasoning(
        self,
        model: str,
        model_info: dict[str, Any],
        requirements: dict[str, Any],
        risk_level: str,
    ) -> str:
        """Build reasoning string."""
        parts = []
        
        parts.append(f"Selected {model} for {requirements.get('required_strengths', ['general'])} tasks")
        
        if "reasoning" in model_info.get("strengths", []):
            parts.append("Strong reasoning capabilities")
        
        cost = model_info["cost_per_1k_input"] + model_info["cost_per_1k_output"]
        parts.append(f"Cost: ~${cost:.4f} per 1k tokens")
        
        if risk_level == "high":
            parts.append("Enhanced capabilities for high-risk task")
        
        return ". ".join(parts)


def recommend_model_for_stage(
    stage: str,
    task_type: str | None = None,
    risk_level: str = "medium",
) -> dict[str, Any]:
    """Recommend optimal model for agent stage.
    
    Args:
        stage: Agent stage
        task_type: Type of task
        risk_level: Risk level
        
    Returns:
        Dict with recommendation
    """
    selector = ModelSelector()
    recommendation = selector.recommend(
        stage=stage,
        task_type=task_type,
        risk_level=risk_level,
    )
    
    return recommendation.to_dict()
