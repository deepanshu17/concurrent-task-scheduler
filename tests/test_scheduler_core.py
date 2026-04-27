from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from logger.execution_logger import ExecutionLogger
from models import ExecutionResult, Job
from scheduler.core import JobScheduler

class _DummyAPS:
    def __init__(self, *args, **kwargs) -> None:
        self.add_job = MagicMock()
        self.remove_job = MagicMock()
        self.start = MagicMock()
        self.shutdown = MagicMock()
        self.running = False


def test_add_job_schedules_and_indexes(monkeypatch, tmp_path: Path) -> None:
    import scheduler.core as core_mod

    monkeypatch.setattr(core_mod, "BackgroundScheduler", lambda *a, **k: _DummyAPS())

    # Keep trigger creation out of scope; we only assert it is called.
    import scheduler.job as job_mod

    monkeypatch.setattr(job_mod, "make_trigger", lambda _s: SimpleNamespace())

    exec_logger = ExecutionLogger(log_file=tmp_path / "x.log")
    s = JobScheduler(execution_logger=exec_logger)
    j = Job(
        job_id="job-1",
        schedule="*/5 * * * *",
        task_type="write_file",
        task_config={"path": "/tmp/x", "content": "hi"},
        source_file=tmp_path / "a.json",
    )

    s.add_job(j)
    assert s.get_job("job-1") == j
    assert str(j.source_file) in s._file_registry  # type: ignore[attr-defined]
    s._aps.add_job.assert_called_once()  # type: ignore[attr-defined]


def test_remove_job_cleans_indexes(monkeypatch, tmp_path: Path) -> None:
    import scheduler.core as core_mod

    monkeypatch.setattr(core_mod, "BackgroundScheduler", lambda *a, **k: _DummyAPS())

    import scheduler.job as job_mod

    monkeypatch.setattr(job_mod, "make_trigger", lambda _s: SimpleNamespace())

    exec_logger = ExecutionLogger(log_file=tmp_path / "x.log")
    s = JobScheduler(execution_logger=exec_logger)
    src = tmp_path / "a.json"
    j = Job(
        job_id="job-1",
        schedule="*/5 * * * *",
        task_type="write_file",
        task_config={"path": "/tmp/x", "content": "hi"},
        source_file=src,
    )
    s.add_job(j)
    s.remove_job("job-1")
    assert s.get_job("job-1") is None
    assert str(src) not in s._file_registry  # type: ignore[attr-defined]


def test_run_job_unknown_type_logs_failure(monkeypatch, tmp_path: Path) -> None:
    import scheduler.core as core_mod

    monkeypatch.setattr(core_mod, "BackgroundScheduler", lambda *a, **k: _DummyAPS())

    exec_logger = MagicMock(spec=ExecutionLogger)
    s = JobScheduler(execution_logger=exec_logger)

    j = Job(
        job_id="job-1",
        schedule="*/5 * * * *",
        task_type="nope",
        task_config={},
        source_file=tmp_path / "a.json",
    )
    res = s.run_job(j)
    assert isinstance(res, ExecutionResult)
    assert res.status == "FAILURE"
    exec_logger.log.assert_called_once()

