from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor


def _sqlite_path_from_url(db_url: str) -> str | None:
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    if db_url == "sqlite:///:memory:":
        return ":memory:"
    return None


class ExecuteSQLExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        db_url = config.get("db_url")
        query = config.get("query")

        if not isinstance(db_url, str) or not db_url.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'db_url'",
            )
        if not isinstance(query, str) or not query.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'query'",
            )

        sqlite_path = _sqlite_path_from_url(db_url)
        if sqlite_path is None:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"unsupported db_url: {db_url!r}",
            )

        try:
            conn = sqlite3.connect(sqlite_path)
            try:
                cur = conn.cursor()
                cur.execute(query)
                conn.commit()
                return ExecutionResult(
                    job_id=job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="SUCCESS",
                    output=f"rows_affected={cur.rowcount}",
                )
            finally:
                conn.close()
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
