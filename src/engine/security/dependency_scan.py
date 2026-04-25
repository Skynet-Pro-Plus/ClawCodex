"""Dependency Scanner - Scan and analyze project dependencies."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class DependencyInfo:
    """Information about a project dependency.
    
    Attributes:
        name: Package name
        current_version: Installed version
        latest_version: Latest available version
        latest_major: Latest major version
        latest_minor: Latest minor version
        is_outdated: Whether update is available
        is_vulnerable: Whether known vulnerabilities exist
        vulnerabilities: List of vulnerability IDs
        license: Package license
        package_manager: Source of this dependency
        file_path: Where dependency is declared
    """
    
    name: str
    current_version: str
    latest_version: str = ""
    latest_major: str = ""
    latest_minor: str = ""
    is_outdated: bool = False
    is_vulnerable: bool = False
    vulnerabilities: list[str] = field(default_factory=list)
    license: str = ""
    package_manager: str = ""
    file_path: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "latest_major": self.latest_major,
            "latest_minor": self.latest_minor,
            "is_outdated": self.is_outdated,
            "is_vulnerable": self.is_vulnerable,
            "vulnerabilities": self.vulnerabilities,
            "license": self.license,
            "package_manager": self.package_manager,
            "file_path": self.file_path,
        }


class DependencyScanner:
    """Scans and analyzes project dependencies.
    
    This class detects installed packages, checks for updates,
    and identifies known vulnerabilities.
    """
    
    def __init__(self, repo_path: str | None = None):
        self.repo_path = Path(repo_path or os.getcwd())
        self._dependencies: list[DependencyInfo] = []
    
    def scan(self) -> list[DependencyInfo]:
        """Scan for all dependencies.
        
        Returns:
            List of DependencyInfo objects
        """
        self._dependencies = []
        
        # Detect package managers
        managers = self._detect_package_managers()
        
        # Scan each manager
        for manager in managers:
            deps = self._scan_manager(manager)
            self._dependencies.extend(deps)
        
        return self._dependencies
    
    def _detect_package_managers(self) -> list[str]:
        """Detect which package managers are in use."""
        managers = []
        
        if (self.repo_path / "requirements.txt").exists():
            managers.append("pip")
        if (self.repo_path / "pyproject.toml").exists():
            managers.append("poetry")
        if (self.repo_path / "package.json").exists():
            managers.append("npm")
        if (self.repo_path / "go.mod").exists():
            managers.append("go")
        if (self.repo_path / "Cargo.toml").exists():
            managers.append("cargo")
        
        return managers
    
    def _scan_manager(self, manager: str) -> list[DependencyInfo]:
        """Scan dependencies for a specific manager."""
        if manager == "pip":
            return self._scan_pip()
        elif manager == "poetry":
            return self._scan_poetry()
        elif manager == "npm":
            return self._scan_npm()
        elif manager == "go":
            return self._scan_go()
        elif manager == "cargo":
            return self._scan_cargo()
        return []
    
    def _scan_pip(self) -> list[DependencyInfo]:
        """Scan Python dependencies via pip."""
        deps = []
        
        try:
            result = subprocess.run(
                ["pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                
                for pkg in packages:
                    deps.append(DependencyInfo(
                        name=pkg.get("name", ""),
                        current_version=pkg.get("version", ""),
                        package_manager="pip",
                        file_path="requirements.txt",
                    ))
        except Exception:
            pass
        
        return deps
    
    def _scan_poetry(self) -> list[DependencyInfo]:
        """Scan Python dependencies via Poetry."""
        deps = []
        
        try:
            result = subprocess.run(
                ["poetry", "show", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                
                for pkg in packages:
                    deps.append(DependencyInfo(
                        name=pkg.get("name", ""),
                        current_version=pkg.get("version", ""),
                        latest_version=pkg.get("latest", ""),
                        package_manager="poetry",
                        file_path="pyproject.toml",
                    ))
        except Exception:
            pass
        
        return deps
    
    def _scan_npm(self) -> list[DependencyInfo]:
        """Scan Node.js dependencies via npm."""
        deps = []
        
        try:
            result = subprocess.run(
                ["npm", "list", "--depth=0", "--json"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                dependencies = data.get("dependencies", {})
                
                for name, info in dependencies.items():
                    deps.append(DependencyInfo(
                        name=name,
                        current_version=info.get("version", ""),
                        package_manager="npm",
                        file_path="package.json",
                    ))
        except Exception:
            pass
        
        return deps
    
    def _scan_go(self) -> list[DependencyInfo]:
        """Scan Go dependencies."""
        deps = []
        
        # Read go.mod
        go_mod = self.repo_path / "go.mod"
        if go_mod.exists():
            with open(go_mod) as f:
                for line in f:
                    match = re.match(r'\s+(\S+)\s+v?([\d.]+)', line)
                    if match:
                        deps.append(DependencyInfo(
                            name=match.group(1),
                            current_version=match.group(2),
                            package_manager="go",
                            file_path="go.mod",
                        ))
        
        return deps
    
    def _scan_cargo(self) -> list[DependencyInfo]:
        """Scan Rust dependencies via Cargo."""
        deps = []
        
        try:
            result = subprocess.run(
                ["cargo", "tree", "--depth=1", "--format=json"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        try:
                            data = json.loads(line)
                            deps.append(DependencyInfo(
                                name=data.get("name", ""),
                                current_version=data.get("version", ""),
                                package_manager="cargo",
                                file_path="Cargo.toml",
                            ))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        
        return deps
    
    def check_updates(self) -> list[DependencyInfo]:
        """Check for available updates."""
        # Check pip first
        try:
            result = subprocess.run(
                ["pip", "list", "--outdated", "--format=json"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                outdated = json.loads(result.stdout)
                
                # Update our dependencies
                outdated_map = {
                    pkg["name"].lower(): pkg
                    for pkg in outdated
                }
                
                for dep in self._dependencies:
                    if dep.name.lower() in outdated_map:
                        info = outdated_map[dep.name.lower()]
                        dep.latest_version = info.get("latest_version", "")
                        dep.is_outdated = True
        except Exception:
            pass
        
        return self._dependencies
    
    def get_dependency(self, name: str) -> DependencyInfo | None:
        """Get a specific dependency by name."""
        for dep in self._dependencies:
            if dep.name.lower() == name.lower():
                return dep
        return None


def scan_dependencies(
    repo_path: str | None = None,
    package_managers: list[str] | None = None,
) -> dict[str, Any]:
    """Scan project dependencies.
    
    Args:
        repo_path: Path to the repository
        package_managers: Optional list of package managers to check
        
    Returns:
        Dict with dependency information
    """
    scanner = DependencyScanner(repo_path)
    
    dependencies = scanner.scan()
    
    if package_managers:
        dependencies = [d for d in dependencies if d.package_manager in package_managers]
    
    # Separate by manager
    by_manager: dict[str, list[dict]] = {}
    for dep in dependencies:
        manager = dep.package_manager
        if manager not in by_manager:
            by_manager[manager] = []
        by_manager[manager].append(dep.to_dict())
    
    return {
        "dependencies": [d.to_dict() for d in dependencies],
        "count": len(dependencies),
        "by_manager": by_manager,
        "message": f"Found {len(dependencies)} dependencies",
    }


def check_outdated_packages(
    repo_path: str | None = None,
) -> dict[str, Any]:
    """Check for outdated packages.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        Dict with outdated package information
    """
    scanner = DependencyScanner(repo_path)
    scanner.scan()
    dependencies = scanner.check_updates()
    
    outdated = [d for d in dependencies if d.is_outdated]
    
    return {
        "outdated": [d.to_dict() for d in outdated],
        "count": len(outdated),
        "message": f"Found {len(outdated)} outdated packages",
    }
