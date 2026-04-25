"""Secret Detection - Scan for API keys, tokens, and sensitive data."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SecretPattern:
    """A pattern for detecting secrets.
    
    Attributes:
        name: Pattern name
        pattern: Regex pattern
        entropy_threshold: Minimum entropy for high-entropy secrets
        severity: Critical, high, medium, low
        description: What this pattern detects
    """
    
    name: str
    pattern: str
    entropy_threshold: float = 0.0
    severity: str = "high"
    description: str = ""


@dataclass
class SecretMatch:
    """A detected secret match.
    
    Attributes:
        pattern_name: Name of the pattern that matched
        file_path: File where secret was found
        line_number: Line number
        match_content: The matched content (redacted)
        severity: Match severity
        context: Surrounding context
    """
    
    pattern_name: str
    file_path: str
    line_number: int
    match_content: str
    severity: str
    context: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_name": self.pattern_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "match_content": self.match_content,
            "severity": self.severity,
            "context": self.context,
        }


# Common secret patterns
DEFAULT_PATTERNS = [
    # AWS
    SecretPattern(
        name="AWS Access Key",
        pattern=r'AKIA[0-9A-Z]{16}',
        severity="critical",
        description="AWS Access Key ID",
    ),
    SecretPattern(
        name="AWS Secret Key",
        pattern=r'aws_secret_access_key\s*[=:]\s*["\']?[A-Za-z0-9/+=]{40}["\']?',
        severity="critical",
        description="AWS Secret Access Key",
    ),
    # GitHub
    SecretPattern(
        name="GitHub Token",
        pattern=r'ghp_[A-Za-z0-9]{36}',
        severity="critical",
        description="GitHub Personal Access Token",
    ),
    SecretPattern(
        name="GitHub OAuth",
        pattern=r'gho_[A-Za-z0-9]{36}',
        severity="critical",
        description="GitHub OAuth Token",
    ),
    # Generic API Keys
    SecretPattern(
        name="Generic API Key",
        pattern=r'api[_-]?key\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}["\']?',
        severity="high",
        description="Generic API Key",
    ),
    SecretPattern(
        name="Generic Secret",
        pattern=r'secret[_-]?key\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}["\']?',
        severity="high",
        description="Generic Secret Key",
    ),
    # Database
    SecretPattern(
        name="Database Connection String",
        pattern=r'(mysql|postgres|postgresql|mongodb)://[^\s]+',
        severity="critical",
        description="Database Connection String",
    ),
    SecretPattern(
        name="Database Password",
        pattern=r'(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}["\']?',
        severity="high",
        description="Database Password",
    ),
    # JWT
    SecretPattern(
        name="JWT Token",
        pattern=r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*',
        severity="high",
        description="JSON Web Token",
    ),
    # Private Keys
    SecretPattern(
        name="RSA Private Key",
        pattern=r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
        severity="critical",
        description="Private Key",
    ),
    SecretPattern(
        name="SSH Private Key",
        pattern=r'-----BEGIN OPENSSH PRIVATE KEY-----',
        severity="critical",
        description="SSH Private Key",
    ),
    # Slack
    SecretPattern(
        name="Slack Token",
        pattern=r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]+',
        severity="critical",
        description="Slack Token",
    ),
    # Stripe
    SecretPattern(
        name="Stripe API Key",
        pattern=r'sk_live_[A-Za-z0-9]{24}',
        severity="critical",
        description="Stripe Live API Key",
    ),
    SecretPattern(
        name="Stripe Test Key",
        pattern=r'sk_test_[A-Za-z0-9]{24}',
        severity="high",
        description="Stripe Test API Key",
    ),
    # Generic Bearer Token
    SecretPattern(
        name="Bearer Token",
        pattern=r'Bearer\s+[A-Za-z0-9_\-\.]+',
        severity="medium",
        description="Bearer Authorization Token",
    ),
    # Environment variables (common secrets)
    SecretPattern(
        name="Env Secret Assignment",
        pattern=r'(SECRET|PASSWORD|PASS|TOKEN|KEY|API)[_A-Z0-9]*\s*=\s*["\']?[A-Za-z0-9_\-]{20,}["\']?',
        severity="medium",
        description="Environment Variable with Secret-like Name",
    ),
]


class SecretScanner:
    """Scans files for secrets and sensitive data.
    
    This class provides pattern-based detection of API keys,
    tokens, passwords, and other sensitive information.
    """
    
    def __init__(
        self,
        patterns: list[SecretPattern] | None = None,
        exclude_paths: list[str] | None = None,
    ):
        self.patterns = patterns or DEFAULT_PATTERNS
        self.exclude_paths = exclude_paths or [
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
        ]
        
        # Compile regex patterns
        self._compiled = [
            (p, re.compile(p.pattern)) for p in self.patterns
        ]
    
    def scan_file(self, path: str) -> list[SecretMatch]:
        """Scan a single file for secrets.
        
        Args:
            path: Path to the file
            
        Returns:
            List of SecretMatch objects
        """
        matches = []
        
        # Check exclusions
        if any(excl in path for excl in self.exclude_paths):
            return matches
        
        if not os.path.isfile(path):
            return matches
        
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    line_matches = self._scan_line(line, path, line_num)
                    matches.extend(line_matches)
        except (IOError, OSError):
            pass
        
        return matches
    
    def _scan_line(self, line: str, path: str, line_num: int) -> list[SecretMatch]:
        """Scan a single line for secrets."""
        matches = []
        
        for pattern, regex in self._compiled:
            for match in regex.finditer(line):
                # Redact the actual secret
                redacted = self._redact_match(match.group(), pattern.name)
                
                matches.append(SecretMatch(
                    pattern_name=pattern.name,
                    file_path=path,
                    line_number=line_num,
                    match_content=redacted,
                    severity=pattern.severity,
                    context=line.strip()[:200],
                ))
        
        return matches
    
    def _redact_match(self, match: str, pattern_name: str) -> str:
        """Redact a matched secret."""
        if len(match) <= 8:
            return "***REDACTED***"
        
        # Show first 4 and last 4 characters
        return f"{match[:4]}...{match[-4:]}"
    
    def scan_directory(
        self,
        path: str,
        extensions: list[str] | None = None,
        max_file_size: int = 1024 * 1024,  # 1MB
    ) -> list[SecretMatch]:
        """Scan a directory for secrets.
        
        Args:
            path: Directory path to scan
            extensions: File extensions to scan (default: common code files)
            max_file_size: Maximum file size to scan
            
        Returns:
            List of SecretMatch objects
        """
        if extensions is None:
            extensions = [
                ".py", ".js", ".ts", ".jsx", ".tsx",
                ".env", ".json", ".yaml", ".yml",
                ".txt", ".sh", ".bash", ".zsh",
                ".conf", ".config", ".properties",
                ".java", ".go", ".rs", ".rb",
                ".php", ".cs", ".cpp", ".c",
            ]
        
        matches = []
        base_path = Path(path)
        
        for ext in extensions:
            for file_path in base_path.rglob(f"*{ext}"):
                # Check exclusions
                if any(excl in str(file_path) for excl in self.exclude_paths):
                    continue
                
                # Check file size
                try:
                    if file_path.stat().st_size > max_file_size:
                        continue
                except OSError:
                    continue
                
                file_matches = self.scan_file(str(file_path))
                matches.extend(file_matches)
        
        return matches


def scan_secrets(
    path: str | None = None,
    extensions: list[str] | None = None,
) -> dict[str, Any]:
    """Scan for secrets in a directory.
    
    Args:
        path: Directory to scan (default: current directory)
        extensions: File extensions to scan
        
    Returns:
        Dict with scan results
    """
    import os
    
    path = path or os.getcwd()
    
    scanner = SecretScanner()
    matches = scanner.scan_directory(path, extensions)
    
    # Group by severity
    by_severity: dict[str, list[dict]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }
    
    for match in matches:
        by_severity[match.severity].append(match.to_dict())
    
    # Group by file
    by_file: dict[str, list[dict]] = {}
    for match in matches:
        if match.file_path not in by_file:
            by_file[match.file_path] = []
        by_file[match.file_path].append(match.to_dict())
    
    return {
        "matches": [m.to_dict() for m in matches],
        "count": len(matches),
        "by_severity": by_severity,
        "by_file": by_file,
        "message": f"Found {len(matches)} secrets",
    }
