from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor


def _sqlite_path_from_url(db_url: str) -> str | None:
    if db_url == ":memory:" or db_url == "sqlite:///:memory:":
        return ":memory:"
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    if db_url and "://" not in db_url:
        return db_url
    return None


class ExecuteSQLExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        db_url = config.get("db_url")
        query = config.get("query")
        max_rows = config.get("max_rows", 50)

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
                lowered = query.lstrip().lower()
                if lowered.startswith("select") or cur.description is not None:
                    cols = [d[0] for d in (getattr(cur, "description", None) or [])]
                    rows = None
                    if hasattr(cur, "fetchmany"):
                        rows = cur.fetchmany(
                            max_rows if isinstance(max_rows, int) and max_rows > 0 else 50
                        )
                    conn.commit()
                    return ExecutionResult(
                        job_id=job_id,
                        executed_at=datetime.now(timezone.utc),
                        status="SUCCESS",
                        output=(
                            f"rows_returned={len(rows) if rows is not None else 'unknown'} "
                            f"columns={cols} preview={rows!r}"
                        ),
                    )

                before_changes = getattr(conn, "total_changes", None)
                conn.commit()
                if isinstance(before_changes, int) and isinstance(getattr(conn, "total_changes", None), int):
                    rows_affected = conn.total_changes - before_changes
                else:
                    rows_affected = getattr(cur, "rowcount", -1)
                return ExecutionResult(
                    job_id=job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="SUCCESS",
                    output=f"rows_affected={rows_affected}",
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
