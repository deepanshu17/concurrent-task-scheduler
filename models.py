from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Job:
    """Parsed representation of a single job definition file."""

    job_id: str
    schedule: str        # cron string OR ISO 8601 timestamp
    task_type: str       # key into TASK_REGISTRY
    task_config: dict    # passed as-is to the executor
    source_file: Path    # which .json file this job came from
    description: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable record produced by every job execution."""

    job_id: str
    executed_at: datetime
    status: Literal["SUCCESS", "FAILURE"]
    output: str          # stdout / return value / error message
