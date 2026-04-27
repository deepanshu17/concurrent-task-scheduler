from __future__ import annotations

from tasks.base import TaskExecutor
from tasks.execute_command import ExecuteCommandExecutor
from tasks.execute_sql import ExecuteSQLExecutor
from tasks.http_request import HttpRequestExecutor
from tasks.send_email import SendEmailExecutor
from tasks.write_file import WriteFileExecutor

TASK_REGISTRY: dict[str, type[TaskExecutor]] = {
    "execute_command": ExecuteCommandExecutor,
    "execute_sql": ExecuteSQLExecutor,
    "send_email": SendEmailExecutor,
    "http_request": HttpRequestExecutor,
    "write_file": WriteFileExecutor,
}
