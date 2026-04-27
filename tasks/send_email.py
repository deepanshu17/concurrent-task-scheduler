from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from models import ExecutionResult
from tasks.base import TaskExecutor
from tasks.timeout_config import timeout_sec_from_config


class SendEmailExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        job_id = str(config.get("job_id", ""))

        smtp_host = config.get("smtp_host")
        smtp_port = config.get("smtp_port")
        sender = config.get("from")
        recipients = config.get("to")
        subject = config.get("subject", "")
        body = config.get("body", "")
        timeout_sec = timeout_sec_from_config(config, default=30.0)
        username = config.get("username")
        password = config.get("password")

        if not isinstance(smtp_host, str) or not smtp_host.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'smtp_host'",
            )
        if not isinstance(smtp_port, int):
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'smtp_port'",
            )
        if not isinstance(sender, str) or not sender.strip():
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'from'",
            )
        if not isinstance(recipients, list) or not all(isinstance(x, str) for x in recipients) or not recipients:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output="missing or invalid 'to'",
            )

        try:
            msg = EmailMessage()
            msg["From"] = sender
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = str(subject)
            msg.set_content(str(body))

            with smtplib.SMTP(host=smtp_host, port=smtp_port, timeout=timeout_sec) as smtp:
                if isinstance(username, str) and username and isinstance(password, str) and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="SUCCESS",
                output=f"sent_to={len(recipients)}",
            )
        except Exception as e:
            return ExecutionResult(
                job_id=job_id,
                executed_at=datetime.now(timezone.utc),
                status="FAILURE",
                output=str(e),
            )
