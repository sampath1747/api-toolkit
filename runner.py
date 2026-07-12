"""Runs diagnostics across all configured endpoints."""

import requests
from .config import EndpointConfig, ToolkitConfig
from .diagnostics import (
    EndpointReport,
    check_status_code,
    check_response_time,
    check_json_valid,
    check_schema,
    check_rate_limit_headers,
    check_cors_headers,
    check_security_headers,
    check_auth_behavior,
    check_ssl_certificate,
    measure_connection_timing,
)


def run_single_endpoint(session: requests.Session, ep: EndpointConfig, timeout: float) -> EndpointReport:
    report = EndpointReport(name=ep.name, url=ep.url, method=ep.method)

    try:
        resp = session.request(
            ep.method,
            ep.url,
            headers=ep.headers,
            params=ep.params,
            json=ep.body if ep.body is not None else None,
            timeout=timeout,
        )
    except requests.exceptions.SSLError as e:
        report.error = f"SSL error: {e}"
        return report
    except requests.exceptions.ConnectionError as e:
        report.error = f"Connection error (DNS/refused/unreachable): {e}"
        return report
    except requests.exceptions.Timeout:
        report.error = f"Request timed out after {timeout}s"
        return report
    except requests.RequestException as e:
        report.error = f"Request failed: {e}"
        return report

    report.status_code = resp.status_code
    report.elapsed_ms = round(resp.elapsed.total_seconds() * 1000, 2)

    report.checks.append(check_status_code(resp, ep.expected_status))
    report.checks.append(check_response_time(resp, ep.response_time_threshold_ms))
    report.checks.append(check_json_valid(resp))
    if ep.schema:
        report.checks.append(check_schema(resp, ep.schema))
    report.checks.append(check_rate_limit_headers(resp))
    report.checks.append(check_cors_headers(resp))
    report.checks.append(check_security_headers(resp))
    report.checks.append(check_ssl_certificate(ep.url))

    if ep.check_auth_enforcement:
        report.checks.append(check_auth_behavior(session, ep.url, ep.method, ep.headers))

    if ep.repeat > 1:
        report.checks.append(_check_consistency(session, ep, timeout))

    return report


def _check_consistency(session: requests.Session, ep: EndpointConfig, timeout: float):
    from .diagnostics import CheckResult
    import hashlib

    hashes = set()
    statuses = set()
    for _ in range(ep.repeat):
        try:
            r = session.request(ep.method, ep.url, headers=ep.headers, params=ep.params, timeout=timeout)
            statuses.add(r.status_code)
            hashes.add(hashlib.sha256(r.content).hexdigest())
        except requests.RequestException:
            pass

    if len(statuses) > 1:
        return CheckResult(
            "consistency", False,
            f"Inconsistent status codes across {ep.repeat} calls: {statuses}"
        )
    if len(hashes) > 1:
        return CheckResult(
            "consistency", True,
            f"Response body varies across {ep.repeat} calls (expected for dynamic data)"
        )
    return CheckResult("consistency", True, f"Identical responses across {ep.repeat} calls")


def run_all(config: ToolkitConfig) -> list:
    session = requests.Session()
    reports = []
    for ep in config.endpoints:
        reports.append(run_single_endpoint(session, ep, config.global_timeout))
    return reports
