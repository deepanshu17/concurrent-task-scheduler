from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from models import ExecutionResult
from tasks.base import TaskExecutor


class WriteFileExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        path = config.get("path")
        content = config.get("content", "")
        mode = config.get("mode", "overwrite")
        encoding = config.get("encoding", "utf-8")

        if not isinstance(path, str) or not path.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'path'",
            )

        if mode in ("write", "w", None):
            mode = "overwrite"
        if mode in ("a",):
            mode = "append"
        if mode not in ("append", "overwrite"):
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="invalid 'mode' (expected 'append' or 'overwrite')",
            )

        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            file_mode = "a" if mode == "append" else "w"
            with p.open(file_mode, encoding=encoding) as fh:
                fh.write(str(content))
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="SUCCESS",
                output=str(p),
            )
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
