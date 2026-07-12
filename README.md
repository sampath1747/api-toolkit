# REST API Diagnostic & Troubleshooting Toolkit

A Python CLI that tests REST APIs and tells you *why* they're failing —
not just that they are. Checks status codes, latency, SSL certs, JSON
validity, schema conformance, rate-limit headers, CORS, security headers,
and auth enforcement.

## Install

```bash
pip install -r requirements.txt
```

## Usage

### Quick one-off check
```bash
python -m api_toolkit check https://api.example.com/health --expect 200
```

### Run a full suite from config
```bash
python -m api_toolkit run example_config.yaml
python -m api_toolkit run example_config.yaml --html report.html
```

Exit code is `0` if everything passes, `1` if anything fails — so it's
CI-friendly (drop it into a pipeline as a smoke-test step).

## Config file format

```yaml
global_timeout: 10

endpoints:
  - name: Get Post
    url: https://api.example.com/posts/1
    method: GET
    expected_status: 200
    response_time_threshold_ms: 1500
    headers:
      Authorization: "Bearer ${API_TOKEN}"   # pulls from env var
    schema:                                  # optional JSON Schema
      type: object
      required: [id, title]
      properties:
        id: { type: integer }
    check_auth_enforcement: true             # re-fires request w/o auth
    repeat: 3                                # consistency check
```

## What each check does

| Check | What it catches |
|---|---|
| `status_code` | Wrong/unexpected status codes |
| `response_time` | Slow endpoints past your threshold |
| `json_valid` | Malformed JSON bodies |
| `schema` | Response shape drift (breaking API changes) |
| `rate_limit` | 429s, missing/present rate-limit headers |
| `cors` | Missing CORS headers (useful for browser-consumed APIs) |
| `security_headers` | Missing HSTS/CSP/X-Frame-Options etc. |
| `ssl_certificate` | Expired or soon-to-expire certs |
| `auth_enforcement` | Endpoint that *should* require auth but doesn't |
| `consistency` | Flaky/non-deterministic responses across repeated calls |

## Project layout

```
api_toolkit/
  cli.py          # typer CLI (check / run commands)
  config.py       # YAML config loading + env var substitution
  diagnostics.py  # individual check functions
  runner.py       # orchestrates checks per endpoint
  report.py       # rich terminal output + HTML report generation
example_config.yaml
requirements.txt
```

## Extending it

Add a new check by writing a function in `diagnostics.py` that returns a
`CheckResult(name, passed, message, details)`, then call it from
`runner.run_single_endpoint`. Everything else (CLI, reporting) picks it
up automatically.
