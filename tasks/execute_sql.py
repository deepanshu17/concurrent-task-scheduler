from __future__ import annotations

import sqlite3
import traceback
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor

_OUTPUT_LIMIT = 4096


class ExecuteSQLExecutor(TaskExecutor):
    """Execute a SQL statement against a SQLite database using stdlib sqlite3.

    Config keys:
        db_url  (str, required) — SQLite path or sqlite:///... / sqlite://... URL
        query   (str, required) — SQL statement to execute

    Supports sqlite:///path (relative) and sqlite:////abs/path (absolute) URL
    forms as used by SQLAlchemy, as well as bare file paths.
    """

    def execute(self, config: dict) -> ExecutionResult:
        job_id: str = config.get("job_id", "unknown")
        db_url: str = config.get("db_url", "")
        query: str = config.get("query", "")

        db_path = self._resolve_db_path(db_url)

        try:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute(query)
                conn.commit()
                rows = cur.fetchall()
            finally:
                conn.close()

            if rows:
                preview = str(rows[:10])[:_OUTPUT_LIMIT]
                output = f"OK — {len(rows)} row(s) returned: {preview}"
            elif cur.rowcount >= 0:
                output = f"OK — {cur.rowcount} row(s) affected"
            else:
                output = "OK"

            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="SUCCESS",
                output=output[:_OUTPUT_LIMIT],
            )
        except Exception:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=traceback.format_exc()[:_OUTPUT_LIMIT],
            )

    @staticmethod
    def _resolve_db_path(db_url: str) -> str:
        """Strip SQLAlchemy-style sqlite:// prefixes, return a plain file path."""
        if db_url.startswith("sqlite:///"):
            return db_url[len("sqlite:///"):]
        if db_url.startswith("sqlite://"):
            return db_url[len("sqlite://"):]
        return db_url
