from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from models import ExecutionResult

_stdlib_log = logging.getLogger(__name__)
_OUTPUT_LIMIT = 4096


class ExecutionLogger:
    """Writes every ExecutionResult to an NDJSON (newline-delimited JSON) file.

    Each call to log() produces exactly one JSON object on its own line:
        {"job_id": "...", "executed_at": "...Z", "status": "SUCCESS", "output": "..."}

    Thread-safety: a module-level lock serialises the open/write/close sequence.
    File handles are not kept open between writes so that log rotation tools
    (logrotate, etc.) can safely move or truncate the file at any time.
    """

    def __init__(self, log_file: Path) -> None:
        self._log_file = log_file
        self._lock = threading.Lock()

    def log(self, result: ExecutionResult) -> None:
        executed_at = result.executed_at
        if executed_at.tzinfo is not None:
            ts = executed_at.isoformat()
        else:
            ts = executed_at.isoformat() + "Z"

        record = {
            "job_id": result.job_id,
            "executed_at": ts,
            "status": result.status,
            "output": result.output[:_OUTPUT_LIMIT],
        }
        line = json.dumps(record, ensure_ascii=False)

        with self._lock:
            with self._log_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        if result.status == "SUCCESS":
            _stdlib_log.info("[SUCCESS] %s — %s", result.job_id, result.output[:200])
        else:
            _stdlib_log.error("[FAILURE] %s — %s", result.job_id, result.output[:200])
