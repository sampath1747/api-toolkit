"""
REST API Diagnostic & Troubleshooting Toolkit — CLI

Usage:
  python -m api_toolkit check https://api.example.com/health
  python -m api_toolkit run config.yaml
  python -m api_toolkit run config.yaml --html report.html
"""

import typer
import requests
from typing import Optional
from rich.console import Console

from .config import EndpointConfig, ToolkitConfig
from .runner import run_single_endpoint, run_all
from .report import print_terminal_report, generate_html_report

app = typer.Typer(help="REST API Diagnostic & Troubleshooting Toolkit")
console = Console()


@app.command()
def check(
    url: str,
    method: str = typer.Option("GET", help="HTTP method"),
    expect: Optional[int] = typer.Option(None, help="Expected status code"),
    threshold: float = typer.Option(1000, help="Response time threshold (ms)"),
    timeout: float = typer.Option(10, help="Request timeout (s)"),
):
    """Run diagnostics against a single URL."""
    ep = EndpointConfig(
        name=url,
        url=url,
        method=method.upper(),
        expected_status=expect,
        response_time_threshold_ms=threshold,
    )
    session = requests.Session()
    report = run_single_endpoint(session, ep, timeout)
    print_terminal_report([report])
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def run(
    config_path: str = typer.Argument(..., help="Path to YAML config file"),
    html: Optional[str] = typer.Option(None, help="Write an HTML report to this path"),
):
    """Run diagnostics for all endpoints defined in a config file."""
    config = ToolkitConfig.from_file(config_path)
    if not config.endpoints:
        console.print("[yellow]No endpoints found in config.[/yellow]")
        raise typer.Exit(code=1)

    reports = run_all(config)
    print_terminal_report(reports)

    if html:
        generate_html_report(reports, html)
        console.print(f"[cyan]HTML report written to {html}[/cyan]")

    if not all(r.passed for r in reports):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
