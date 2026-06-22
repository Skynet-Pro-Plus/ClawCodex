"""Code generation services used by the orchestrator CODE stage."""

from .code_generator import CodeGenerationResult, ProposedChange, generate_code_changes

__all__ = ["CodeGenerationResult", "ProposedChange", "generate_code_changes"]
