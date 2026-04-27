from __future__ import annotations

import logging
import signal
import sys

from watchdog.observers import Observer

from config import load_settings
from logger.execution_logger import ExecutionLogger
from scheduler.core import JobScheduler
from scheduler.job import parse_job
from scheduler.watcher import JobFileHandler


def main() -> int:
    settings = load_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    log = logging.getLogger("chronoflow")

    # Ensure jobs directory exists; auto-create so the service starts cleanly
    # even on a fresh deployment with no pre-existing jobs.
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)

    execution_logger = ExecutionLogger(log_file=settings.log_file)
    scheduler = JobScheduler(
        execution_logger=execution_logger,
        misfire_grace_sec=settings.misfire_grace_sec,
        executor_pool_size=settings.executor_pool_size,
    )
    scheduler.start()

    # Scan and load all existing job files before the watcher goes live so we
    # don't miss anything that was dropped while the service was down.
    for job_file in sorted(settings.jobs_dir.glob("*.json")):
        for job in parse_job(job_file):
            scheduler.add_job(job)

    handler = JobFileHandler(scheduler=scheduler, jobs_dir=settings.jobs_dir)
    observer = Observer()
    observer.schedule(handler, str(settings.jobs_dir), recursive=False)
    observer.start()

    log.info("ChronoFlow started — watching %s", settings.jobs_dir)
    log.info("Execution log → %s", settings.log_file)

    def _shutdown(signum, _frame) -> None:
        log.info("Signal %s received — shutting down gracefully", signum)
        observer.stop()
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        observer.join()
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
