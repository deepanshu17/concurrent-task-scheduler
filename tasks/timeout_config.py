from __future__ import annotations

from typing import Any


def timeout_sec_from_config(config: dict[str, Any], *, default: float) -> float:
    """Return a positive numeric ``timeout_sec`` from config, else *default*."""
    v = config.get("timeout_sec", default)
    if isinstance(v, bool):
        return float(default)
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    return float(default)
