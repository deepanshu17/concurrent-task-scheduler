from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from logger.execution_logger import ExecutionLogger
from models import ExecutionResult

def test_execution_logger_writes_one_json_line(tmp_path: Path) -> None:
    log_file = tmp_path / "chronoflow.log"
    logger = ExecutionLogger(log_file=log_file)

    r = ExecutionResult(
        job_id="job-1",
        executed_at=datetime(2030, 1, 1, 0, 0, 0),
        status="SUCCESS",
        output="hello",
    )
    logger.log(r)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["job_id"] == "job-1"
    assert obj["status"] == "SUCCESS"
    assert obj["output"] == "hello"
    assert obj["executed_at"].startswith("2030-01-01T00:00:00")


def test_execution_logger_tz_aware_keeps_isoformat(tmp_path: Path) -> None:
    log_file = tmp_path / "chronoflow.log"
    logger = ExecutionLogger(log_file=log_file)

    r = ExecutionResult(
        job_id="job-2",
        executed_at=datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        status="FAILURE",
        output="oops",
    )
    logger.log(r)

    obj = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert obj["executed_at"].endswith("+00:00")

