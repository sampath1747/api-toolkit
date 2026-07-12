"""Terminal (rich) and HTML report generation."""

from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

# Set this to your repo URL so every generated report links back to the source.
GITHUB_REPO_URL = "https://github.com/sampath1747/api-toolkit"


def print_terminal_report(reports: list):
    total = len(reports)
    passed = sum(1 for r in reports if r.passed)

    for r in reports:
        header_style = "bold green" if r.passed else "bold red"
        status_label = "PASS" if r.passed else "FAIL"
        title = f"[{header_style}]{status_label}[/{header_style}] {r.name}  ({r.method} {r.url})"

        if r.error:
            console.print(Panel(f"[red]{r.error}[/red]", title=title, box=box.ROUNDED))
            continue

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Check")
        table.add_column("Result")
        table.add_column("Detail")

        for c in r.checks:
            mark = "[green]OK[/green]" if c.passed else "[red]FAIL[/red]"
            table.add_row(c.name, mark, c.message)

        summary = f"HTTP {r.status_code} | {r.elapsed_ms}ms"
        console.print(Panel(table, title=title, subtitle=summary, box=box.ROUNDED))

    color = "green" if passed == total else "yellow" if passed else "red"
    console.print(f"\n[bold {color}]Summary: {passed}/{total} endpoints passed all checks[/bold {color}]\n")


def generate_html_report(reports: list, output_path: str):
    rows = []
    for r in reports:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        if r.error:
            checks_html = f"<tr><td colspan='3' style='color:red'>{r.error}</td></tr>"
        else:
            row_parts = []
            for c in r.checks:
                color = "green" if c.passed else "red"
                label = "OK" if c.passed else "FAIL"
                row_parts.append(
                    f"<tr><td>{c.name}</td><td style='color:{color}'>{label}</td><td>{c.message}</td></tr>"
                )
            checks_html = "".join(row_parts)
        rows.append(f"""
        <div class="endpoint {'pass' if r.passed else 'fail'}">
          <h3>{status} — {r.name}</h3>
          <p><code>{r.method} {r.url}</code>
             {f"— HTTP {r.status_code} — {r.elapsed_ms}ms" if r.status_code else ""}</p>
          <table>
            <tr><th>Check</th><th>Result</th><th>Detail</th></tr>
            {checks_html}
          </table>
        </div>
        """)

    total = len(reports)
    passed = sum(1 for r in reports if r.passed)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>API Diagnostic Report</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 900px; margin: 40px auto; background:#0f1115; color:#e6e6e6; }}
  h1 {{ color: #fff; margin-bottom: 4px; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }}
  .topbar a {{ color: #6cc4ff; text-decoration: none; font-size: 0.95em; }}
  .topbar a:hover {{ text-decoration: underline; }}
  .timestamp {{ color: #888; font-size: 0.85em; margin-bottom: 24px; }}
  .summary {{ font-size: 1.1em; margin-bottom: 30px; }}
  .endpoint {{ border-radius: 8px; padding: 16px 20px; margin-bottom: 18px; background:#1a1d24; border-left: 5px solid #444; }}
  .endpoint.pass {{ border-left-color: #2ecc71; }}
  .endpoint.fail {{ border-left-color: #e74c3c; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #2a2d35; font-size: 0.9em; }}
  code {{ color: #9cd; }}
</style>
</head>
<body>
  <div class="topbar">
    <h1>REST API Diagnostic Report</h1>
    <a href="{GITHUB_REPO_URL}" target="_blank">View source on GitHub &rarr;</a>
  </div>
  <div class="timestamp">Last updated: {generated_at} &middot; runs automatically via GitHub Actions</div>
  <div class="summary">Passed <strong>{passed}/{total}</strong> endpoints</div>
  {"".join(rows)}
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
