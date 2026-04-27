from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path

from models import ExecutionResult
from tasks.base import TaskExecutor

_OUTPUT_LIMIT = 4096


class WriteFileExecutor(TaskExecutor):
    """Write or append text content to a file using stdlib pathlib.

    Config keys:
        path     (str, required) — destination file path
        content  (str, required) — text to write
        mode     (str, optional) — "write" (default, overwrites) or "append"

    Parent directories are created automatically if they do not exist.
    """

    def execute(self, config: dict) -> ExecutionResult:
        job_id: str = config.get("job_id", "unknown")
        path_str: str = config.get("path", "")
        content: str = config.get("content", "")
        mode: str = config.get("mode", "write")

        open_mode = "a" if mode == "append" else "w"
        action = "appended" if mode == "append" else "wrote"

        try:
            dest = Path(path_str)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open(open_mode, encoding="utf-8") as fh:
                fh.write(content)

            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="SUCCESS",
                output=f"{action} {len(content)} chars to {path_str}",
            )
        except Exception:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=traceback.format_exc()[:_OUTPUT_LIMIT],
            )
