from __future__ import annotations

from typing import Any


def timeout_sec_from_config(config: dict[str, Any], *, default: float) -> float:
    """Return ``timeout_sec`` from task config if set and numeric, else *default*."""
    v = config.get("timeout_sec", default)
    if isinstance(v, bool):
        return float(default)
    if isinstance(v, (int, float)):
        return float(v)
    return float(default)
