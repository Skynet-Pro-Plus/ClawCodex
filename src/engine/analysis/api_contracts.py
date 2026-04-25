"""API Contract Validator - Validates API contracts against code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class APIContract:
    """Represents an API endpoint contract."""
    
    path: str
    method: str
    handler: str
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    auth_required: bool = False


@dataclass
class ContractValidationResult:
    """Result of API contract validation."""
    
    valid: bool = True
    breaking_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    endpoints_checked: int = 0
    endpoints_valid: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "breaking_changes": self.breaking_changes,
            "warnings": self.warnings,
            "endpoints_checked": self.endpoints_checked,
            "endpoints_valid": self.endpoints_valid,
        }


class APIContractValidator:
    """Validates API contracts against implementations."""
    
    def __init__(self):
        self.contracts: list[APIContract] = []
    
    def add_contract(self, path: str, method: str = "GET", handler: str = "") -> None:
        """Add an API contract to track."""
        contract = APIContract(path=path, method=method, handler=handler)
        self.contracts.append(contract)
    
    def validate_against_code(
        self,
        code_files: list[str],
    ) -> ContractValidationResult:
        """Validate contracts against actual code.
        
        Args:
            code_files: List of source files to validate against
            
        Returns:
            ContractValidationResult with any breaking changes
        """
        result = ContractValidationResult()
        result.endpoints_checked = len(self.contracts)
        
        for contract in self.contracts:
            # Check if handler exists
            handler_found = False
            
            for code_file in code_files:
                if contract.handler:
                    # Simple check - would use actual code analysis
                    try:
                        with open(code_file, 'r') as f:
                            content = f.read()
                            if contract.handler in content:
                                handler_found = True
                                break
                    except FileNotFoundError:
                        pass
            
            if not handler_found and contract.handler:
                result.breaking_changes.append({
                    "type": "missing_handler",
                    "path": contract.path,
                    "method": contract.method,
                    "handler": contract.handler,
                })
                result.valid = False
            else:
                result.endpoints_valid += 1
        
        return result
    
    def compare_snapshots(
        self,
        old_contracts: list[APIContract],
        new_contracts: list[APIContract],
    ) -> ContractValidationResult:
        """Compare two contract snapshots for breaking changes.
        
        Args:
            old_contracts: Previous contract definitions
            new_contracts: New contract definitions
            
        Returns:
            ContractValidationResult with breaking changes
        """
        result = ContractValidationResult()
        
        old_map = {f"{c.method}:{c.path}": c for c in old_contracts}
        new_map = {f"{c.method}:{c.path}": c for c in new_contracts}
        
        # Check for removed endpoints
        for key, old in old_map.items():
            if key not in new_map:
                result.breaking_changes.append({
                    "type": "removed_endpoint",
                    "path": old.path,
                    "method": old.method,
                })
                result.valid = False
        
        # Check for changed signatures
        for key, new in new_map.items():
            if key in old_map:
                old = old_map[key]
                
                # Check request schema changes
                if old.request_schema != new.request_schema:
                    result.breaking_changes.append({
                        "type": "changed_request_schema",
                        "path": new.path,
                        "method": new.method,
                        "old_schema": old.request_schema,
                        "new_schema": new.request_schema,
                    })
                
                # Check response schema changes
                if old.response_schema != new.response_schema:
                    result.breaking_changes.append({
                        "type": "changed_response_schema",
                        "path": new.path,
                        "method": new.method,
                        "old_schema": old.response_schema,
                        "new_schema": new.response_schema,
                    })
        
        # Check for new endpoints
        for key, new in new_map.items():
            if key not in old_map:
                result.warnings.append(f"New endpoint added: {new.method} {new.path}")
        
        result.endpoints_checked = len(new_contracts)
        result.endpoints_valid = len(new_contracts) - len(result.breaking_changes)
        
        return result


def validate_api_contracts(
    repo_path: str,
    openapi_spec: dict[str, Any] | None = None,
) -> ContractValidationResult:
    """Convenience function for API contract validation.
    
    Args:
        repo_path: Path to repository
        openapi_spec: Optional OpenAPI specification dict
        
    Returns:
        ContractValidationResult
    """
    validator = APIContractValidator()
    
    # Extract contracts from OpenAPI spec if provided
    if openapi_spec:
        for path, path_item in openapi_spec.get("paths", {}).items():
            for method in ["get", "post", "put", "delete", "patch"]:
                if method in path_item:
                    contract = APIContract(
                        path=path,
                        method=method.upper(),
                        request_schema=path_item[method].get("requestBody", {}),
                        response_schema=path_item[method].get("responses", {}),
                    )
                    validator.contracts.append(contract)
    
    # Would scan code files here
    # For now, return empty result
    return ContractValidationResult()
