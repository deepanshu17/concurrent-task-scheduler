from __future__ import annotations

import atexit
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from models import ExecutionResult, Job

if TYPE_CHECKING:
    from logger.execution_logger import ExecutionLogger

logger = logging.getLogger(__name__)


class JobScheduler:
    """Thin wrapper around APScheduler's BackgroundScheduler.

    Owns two secondary indexes so the watcher can resolve jobs by source file:
      _job_registry  : job_id  → Job
      _file_registry : str(path) → [job_id, ...]
    """

    def __init__(
        self,
        *,
        execution_logger: ExecutionLogger,
        misfire_grace_sec: int = 60,
        executor_pool_size: int = 5,
    ) -> None:
        executors = {"default": APSThreadPoolExecutor(executor_pool_size)}
        job_defaults = {"misfire_grace_time": misfire_grace_sec}
        self._aps = BackgroundScheduler(executors=executors, job_defaults=job_defaults)
        self._execution_logger = execution_logger
        self._job_registry: dict[str, Job] = {}
        self._file_registry: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._aps.start()
        atexit.register(self.shutdown)
        logger.info("JobScheduler started")

    def shutdown(self) -> None:
        if self._aps.running:
            self._aps.shutdown(wait=True)
            logger.info("JobScheduler shut down")

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(self, job: Job) -> None:
        """Schedule a job, replacing any existing job with the same ID."""
        if job.job_id in self._job_registry:
            self.remove_job(job.job_id)

        from scheduler.job import make_trigger

        try:
            trigger = make_trigger(job.schedule)
        except ValueError:
            logger.error(
                "Invalid schedule string for job %r: %r — skipping",
                job.job_id,
                job.schedule,
            )
            return

        self._aps.add_job(
            func=self.run_job,
            trigger=trigger,
            args=[job],
            id=job.job_id,
            name=job.description or job.job_id,
            replace_existing=True,
        )
        self._job_registry[job.job_id] = job
        self._file_registry.setdefault(str(job.source_file), []).append(job.job_id)

        logger.info(
            "Scheduled job %r  schedule=%r  type=%s",
            job.job_id,
            job.schedule,
            job.task_type,
        )

    def remove_job(self, job_id: str) -> None:
        """Remove a job from APScheduler and both registries (no-op if absent)."""
        try:
            self._aps.remove_job(job_id)
        except JobLookupError:
            pass  # already gone or never registered in APS

        job = self._job_registry.pop(job_id, None)
        if job is not None:
            file_key = str(job.source_file)
            ids = self._file_registry.get(file_key, [])
            if job_id in ids:
                ids.remove(job_id)
            if not ids:
                self._file_registry.pop(file_key, None)
            logger.info("Removed job %r", job_id)

    def remove_jobs_from_file(self, path: Path) -> None:
        """Remove every job that was loaded from *path*."""
        file_key = str(path)
        for job_id in list(self._file_registry.pop(file_key, [])):
            # Call remove_job but skip the file_registry cleanup — already popped above.
            try:
                self._aps.remove_job(job_id)
            except JobLookupError:
                pass
            self._job_registry.pop(job_id, None)
            logger.info("Removed job %r (file deleted/modified)", job_id)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_job(self, job: Job) -> ExecutionResult:
        """Resolve executor, run the job, log the result.

        This method is the APScheduler callback — it must never raise.
        All exceptions are caught and surfaced as FAILURE ExecutionResults.
        """
        from tasks.registry import TASK_REGISTRY

        # Inject job_id into a copy of task_config so executors can include it
        # in the ExecutionResult without needing a reference to the Job object.
        config = {**job.task_config, "job_id": job.job_id}

        executor_cls = TASK_REGISTRY.get(job.task_type)
        if executor_cls is None:
            result = ExecutionResult(
                job_id=job.job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"unknown task type: {job.task_type!r}",
            )
        else:
            try:
                result = executor_cls().execute(config)
            except Exception:
                result = ExecutionResult(
                    job_id=job.job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="FAILURE",
                    output=traceback.format_exc(),
                )

        self._execution_logger.log(result)
        return result

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> Job | None:
        return self._job_registry.get(job_id)

    @property
    def running(self) -> bool:
        return self._aps.running
