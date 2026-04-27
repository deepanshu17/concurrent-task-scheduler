from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor


class HttpRequestExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        method = str(config.get("method", "GET")).upper()
        url = config.get("url")
        headers = config.get("headers", {}) or {}
        body = config.get("body", None)
        timeout_sec = config.get("timeout_sec", 30)

        if not isinstance(url, str) or not url.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'url'",
            )
        if not isinstance(headers, dict):
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="invalid 'headers' (expected object)",
            )

        data: bytes | None
        if body is None:
            data = None
        elif isinstance(body, (str, bytes)):
            data = body.encode("utf-8") if isinstance(body, str) else body
        else:
            data = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url=url, data=data, method=method)
        for k, v in headers.items():
            req.add_header(str(k), str(v))

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                status_code = getattr(resp, "status", None)
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                return ExecutionResult(
                    job_id=job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="SUCCESS",
                    output=f"status={status_code} body={text}",
                )
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
