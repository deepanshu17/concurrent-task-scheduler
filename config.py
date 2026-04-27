from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    jobs_dir: Path
    log_file: Path
    log_level: str
    executor_pool_size: int
    misfire_grace_sec: int
    http_timeout_sec: int
    cmd_timeout_sec: int


def load_settings() -> Settings:
    """Load settings from environment variables with sensible defaults.

    All paths are resolved to absolute so that job file paths produced by the
    directory scanner and by watchdog are always comparable via string equality.
    """
    return Settings(
        jobs_dir=Path(os.getenv("CHRONOFLOW_JOBS_DIR", "./jobs.d")).resolve(),
        log_file=Path(os.getenv("CHRONOFLOW_LOG_FILE", "./chronoflow.log")).resolve(),
        log_level=os.getenv("CHRONOFLOW_LOG_LEVEL", "INFO"),
        executor_pool_size=_env_int("CHRONOFLOW_POOL_SIZE", 5),
        misfire_grace_sec=_env_int("CHRONOFLOW_MISFIRE_GRACE", 60),
        http_timeout_sec=_env_int("CHRONOFLOW_HTTP_TIMEOUT", 30),
        cmd_timeout_sec=_env_int("CHRONOFLOW_CMD_TIMEOUT", 60),
    )
