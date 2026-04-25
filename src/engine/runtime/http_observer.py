"""HTTP Observer - HTTP traffic capture and analysis."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HTTPTransaction:
    """A captured HTTP request/response transaction."""
    
    id: str
    timestamp: datetime
    method: str
    path: str
    host: str
    status_code: int | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str | None = None
    duration_ms: float = 0.0
    source_ip: str | None = None
    destination_ip: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "host": self.host,
            "status_code": self.status_code,
            "request_headers": self.request_headers,
            "request_body": self.request_body,
            "response_headers": self.response_headers,
            "response_body": self.response_body[:1000] if self.response_body else None,  # Truncate for safety
            "duration_ms": self.duration_ms,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
        }


class HTTPObserver:
    """Observes and captures HTTP traffic."""
    
    def __init__(self):
        self._transactions: list[HTTPTransaction] = []
        self._lock = threading.Lock()
        self._max_transactions = 1000
        self._running = False
        self._id_counter = 0
    
    def add_transaction(self, transaction: HTTPTransaction) -> None:
        """Add a captured transaction."""
        with self._lock:
            self._transactions.append(transaction)
            
            # Trim old transactions
            if len(self._transactions) > self._max_transactions:
                self._transactions = self._transactions[-self._max_transactions:]
    
    def get_transactions(
        self,
        method: str | None = None,
        path_pattern: str | None = None,
        host: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[HTTPTransaction]:
        """Get captured transactions with optional filtering.
        
        Args:
            method: Filter by HTTP method
            path_pattern: Filter by path regex pattern
            host: Filter by host
            since: Only return transactions after this time
            limit: Maximum number to return
            
        Returns:
            List of matching transactions
        """
        with self._lock:
            results = self._transactions.copy()
        
        # Apply filters
        if method:
            results = [t for t in results if t.method.upper() == method.upper()]
        
        if path_pattern:
            pattern = re.compile(path_pattern)
            results = [t for t in results if pattern.search(t.path)]
        
        if host:
            results = [t for t in results if host.lower() in t.host.lower()]
        
        if since:
            results = [t for t in results if t.timestamp >= since]
        
        # Sort by timestamp (most recent first) and limit
        results.sort(key=lambda t: t.timestamp, reverse=True)
        return results[:limit]
    
    def clear(self) -> None:
        """Clear captured transactions."""
        with self._lock:
            self._transactions.clear()
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics of captured traffic."""
        with self._lock:
            transactions = self._transactions
        
        if not transactions:
            return {
                "total_transactions": 0,
                "methods": {},
                "status_codes": {},
                "hosts": {},
                "avg_duration_ms": 0,
            }
        
        # Count by method
        methods: dict[str, int] = {}
        for t in transactions:
            methods[t.method] = methods.get(t.method, 0) + 1
        
        # Count by status code
        status_codes: dict[str, int] = {}
        for t in transactions:
            if t.status_code:
                code_str = str(t.status_code)
                status_codes[code_str] = status_codes.get(code_str, 0) + 1
        
        # Count by host
        hosts: dict[str, int] = {}
        for t in transactions:
            hosts[t.host] = hosts.get(t.host, 0) + 1
        
        # Calculate average duration
        durations = [t.duration_ms for t in transactions if t.duration_ms > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_transactions": len(transactions),
            "methods": methods,
            "status_codes": status_codes,
            "hosts": hosts,
            "avg_duration_ms": avg_duration,
            "time_range": {
                "start": transactions[0].timestamp.isoformat() if transactions else None,
                "end": transactions[-1].timestamp.isoformat() if transactions else None,
            },
        }
    
    def _generate_id(self) -> str:
        """Generate a unique transaction ID."""
        self._id_counter += 1
        return f"txn_{int(time.time() * 1000)}_{self._id_counter}"


# Global observer instance
_observer: HTTPObserver | None = None
_observer_lock = threading.Lock()


def get_observer() -> HTTPObserver:
    """Get or create the global HTTP observer."""
    global _observer
    with _observer_lock:
        if _observer is None:
            _observer = HTTPObserver()
        return _observer


def observe_http_traffic(
    port: int | None = None,
    route: str | None = None,
    method: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Observe HTTP traffic.
    
    This function captures and analyzes HTTP traffic. For actual packet capture,
    use a tool like mitmproxy or tcpdump. This function provides tools for
    parsing and analyzing HTTP data that may be captured through other means.
    
    Args:
        port: Optional port to filter
        route: Optional route pattern to filter
        method: Optional HTTP method to filter
        limit: Maximum number of transactions to return
        
    Returns:
        Dict with transactions and summary
    """
    observer = get_observer()
    
    # Apply filters
    transactions = observer.get_transactions(
        method=method,
        path_pattern=route,
        limit=limit,
    )
    
    # Filter by port if specified
    if port:
        transactions = [t for t in transactions if _extract_port(t.host) == port]
    
    return {
        "transactions": [t.to_dict() for t in transactions],
        "count": len(transactions),
        "summary": observer.get_summary(),
    }


def _extract_port(host: str) -> int | None:
    """Extract port from host:port string."""
    if ':' in host:
        try:
            return int(host.split(':')[-1])
        except ValueError:
            return None
    return None


def parse_http_request(data: bytes) -> dict[str, Any] | None:
    """Parse raw HTTP request data.
    
    Args:
        data: Raw HTTP request bytes
        
    Returns:
        Dict with parsed request info or None if invalid
    """
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        return None
    
    # Split headers and body
    parts = text.split('\r\n\r\n')
    if not parts:
        return None
    
    headers_text = parts[0]
    body = parts[1] if len(parts) > 1 else None
    
    # Parse request line
    lines = headers_text.split('\r\n')
    if not lines:
        return None
    
    request_line = lines[0]
    match = re.match(r'(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+HTTP/(\d+\.\d+)', request_line)
    
    if not match:
        return None
    
    method, path, version = match.groups()
    
    # Parse headers
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
    
    # Extract host
    host = headers.get('Host', '')
    
    return {
        "method": method,
        "path": path,
        "version": version,
        "headers": headers,
        "body": body,
        "host": host,
    }


def parse_http_response(data: bytes) -> dict[str, Any] | None:
    """Parse raw HTTP response data.
    
    Args:
        data: Raw HTTP response bytes
        
    Returns:
        Dict with parsed response info or None if invalid
    """
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        return None
    
    # Split headers and body
    parts = text.split('\r\n\r\n')
    if not parts:
        return None
    
    headers_text = parts[0]
    body = parts[1] if len(parts) > 1 else None
    
    # Parse status line
    lines = headers_text.split('\r\n')
    if not lines:
        return None
    
    status_line = lines[0]
    match = re.match(r'HTTP/(\d+\.\d+)\s+(\d+)\s+(.*)', status_line)
    
    if not match:
        return None
    
    version, status_code, status_text = match.groups()
    
    # Parse headers
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
    
    return {
        "version": version,
        "status_code": int(status_code),
        "status_text": status_text,
        "headers": headers,
        "body": body,
    }


def record_transaction(
    method: str,
    path: str,
    host: str,
    request_headers: dict[str, str] | None = None,
    request_body: str | None = None,
    status_code: int | None = None,
    response_headers: dict[str, str] | None = None,
    response_body: str | None = None,
    duration_ms: float = 0.0,
) -> HTTPTransaction:
    """Record an HTTP transaction in the global observer.
    
    Args:
        method: HTTP method
        path: Request path
        host: Target host
        request_headers: Request headers
        request_body: Request body
        status_code: Response status code
        response_headers: Response headers
        response_body: Response body
        duration_ms: Request duration in milliseconds
        
    Returns:
        The recorded HTTPTransaction
    """
    observer = get_observer()
    
    transaction = HTTPTransaction(
        id=observer._generate_id(),
        timestamp=datetime.now(),
        method=method,
        path=path,
        host=host,
        status_code=status_code,
        request_headers=request_headers or {},
        request_body=request_body,
        response_headers=response_headers or {},
        response_body=response_body,
        duration_ms=duration_ms,
    )
    
    observer.add_transaction(transaction)
    return transaction
