"""
Core diagnostic engine for the REST API Toolkit.
Each check is a small function that takes a `requests.Response` (plus context)
and returns a CheckResult(name, passed, message, details).
"""

import socket
import ssl
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class EndpointReport:
    name: str
    url: str
    method: str
    status_code: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None
    checks: list = field(default_factory=list)  # list[CheckResult]

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        return all(c.passed for c in self.checks)


# ---------- low-level timing (DNS / connect / TLS / TTFB) ----------

def measure_connection_timing(url: str, timeout: float = 5.0) -> dict:
    """Rough breakdown of DNS, TCP connect, and TLS handshake time."""
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    timing = {"dns_ms": None, "connect_ms": None, "tls_ms": None, "error": None}

    if not host:
        timing["error"] = "Could not parse hostname from URL"
        return timing

    try:
        t0 = time.perf_counter()
        addr_info = socket.getaddrinfo(host, port)
        t1 = time.perf_counter()
        timing["dns_ms"] = round((t1 - t0) * 1000, 2)

        ip = addr_info[0][4][0]
        sock = socket.create_connection((ip, port), timeout=timeout)
        t2 = time.perf_counter()
        timing["connect_ms"] = round((t2 - t1) * 1000, 2)

        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            tls_sock = ctx.wrap_socket(sock, server_hostname=host)
            t3 = time.perf_counter()
            timing["tls_ms"] = round((t3 - t2) * 1000, 2)
            tls_sock.close()
        else:
            sock.close()
    except Exception as e:
        timing["error"] = str(e)

    return timing


def check_ssl_certificate(url: str) -> CheckResult:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return CheckResult("ssl_certificate", True, "Not an HTTPS endpoint, skipped")

    host = parsed.hostname
    port = parsed.port or 443
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
        days_left = (not_after - datetime.now(timezone.utc)).days
        if days_left < 0:
            return CheckResult(
                "ssl_certificate", False, f"Certificate EXPIRED {abs(days_left)} days ago",
                {"expires": str(not_after)}
            )
        elif days_left < 14:
            return CheckResult(
                "ssl_certificate", False, f"Certificate expires soon ({days_left} days)",
                {"expires": str(not_after)}
            )
        return CheckResult(
            "ssl_certificate", True, f"Valid, expires in {days_left} days",
            {"expires": str(not_after)}
        )
    except Exception as e:
        return CheckResult("ssl_certificate", False, f"SSL check failed: {e}")


# ---------- response-based checks ----------

def check_status_code(response: requests.Response, expected: Any) -> CheckResult:
    if expected is None:
        ok = response.status_code < 500
        return CheckResult(
            "status_code", ok,
            f"Got {response.status_code}" + ("" if ok else " (server error)")
        )
    expected_list = expected if isinstance(expected, list) else [expected]
    ok = response.status_code in expected_list
    return CheckResult(
        "status_code", ok,
        f"Expected {expected_list}, got {response.status_code}"
    )


def check_response_time(response: requests.Response, threshold_ms: float = 1000) -> CheckResult:
    elapsed_ms = response.elapsed.total_seconds() * 1000
    ok = elapsed_ms <= threshold_ms
    return CheckResult(
        "response_time", ok,
        f"{elapsed_ms:.0f}ms (threshold {threshold_ms:.0f}ms)",
        {"elapsed_ms": round(elapsed_ms, 2)}
    )


def check_json_valid(response: requests.Response) -> CheckResult:
    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type and not response.text.strip().startswith(("{", "[")):
        return CheckResult("json_valid", True, "Not a JSON response, skipped")
    try:
        response.json()
        return CheckResult("json_valid", True, "Valid JSON body")
    except json.JSONDecodeError as e:
        return CheckResult("json_valid", False, f"Invalid JSON: {e}")


def check_schema(response: requests.Response, schema: dict) -> CheckResult:
    try:
        import jsonschema
    except ImportError:
        return CheckResult("schema", True, "jsonschema not installed, skipped")
    try:
        data = response.json()
        jsonschema.validate(instance=data, schema=schema)
        return CheckResult("schema", True, "Response matches schema")
    except jsonschema.ValidationError as e:
        return CheckResult("schema", False, f"Schema mismatch: {e.message}")
    except Exception as e:
        return CheckResult("schema", False, f"Could not validate schema: {e}")


def check_rate_limit_headers(response: requests.Response) -> CheckResult:
    headers = response.headers
    rl_headers = {k: v for k, v in headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
    if response.status_code == 429:
        retry_after = headers.get("Retry-After", "unknown")
        return CheckResult(
            "rate_limit", False, f"Rate limited (429). Retry-After: {retry_after}",
            rl_headers
        )
    if rl_headers:
        return CheckResult("rate_limit", True, "Rate limit headers present", rl_headers)
    return CheckResult("rate_limit", True, "No rate limiting detected")


def check_cors_headers(response: requests.Response) -> CheckResult:
    headers = response.headers
    cors = {k: v for k, v in headers.items() if k.lower().startswith("access-control")}
    if cors:
        return CheckResult("cors", True, "CORS headers present", cors)
    return CheckResult("cors", True, "No CORS headers found (may be fine for server-to-server)")


def check_security_headers(response: requests.Response) -> CheckResult:
    headers = response.headers
    recommended = [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Content-Security-Policy",
    ]
    present = [h for h in recommended if h in headers]
    missing = [h for h in recommended if h not in headers]
    msg = f"{len(present)}/{len(recommended)} security headers present (informational)"
    if missing:
        msg += f" — missing: {', '.join(missing)}"
    return CheckResult("security_headers", True, msg, {"present": present, "missing": missing})


def check_auth_behavior(session: requests.Session, url: str, method: str, headers: dict) -> CheckResult:
    """Fire the same request without auth headers to confirm auth is actually enforced."""
    stripped = {k: v for k, v in headers.items() if k.lower() not in ("authorization", "x-api-key")}
    if stripped == headers:
        return CheckResult("auth_enforcement", True, "No auth headers used, skipped")
    try:
        resp = session.request(method, url, headers=stripped, timeout=10)
        if resp.status_code in (401, 403):
            return CheckResult(
                "auth_enforcement", True,
                f"Endpoint correctly rejects unauthenticated requests ({resp.status_code})"
            )
        return CheckResult(
            "auth_enforcement", False,
            f"Endpoint returned {resp.status_code} WITHOUT auth — possible auth bypass"
        )
    except requests.RequestException as e:
        return CheckResult("auth_enforcement", False, f"Could not test auth enforcement: {e}")
