from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scheduler.job import make_trigger, parse_job

def test_parse_job_valid(tmp_path: Path) -> None:
    p = tmp_path / "job.json"
    p.write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "description": "hello",
                "schedule": "*/5 * * * *",
                "task": {"type": "write_file", "path": "/tmp/x", "content": "hi"},
            }
        ),
        encoding="utf-8",
    )

    jobs = parse_job(p)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.job_id == "job-1"
    assert j.description == "hello"
    assert j.schedule == "*/5 * * * *"
    assert j.task_type == "write_file"
    assert j.task_config == {"path": "/tmp/x", "content": "hi"}
    assert j.source_file == p


def test_parse_job_invalid_returns_empty_list(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert parse_job(p) == []


def test_make_trigger_iso8601_date_trigger() -> None:
    t = make_trigger("2030-01-02T03:04:05")
    assert t.__class__.__name__ == "DateTrigger"


@pytest.mark.parametrize(
    "cron",
    [
        "*/5 * * * *",  # 5-field
        "*/10 */2 * * * *",  # 6-field with seconds
    ],
)
def test_make_trigger_cron_triggers(cron: str) -> None:
    t = make_trigger(cron)
    assert t.__class__.__name__ == "CronTrigger"

