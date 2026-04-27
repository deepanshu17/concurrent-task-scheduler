from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler

logger = logging.getLogger(__name__)


class JobFileHandler(FileSystemEventHandler):
    """Watchdog event handler that keeps the scheduler in sync with jobs.d/.

    Reacts only to *.json file events.  Two rapid `modified` events per save
    (common in editors like vim/PyCharm that truncate then rewrite) are handled
    safely because remove_jobs_from_file is a no-op when the job is already gone
    and add_job uses remove-then-add semantics for duplicate IDs.
    """

    def __init__(self, scheduler, jobs_dir: Path) -> None:
        super().__init__()
        self._scheduler = scheduler
        self._jobs_dir = jobs_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_json(path_str: str) -> bool:
        return path_str.endswith(".json")

    def _load_and_schedule(self, path: Path) -> None:
        from scheduler.job import parse_job

        for job in parse_job(path):
            self._scheduler.add_job(job)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_json(event.src_path):
            return
        path = Path(event.src_path)
        logger.info("Job file created: %s", path.name)
        self._load_and_schedule(path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_json(event.src_path):
            return
        path = Path(event.src_path)
        logger.info("Job file modified: %s", path.name)
        self._scheduler.remove_jobs_from_file(path)
        self._load_and_schedule(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_json(event.src_path):
            return
        path = Path(event.src_path)
        logger.info("Job file deleted: %s", path.name)
        self._scheduler.remove_jobs_from_file(path)
