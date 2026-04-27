from __future__ import annotations

import json
import ssl
import urllib.request
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor
from tasks.timeout_config import timeout_sec_from_config


class HttpRequestExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))
        method = str(config.get("method", "GET")).upper()
        url = config.get("url")
        headers = config.get("headers", {}) or {}
        body = config.get("body", None)
        timeout_sec = timeout_sec_from_config(config, default=30.0)
        verify_ssl = config.get("verify_ssl", True)
        output_limit = int(config.get("output_limit", 4096))
        if output_limit < 1:
            output_limit = 4096

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
            context = None
            if isinstance(verify_ssl, bool) and not verify_ssl:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=timeout_sec, context=context) as resp:
                status_code = getattr(resp, "status", None)
                try:
                    raw = resp.read(output_limit + 1)
                except TypeError:
                    raw = resp.read()
                truncated = len(raw) > output_limit
                if truncated:
                    raw = raw[:output_limit]
                text = raw.decode("utf-8", errors="replace")
                if truncated:
                    text = text + "…(truncated)"
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
