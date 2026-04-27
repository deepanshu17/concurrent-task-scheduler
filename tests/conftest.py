from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_jobs_dir(tmp_path: Path) -> Path:
    """Isolated, auto-cleaned jobs directory per test."""
    d = tmp_path / "jobs.d"
    d.mkdir()
    return d


@pytest.fixture
def mock_scheduler() -> MagicMock:
    """MagicMock stand-in for JobScheduler — used by watcher tests."""
    return MagicMock()
