"""Process Observer - Process inspection and health monitoring."""

from __future__ import annotations

import os
import platform
import psutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProcessInfo:
    """Information about a running process."""
    
    pid: int
    name: str
    status: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    num_threads: int = 0
    create_time: float = 0.0
    cmdline: list[str] = field(default_factory=list)
    cwd: str = ""
    username: str | None = None
    parent_pid: int | None = None
    children: list[int] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "status": self.status,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "memory_percent": self.memory_percent,
            "num_threads": self.num_threads,
            "create_time": datetime.fromtimestamp(self.create_time).isoformat() if self.create_time else None,
            "cmdline": self.cmdline,
            "cwd": self.cwd,
            "username": self.username,
            "parent_pid": self.parent_pid,
            "children": self.children,
            "uptime_seconds": time.time() - self.create_time if self.create_time else 0,
        }


@dataclass
class PortInfo:
    """Information about an open network port."""
    
    port: int
    protocol: str
    local_address: str
    remote_address: str
    status: str
    pid: int | None = None
    process_name: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "protocol": self.protocol,
            "local_address": self.local_address,
            "remote_address": self.remote_address,
            "status": self.status,
            "pid": self.pid,
            "process_name": self.process_name,
        }


@dataclass
class HealthStatus:
    """Health check result for a service."""
    
    name: str
    healthy: bool
    latency_ms: float | None = None
    message: str = ""
    checks: dict[str, bool] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "checks": self.checks,
            "timestamp": self.timestamp.isoformat(),
        }


class ProcessObserver:
    """Observes and monitors system processes."""
    
    def __init__(self):
        self._process_cache: dict[int, ProcessInfo] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 5.0  # 5 seconds
    
    def get_process(
        self,
        pid: int | str,
        refresh: bool = False,
    ) -> ProcessInfo | None:
        """Get information about a specific process.
        
        Args:
            pid: Process ID or process name
            refresh: Force cache refresh
            
        Returns:
            ProcessInfo or None if not found
        """
        # Parse PID
        try:
            pid_int = int(pid)
        except (ValueError, TypeError):
            # Assume it's a process name
            return self._find_by_name(str(pid))
        
        # Check cache
        now = time.time()
        if not refresh and pid_int in self._process_cache and (now - self._cache_time) < self._cache_ttl:
            return self._process_cache[pid_int]
        
        try:
            proc = psutil.Process(pid_int)
            info = self._build_process_info(proc)
            
            self._process_cache[pid_int] = info
            self._cache_time = now
            
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
    
    def _build_process_info(self, proc: psutil.Process) -> ProcessInfo:
        """Build ProcessInfo from psutil.Process."""
        try:
            mem_info = proc.memory_info()
            mem_percent = proc.memory_percent()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            mem_info = psutil._common.pmem(0, 0)
            mem_percent = 0.0
        
        try:
            children = [child.pid for child in proc.children(recursive=True)]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            children = []
        
        try:
            cwd = proc.cwd()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cwd = ""
        
        try:
            username = proc.username()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            username = None
        
        return ProcessInfo(
            pid=proc.pid,
            name=proc.name(),
            status=proc.status(),
            cpu_percent=proc.cpu_percent(interval=0.1),
            memory_mb=mem_info.rss / (1024 * 1024),
            memory_percent=mem_percent,
            num_threads=proc.num_threads(),
            create_time=proc.create_time(),
            cmdline=proc.cmdline(),
            cwd=cwd,
            username=username,
            parent_pid=proc.ppid() if proc.ppid() != 0 else None,
            children=children,
        )
    
    def _find_by_name(self, name: str) -> ProcessInfo | None:
        """Find first process by name."""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and name.lower() in proc.info['name'].lower():
                    return self.get_process(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def find_processes(
        self,
        name: str | None = None,
        cmdline_contains: str | None = None,
    ) -> list[ProcessInfo]:
        """Find processes matching criteria.
        
        Args:
            name: Filter by process name (substring match)
            cmdline_contains: Filter by cmdline containing string
            
        Returns:
            List of matching ProcessInfo
        """
        results = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                proc_name = proc.info.get('name', '')
                cmdline = proc.info.get('cmdline', [])
                
                # Apply filters
                if name and name.lower() not in proc_name.lower():
                    continue
                
                if cmdline_contains:
                    cmdline_str = ' '.join(cmdline)
                    if cmdline_contains.lower() not in cmdline_str.lower():
                        continue
                
                results.append(self.get_process(proc.info['pid'], refresh=True))
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return [r for r in results if r is not None]
    
    def get_system_stats(self) -> dict[str, Any]:
        """Get overall system statistics."""
        return {
            "cpu": {
                "count": psutil.cpu_count(),
                "percent": psutil.cpu_percent(interval=0.5),
                "per_cpu": psutil.cpu_percent(interval=0.5, percpu=True),
            },
            "memory": {
                "total_mb": psutil.virtual_memory().total / (1024 * 1024),
                "available_mb": psutil.virtual_memory().available / (1024 * 1024),
                "percent": psutil.virtual_memory().percent,
            },
            "disk": {
                "total_gb": psutil.disk_usage('/').total / (1024 ** 3) if platform.system() != 'Windows' else psutil.disk_usage('C:').total / (1024 ** 3),
                "free_gb": psutil.disk_usage('/').free / (1024 ** 3) if platform.system() != 'Windows' else psutil.disk_usage('C:').free / (1024 ** 3),
                "percent": psutil.disk_usage('/').percent if platform.system() != 'Windows' else psutil.disk_usage('C:').percent,
            },
            "uptime_seconds": time.time() - psutil.boot_time(),
        }


def inspect_open_ports(
    listening_only: bool = True,
    port_filter: int | list[int] | None = None,
) -> list[PortInfo]:
    """Inspect open network ports.
    
    Args:
        listening_only: Only show listening ports
        port_filter: Optional port or list of ports to filter
        
    Returns:
        List of PortInfo
    """
    ports = []
    
    # Get process name mapping
    process_names: dict[int, str] = {}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            process_names[proc.info['pid']] = proc.info['name']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Iterate connections
    for conn in psutil.net_connections(kind='inet'):
        # Filter by listening status
        if listening_only and conn.status != 'LISTEN':
            continue
        
        # Filter by port
        if port_filter is not None:
            if isinstance(port_filter, int):
                if conn.laddr.port != port_filter:
                    continue
            elif isinstance(port_filter, list):
                if conn.laddr.port not in port_filter:
                    continue
        
        # Build remote address
        remote = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
        
        ports.append(PortInfo(
            port=conn.laddr.port,
            protocol="tcp",
            local_address=f"{conn.laddr.ip}:{conn.laddr.port}",
            remote_address=remote,
            status=conn.status,
            pid=conn.pid,
            process_name=process_names.get(conn.pid),
        ))
    
    # Sort by port number
    ports.sort(key=lambda p: p.port)
    
    return ports


def watch_process(
    process_name_or_pid: int | str,
    interval: float = 1.0,
    duration: float | None = None,
    collect_stats: bool = True,
) -> dict[str, Any]:
    """Watch a process and collect health metrics.
    
    Args:
        process_name_or_pid: Process name or PID to watch
        interval: Sampling interval in seconds
        duration: Optional duration to watch (None = indefinite)
        collect_stats: Whether to collect detailed stats
        
    Returns:
        Dict with process info and collected metrics
    """
    observer = ProcessObserver()
    
    # Find process
    if isinstance(process_name_or_pid, int):
        process = observer.get_process(process_name_or_pid)
    else:
        process = observer.get_process(process_name_or_pid)
    
    if process is None:
        return {
            "error": f"Process not found: {process_name_or_pid}",
            "metrics": [],
        }
    
    # Collect samples
    samples = []
    start_time = time.time()
    
    while True:
        sample_time = time.time()
        
        # Get fresh process info
        current = observer.get_process(process.pid, refresh=True)
        
        if current is None:
            break
        
        sample = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": sample_time - start_time,
            "cpu_percent": current.cpu_percent,
            "memory_mb": current.memory_mb,
            "memory_percent": current.memory_percent,
            "num_threads": current.num_threads,
            "status": current.status,
        }
        
        samples.append(sample)
        
        # Check duration
        if duration and (sample_time - start_time) >= duration:
            break
        
        time.sleep(interval)
    
    # Calculate summary statistics
    if samples:
        cpu_values = [s["cpu_percent"] for s in samples]
        mem_values = [s["memory_mb"] for s in samples]
        
        summary = {
            "sample_count": len(samples),
            "duration_seconds": samples[-1]["elapsed_seconds"] if samples else 0,
            "cpu_avg": sum(cpu_values) / len(cpu_values),
            "cpu_max": max(cpu_values),
            "cpu_min": min(cpu_values),
            "memory_avg_mb": sum(mem_values) / len(mem_values),
            "memory_max_mb": max(mem_values),
            "memory_min_mb": min(mem_values),
            "status_changes": _count_status_changes(samples),
        }
    else:
        summary = {"error": "No samples collected"}
    
    return {
        "process": process.to_dict(),
        "summary": summary,
        "metrics": samples,
    }


def _count_status_changes(samples: list[dict]) -> int:
    """Count status changes in samples."""
    changes = 0
    last_status = None
    
    for sample in samples:
        status = sample.get("status")
        if last_status and status != last_status:
            changes += 1
        last_status = status
    
    return changes


def check_health_endpoint(
    url: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Check a health endpoint.
    
    Args:
        url: Health endpoint URL
        timeout: Request timeout in seconds
        
    Returns:
        Dict with health status
    """
    import urllib.request
    import urllib.error
    
    start = time.time()
    
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            latency_ms = (time.time() - start) * 1000
            status_code = response.status
            
            try:
                import json
                body = json.loads(response.read().decode())
            except Exception:
                body = response.read().decode()[:500]
            
            return {
                "healthy": 200 <= status_code < 300,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "response": body,
                "timestamp": datetime.now().isoformat(),
            }
    except urllib.error.HTTPError as e:
        return {
            "healthy": False,
            "status_code": e.code,
            "latency_ms": (time.time() - start) * 1000,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "latency_ms": (time.time() - start) * 1000,
            "timestamp": datetime.now().isoformat(),
        }
