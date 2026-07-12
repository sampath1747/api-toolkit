"""Load and validate the YAML config describing endpoints to test."""

from dataclasses import dataclass, field
from typing import Any, Optional
import os
import yaml


@dataclass
class EndpointConfig:
    name: str
    url: str
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    body: Optional[Any] = None
    expected_status: Optional[Any] = None
    response_time_threshold_ms: float = 1000
    schema: Optional[dict] = None
    check_auth_enforcement: bool = False
    repeat: int = 1  # for consistency checks


@dataclass
class ToolkitConfig:
    endpoints: list  # list[EndpointConfig]
    global_timeout: float = 10.0

    @classmethod
    def from_file(cls, path: str) -> "ToolkitConfig":
        with open(path, "r") as f:
            raw = yaml.safe_load(f)

        endpoints = []
        for ep in raw.get("endpoints", []):
            # allow env var substitution for secrets, e.g. ${API_TOKEN}
            headers = {
                k: _resolve_env(v) for k, v in ep.get("headers", {}).items()
            }
            endpoints.append(
                EndpointConfig(
                    name=ep.get("name", ep["url"]),
                    url=ep["url"],
                    method=ep.get("method", "GET").upper(),
                    headers=headers,
                    params=ep.get("params", {}),
                    body=ep.get("body"),
                    expected_status=ep.get("expected_status"),
                    response_time_threshold_ms=ep.get("response_time_threshold_ms", 1000),
                    schema=ep.get("schema"),
                    check_auth_enforcement=ep.get("check_auth_enforcement", False),
                    repeat=ep.get("repeat", 1),
                )
            )

        return cls(
            endpoints=endpoints,
            global_timeout=raw.get("global_timeout", 10.0),
        )


def _resolve_env(value: str) -> str:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value
