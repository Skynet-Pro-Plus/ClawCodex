"""Security Scanning Module - Dependency, vulnerability, and secret scanning."""

from .dependency_scan import (
    DependencyInfo,
    DependencyScanner,
    scan_dependencies,
    check_outdated_packages,
)
from .secret_detection import (
    SecretMatch,
    SecretScanner,
    scan_secrets,
    SecretPattern,
)

__all__ = [
    # Dependency scanning
    "DependencyInfo",
    "DependencyScanner",
    "scan_dependencies",
    "check_outdated_packages",
    # Secret detection
    "SecretMatch",
    "SecretScanner",
    "scan_secrets",
    "SecretPattern",
]
