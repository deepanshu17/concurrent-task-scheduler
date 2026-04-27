from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from models import Job

logger = logging.getLogger(__name__)


def parse_job(path: Path) -> list[Job]:
    """Parse a JSON job-definition file into a list of Job dataclasses.

    Returns an empty list (never raises) so the caller can safely iterate
    over the result even when the file is missing, malformed, or incomplete.
    One file currently maps to one job; the list return type future-proofs
    multi-job-per-file support.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        job_id: str = data["job_id"]
        schedule: str = data["schedule"]
        description: str = data.get("description", "")
        task: dict = data["task"]
        task_type: str = task["type"]

        # task_config is everything in the task block except the discriminator key
        task_config = {k: v for k, v in task.items() if k != "type"}

        return [
            Job(
                job_id=job_id,
                schedule=schedule,
                task_type=task_type,
                task_config=task_config,
                source_file=path,
                description=description,
            )
        ]
    except (KeyError, json.JSONDecodeError, TypeError, ValueError):
        logger.exception("Failed to parse job file '%s' — skipping", path)
        return []


def make_trigger(schedule: str) -> DateTrigger | CronTrigger:
    """Produce an APScheduler trigger from a schedule string.

    Tries ISO 8601 first (one-time DateTrigger); falls back to cron syntax
    (recurring CronTrigger). Raises ValueError if neither parses — the caller
    is responsible for catching and logging that error.
    """
    try:
        run_date = datetime.fromisoformat(schedule)
        return DateTrigger(run_date=run_date)
    except ValueError:
        # APScheduler's from_crontab expects standard 5-field cron.
        # To support "every 30 seconds" style schedules, we also accept a
        # 6-field variant: second minute hour day month day_of_week.
        parts = schedule.split()
        if len(parts) == 6:
            second, minute, hour, day, month, day_of_week = parts
            return CronTrigger(
                second=second,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
        return CronTrigger.from_crontab(schedule)
