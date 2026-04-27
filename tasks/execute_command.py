from __future__ import annotations

import shlex
import subprocess
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor


class ExecuteCommandExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        command = config.get("command")
        timeout_sec = config.get("timeout_sec")

        if not isinstance(command, str) or not command.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'command'",
            )

        try:
            args = shlex.split(command)
            cp = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout_sec if isinstance(timeout_sec, (int, float)) else None,
                check=False,
            )
            out = (cp.stdout or "") + (cp.stderr or "")
            status = "SUCCESS" if cp.returncode == 0 else "FAILURE"
            if not out.strip():
                out = f"exit_code={cp.returncode}"
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status=status,
                output=out,
            )
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
