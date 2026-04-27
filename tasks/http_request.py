from __future__ import annotations

import json as _json
import logging
import ssl
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone

from models import ExecutionResult
from tasks.base import TaskExecutor

_logger = logging.getLogger(__name__)
_OUTPUT_LIMIT = 4096


class HttpRequestExecutor(TaskExecutor):
    """Make an HTTP request using stdlib urllib — no third-party dependencies.

    Config keys:
        method      (str,       required) — GET / POST / PUT / DELETE / PATCH
        url         (str,       required) — fully-qualified URL
        headers     (dict,      optional) — extra request headers
        body        (dict|str,  optional) — dict → JSON-encoded; str → raw bytes
        timeout     (int,       optional) — seconds; default 30
        verify_ssl  (bool,      optional) — set False only for internal endpoints
    """

    def execute(self, config: dict) -> ExecutionResult:
        job_id: str = config.get("job_id", "unknown")
        method: str = config.get("method", "GET").upper()
        url: str = config.get("url", "")
        headers: dict = dict(config.get("headers") or {})
        body = config.get("body")
        timeout: int = int(config.get("timeout", 30))
        verify_ssl: bool = bool(config.get("verify_ssl", True))

        try:
            data: bytes | None = None
            if body is not None:
                if isinstance(body, dict):
                    data = _json.dumps(body).encode("utf-8")
                    headers.setdefault("Content-Type", "application/json")
                else:
                    data = str(body).encode("utf-8")

            req = urllib.request.Request(url, data=data, headers=headers, method=method)

            ssl_ctx: ssl.SSLContext | None = None
            if not verify_ssl:
                _logger.warning("SSL verification disabled for job %r — URL: %s", job_id, url)
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
                status: int = resp.status
                body_text: str = resp.read().decode("utf-8", errors="replace")[:_OUTPUT_LIMIT]
                return ExecutionResult(
                    job_id=job_id,
                    executed_at=datetime.now(timezone.utc),
                    status="SUCCESS",
                    output=f"HTTP {status}: {body_text}",
                )

        except urllib.error.HTTPError as exc:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"HTTP {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"connection error: {exc.reason}",
            )
        except TimeoutError:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=f"timed out after {timeout}s",
            )
        except Exception:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=traceback.format_exc()[:_OUTPUT_LIMIT],
            )
