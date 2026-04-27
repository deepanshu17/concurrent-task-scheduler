from __future__ import annotations

import subprocess
import traceback
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor

_OUTPUT_LIMIT = 4096


class ExecuteCommandExecutor(TaskExecutor):
    """Run a shell command via subprocess.

    Config keys:
        command  (str, required)  — shell command string to execute
        timeout  (int, optional)  — seconds before TimeoutExpired; default 60
        shell    (bool, optional) — pass command to the shell; default True
    """

    def execute(self, config: dict) -> ExecutionResult:
        job_id: str = config.get("job_id", "unknown")
        command: str = config.get("command", "")
        timeout: int = int(config.get("timeout", 300))
        shell: bool = bool(config.get("shell", True))

        try:
            proc = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode == 0:
                return ExecutionResult(
                    job_id=job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="SUCCESS",
                    output=proc.stdout[:_OUTPUT_LIMIT],
                )
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"exit {proc.returncode}: {proc.stderr[:_OUTPUT_LIMIT]}",
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"timed out after {timeout}s",
            )
        except Exception:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=traceback.format_exc()[:_OUTPUT_LIMIT],
            )
