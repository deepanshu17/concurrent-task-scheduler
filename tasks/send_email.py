from __future__ import annotations

import smtplib
import traceback
from datetime import datetime, timezone
from email.message import EmailMessage

from models import ExecutionResult
from tasks.base import TaskExecutor

_OUTPUT_LIMIT = 4096


class SendEmailExecutor(TaskExecutor):
    """Send an email via SMTP using stdlib smtplib.

    Config keys:
        smtp_host  (str,        required) — SMTP server hostname
        smtp_port  (int,        optional) — SMTP port; default 25
        from       (str,        required) — sender address
        to         (list[str],  required) — recipient addresses
        subject    (str,        optional) — email subject line
        body       (str,        optional) — plain-text email body
        username   (str,        optional) — SMTP AUTH username
        password   (str,        optional) — SMTP AUTH password
    """

    def execute(self, config: dict) -> ExecutionResult:
        job_id: str = config.get("job_id", "unknown")
        smtp_host: str = config.get("smtp_host", "localhost")
        smtp_port: int = int(config.get("smtp_port", 25))
        from_addr: str = config.get("from", "")
        to_addrs = config.get("to", [])
        subject: str = config.get("subject", "")
        body: str = config.get("body", "")
        username: str | None = config.get("username")
        password: str | None = config.get("password")

        to_str = ", ".join(to_addrs) if isinstance(to_addrs, list) else str(to_addrs)

        try:
            msg = EmailMessage()
            msg["From"] = from_addr
            msg["To"] = to_str
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="SUCCESS",
                output=f"email sent to {to_str}",
            )
        except Exception:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=traceback.format_exc()[:_OUTPUT_LIMIT],
            )
