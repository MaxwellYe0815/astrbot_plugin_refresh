from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PLUGIN_NAME = "astrbot_plugin_refresh"


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "priority_interval_seconds": 3600,
    "normal_interval_seconds": 3600,
    "normal_groups_per_interval": 1,
    "jitter_seconds": 300,
    "startup_delay_seconds": 60,
    "request_timeout_seconds": 60,
}


@dataclass(frozen=True)
class RefreshConfig:
    enabled: bool
    priority_interval_seconds: int
    normal_interval_seconds: int
    normal_groups_per_interval: int
    jitter_seconds: int
    startup_delay_seconds: int
    request_timeout_seconds: int

    @classmethod
    def from_mapping(cls, raw_config: dict[str, Any] | None) -> "RefreshConfig":
        data = dict(DEFAULT_CONFIG)
        data.update(dict(raw_config or {}))

        return cls(
            enabled=bool(data.get("enabled", True)),
            priority_interval_seconds=_positive_int(
                data.get("priority_interval_seconds"),
                DEFAULT_CONFIG["priority_interval_seconds"],
                minimum=60,
            ),
            normal_interval_seconds=_positive_int(
                data.get("normal_interval_seconds"),
                DEFAULT_CONFIG["normal_interval_seconds"],
                minimum=60,
            ),
            normal_groups_per_interval=_positive_int(
                data.get("normal_groups_per_interval"),
                DEFAULT_CONFIG["normal_groups_per_interval"],
                minimum=1,
            ),
            jitter_seconds=_positive_int(
                data.get("jitter_seconds"),
                DEFAULT_CONFIG["jitter_seconds"],
                minimum=0,
            ),
            startup_delay_seconds=_positive_int(
                data.get("startup_delay_seconds"),
                DEFAULT_CONFIG["startup_delay_seconds"],
                minimum=0,
            ),
            request_timeout_seconds=_positive_int(
                data.get("request_timeout_seconds"),
                DEFAULT_CONFIG["request_timeout_seconds"],
                minimum=5,
            ),
        )


def _positive_int(value: Any, default: int, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, parsed)
