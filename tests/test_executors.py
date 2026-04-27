from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tasks.execute_command import ExecuteCommandExecutor
from tasks.execute_sql import ExecuteSQLExecutor
from tasks.http_request import HttpRequestExecutor
from tasks.send_email import SendEmailExecutor
from tasks.write_file import WriteFileExecutor

def test_execute_command_success(monkeypatch) -> None:
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    import tasks.execute_command as mod

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    r = ExecuteCommandExecutor().execute({"job_id": "j1", "command": "echo hi"})
    assert r.status == "SUCCESS"
    assert "ok" in r.output


def test_execute_sql_success(monkeypatch, tmp_path: Path) -> None:
    calls = {"executed": False, "committed": False, "closed": False}

    class _Cur:
        rowcount = 1

        def execute(self, _q):
            calls["executed"] = True

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            calls["committed"] = True

        def close(self):
            calls["closed"] = True

    import tasks.execute_sql as mod

    monkeypatch.setattr(mod.sqlite3, "connect", lambda _p: _Conn())

    r = ExecuteSQLExecutor().execute(
        {"job_id": "j2", "db_url": "sqlite:///x.db", "query": "select 1"}
    )
    assert r.status == "SUCCESS"
    assert calls["executed"] and calls["committed"] and calls["closed"]


def test_send_email_success(monkeypatch) -> None:
    sent = {"count": 0}

    class _SMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send_message(self, _msg):
            sent["count"] += 1

    import tasks.send_email as mod

    monkeypatch.setattr(mod.smtplib, "SMTP", _SMTP)

    r = SendEmailExecutor().execute(
        {
            "job_id": "j3",
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "from": "a@b",
            "to": ["c@d"],
            "subject": "s",
            "body": "b",
        }
    )
    assert r.status == "SUCCESS"
    assert sent["count"] == 1


def test_http_request_success(monkeypatch) -> None:
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    import tasks.http_request as mod

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _Resp())

    r = HttpRequestExecutor().execute(
        {"job_id": "j4", "method": "GET", "url": "https://example.com"}
    )
    assert r.status == "SUCCESS"
    assert "status=200" in r.output


def test_write_file_overwrite(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    r = WriteFileExecutor().execute(
        {"job_id": "j5", "path": str(p), "content": "hello", "mode": "overwrite"}
    )
    assert r.status == "SUCCESS"
    assert p.read_text(encoding="utf-8") == "hello"

