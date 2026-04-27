from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repo root is importable no matter where pytest is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture()
def tmp_jobs_dir(tmp_path: Path) -> Path:
    """Isolated, auto-cleaned jobs directory per test."""
    d = tmp_path / "jobs.d"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture()
def mock_scheduler() -> MagicMock:
    """MagicMock stand-in for JobScheduler — used by watcher tests."""
    return MagicMock()
