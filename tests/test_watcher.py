from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from models import Job
from scheduler.watcher import JobFileHandler


def test_watcher_created_loads_and_schedules(tmp_path: Path, mock_scheduler, monkeypatch) -> None:
    jobs_dir = tmp_path / "jobs.d"
    jobs_dir.mkdir()
    handler = JobFileHandler(scheduler=mock_scheduler, jobs_dir=jobs_dir)

    job_file = jobs_dir / "a.json"
    job = Job(
        job_id="job-1",
        schedule="*/5 * * * *",
        task_type="write_file",
        task_config={"path": "/tmp/x", "content": "hi"},
        source_file=job_file,
    )

    def _fake_parse_job(_path: Path):
        return [job]

    import scheduler.job as job_mod

    monkeypatch.setattr(job_mod, "parse_job", _fake_parse_job)

    event = SimpleNamespace(is_directory=False, src_path=str(job_file))
    handler.on_created(event)
    mock_scheduler.add_job.assert_called_once_with(job)


def test_watcher_modified_removes_then_adds(tmp_path: Path, mock_scheduler, monkeypatch) -> None:
    jobs_dir = tmp_path / "jobs.d"
    jobs_dir.mkdir()
    handler = JobFileHandler(scheduler=mock_scheduler, jobs_dir=jobs_dir)

    job_file = jobs_dir / "a.json"
    job = Job(
        job_id="job-1",
        schedule="*/5 * * * *",
        task_type="write_file",
        task_config={"path": "/tmp/x", "content": "hi"},
        source_file=job_file,
    )

    import scheduler.job as job_mod

    monkeypatch.setattr(job_mod, "parse_job", lambda _p: [job])

    event = SimpleNamespace(is_directory=False, src_path=str(job_file))
    handler.on_modified(event)
    mock_scheduler.remove_jobs_from_file.assert_called_once_with(job_file)
    mock_scheduler.add_job.assert_called_once_with(job)


def test_watcher_deleted_removes(tmp_path: Path, mock_scheduler) -> None:
    jobs_dir = tmp_path / "jobs.d"
    jobs_dir.mkdir()
    handler = JobFileHandler(scheduler=mock_scheduler, jobs_dir=jobs_dir)

    job_file = jobs_dir / "a.json"
    event = SimpleNamespace(is_directory=False, src_path=str(job_file))
    handler.on_deleted(event)
    mock_scheduler.remove_jobs_from_file.assert_called_once_with(job_file)

