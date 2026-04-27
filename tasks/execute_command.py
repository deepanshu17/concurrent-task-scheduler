from __future__ import annotations

import shlex
import subprocess
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor
from tasks.timeout_config import timeout_sec_from_config


class ExecuteCommandExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        command = config.get("command")
        timeout_sec = timeout_sec_from_config(config, default=300.0)
        shell = bool(config.get("shell", True))

        output_limit = int(config.get("output_limit", 4096))
        if output_limit < 1:
            output_limit = 4096

        if not isinstance(command, str) or not command.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'command'",
            )

        try:
            cp = subprocess.run(
                command if shell else shlex.split(command),
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            out = (cp.stdout or "") + (cp.stderr or "")
            if len(out) > output_limit:
                out = out[:output_limit] + "\n…(truncated)"
            status = "SUCCESS" if cp.returncode == 0 else "FAILURE"
            if not out.strip():
                out = f"exit_code={cp.returncode}"
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status=status,
                output=out,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="command timed out",
            )
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
