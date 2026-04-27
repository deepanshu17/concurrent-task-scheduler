# ChronoFlow — Running Instructions

---

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.10+ | 3.11+ recommended; tested on 3.11.15 |
| pip | any recent | comes with Python |
| OS | macOS / Linux / WSL | Windows native untested (watchdog works, but paths may differ) |

---

## 1. Clone / enter the project directory

```bash
cd /path/to/assignment
```

---

## 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows PowerShell
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs four packages — everything else (`subprocess`, `sqlite3`, `smtplib`,
`urllib`, `pathlib`, `logging`) is Python stdlib:

| Package | Version | Purpose |
|---|---|---|
| `apscheduler` | 3.10.4 | Cron + one-time trigger engine |
| `watchdog` | 4.0.1 | Cross-platform file-system events |
| `pytest` | 8.2.0 | Test runner |
| `pytest-mock` | 3.14.0 | Mock helpers for tests |

---

## 4. Run the scheduler

```bash
python main.py
```

On startup the service will:

1. Create `./jobs.d/` if it does not exist
2. Load and schedule every `*.json` file already in `jobs.d/`
3. Start a watchdog observer on `jobs.d/` for live changes
4. Block and log to stdout + `./chronoflow.log`

Sample console output:

```
2026-04-27T12:00:00 INFO     chronoflow — ChronoFlow started — watching /path/to/jobs.d
2026-04-27T12:00:00 INFO     chronoflow — Execution log → /path/to/chronoflow.log
2026-04-27T12:00:00 INFO     scheduler.core — Scheduled job 'sample-command'  schedule='* * * * *'  type=execute_command
```

Stop with **Ctrl+C** or `kill -SIGTERM <pid>` — both trigger a graceful shutdown.

---

## 5. Drop a job file and watch it get picked up live

While the scheduler is running, copy or create a new JSON file inside `jobs.d/`:

```bash
cp jobs.d/sample-command.json jobs.d/my-job.json
# or edit my-job.json to customise job_id / schedule / command
```

The watcher detects the new file instantly and schedules the job — **no restart needed**.
Editing an existing file reschedules the job; deleting it removes the job entirely.

---

## 6. Read the execution log

Every job execution appends one JSON line to `chronoflow.log`:

```bash
tail -f chronoflow.log
```

Example lines:

```json
{"job_id": "sample-command", "executed_at": "2026-04-27T12:01:00.123456+00:00", "status": "SUCCESS", "output": "hello\n"}
{"job_id": "sample-command", "executed_at": "2026-04-27T12:02:00.456789+00:00", "status": "FAILURE", "output": "exit 1: command not found"}
```

---

## 7. Run the test suite

```bash
pytest tests/ -v
```

Run a specific file:

```bash
pytest tests/test_job_parser.py -v
pytest tests/test_executors.py -v
```

Compact output (good for a quick check):

```bash
pytest tests/ --tb=short -q
```

---

## 8. Configuration via environment variables

Every setting has a sensible default; override any of them without touching code:

| Variable | Default | Description |
|---|---|---|
| `CHRONOFLOW_JOBS_DIR` | `./jobs.d` | Directory to watch for job JSON files |
| `CHRONOFLOW_LOG_FILE` | `./chronoflow.log` | Execution log file path (NDJSON format) |
| `CHRONOFLOW_LOG_LEVEL` | `INFO` | stdlib log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CHRONOFLOW_POOL_SIZE` | `5` | Max concurrent job threads (APScheduler pool) |
| `CHRONOFLOW_MISFIRE_GRACE` | `60` | Seconds a job can fire late and still run |
| `CHRONOFLOW_HTTP_TIMEOUT` | `30` | Default timeout (s) for `http_request` jobs |
| `CHRONOFLOW_CMD_TIMEOUT` | `60` | Default timeout (s) for `execute_command` jobs |

Example — run with a custom jobs directory and debug logging:

```bash
CHRONOFLOW_JOBS_DIR=/etc/chronoflow/jobs.d \
CHRONOFLOW_LOG_LEVEL=DEBUG \
python main.py
```

---

## 9. Job definition reference

Place any `.json` file inside `jobs.d/` with this structure:

```jsonc
{
  "job_id": "unique-string",        // required, must be unique across all files
  "description": "Human label",     // optional
  "schedule": "<cron | ISO 8601>",  // required
  "task": {
    "type": "<task_type>",          // required — see table below
    // ... task-specific fields
  }
}
```

### Schedule formats

| Format | Example | Behaviour |
|---|---|---|
| Cron string | `*/5 * * * *` | Recurring — every 5 minutes |
| Cron string | `0 2 * * *` | Recurring — daily at 02:00 UTC |
| ISO 8601 | `2026-10-01T09:00:00+05:30` | One-time — fires once at that timestamp |

### Timeouts in task JSON

Use **`timeout_sec`** (number of seconds) when a task supports it (`execute_command`, `http_request`, `send_email`). If omitted, each executor uses its built-in default.

### Supported task types

**`execute_command`** — run a shell command

```json
{
  "type": "execute_command",
  "command": "echo hello",
  "timeout_sec": 60,
  "shell": true
}
```

**`http_request`** — make an HTTP request

```json
{
  "type": "http_request",
  "method": "POST",
  "url": "https://hooks.example.com/notify",
  "headers": { "X-Source": "chronoflow" },
  "body": { "status": "alive" },
  "timeout_sec": 30,
  "verify_ssl": true
}
```

**`execute_sql`** — run a SQL statement on a SQLite database

```json
{
  "type": "execute_sql",
  "db_url": "sqlite:///app.db",
  "query": "DELETE FROM logs WHERE created_at < date('now','-30 days')"
}
```

**`send_email`** — send an email via SMTP

```json
{
  "type": "send_email",
  "smtp_host": "localhost",
  "smtp_port": 1025,
  "from": "scheduler@local",
  "to": ["ops@local"],
  "subject": "Scheduled report",
  "body": "See attached.",
  "timeout_sec": 30,
  "username": "optional",
  "password": "optional"
}
```

**`write_file`** — write or append text to a file

```json
{
  "type": "write_file",
  "path": "/var/log/heartbeat.log",
  "content": "alive\n",
  "mode": "append"
}
```

---

## 10. Project structure at a glance

```
assignment/
├── main.py                    # entry point — run this
├── config.py                  # Settings dataclass + env-var loader
├── models.py                  # Job and ExecutionResult dataclasses
├── requirements.txt
│
├── scheduler/
│   ├── core.py                # JobScheduler (APScheduler wrapper)
│   ├── job.py                 # JSON parser + trigger factory
│   └── watcher.py             # watchdog event handler
│
├── tasks/
│   ├── base.py                # TaskExecutor ABC
│   ├── registry.py            # TASK_REGISTRY dict
│   ├── execute_command.py
│   ├── execute_sql.py
│   ├── send_email.py
│   ├── http_request.py
│   └── write_file.py
│
├── logger/
│   └── execution_logger.py    # NDJSON execution log writer
│
├── jobs.d/                    # drop job JSON files here
│   ├── sample-command.json
│   ├── sample-sql.json
│   ├── sample-email.json
│   ├── sample-http.json
│   └── sample-writefile.json
│
└── tests/
    ├── conftest.py
    ├── test_job_parser.py
    ├── test_executors.py
    ├── test_scheduler_core.py
    ├── test_watcher.py
    └── test_execution_logger.py
```

---

## 11. Adding a new task type

1. Create `tasks/my_task.py` with a class that subclasses `TaskExecutor` and implements `execute(self, config: dict) -> ExecutionResult`
2. Register it in `tasks/registry.py`:
   ```python
   from tasks.my_task import MyTaskExecutor
   TASK_REGISTRY["my_task"] = MyTaskExecutor
   ```
3. Drop a job file into `jobs.d/` with `"type": "my_task"` — no scheduler restart required.

---

## 12. Common errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: apscheduler` | venv not activated or deps not installed | `source .venv/bin/activate && pip install -r requirements.txt` |
| Job file silently ignored | Malformed JSON or missing required field (`job_id`, `schedule`, `task.type`) | Check stdout logs for a `Failed to parse job file` error |
| Job always `FAILURE: exit 1` | Command not found or wrong path | Test the command directly in your shell first |
| `chronoflow.log` not created | Permissions issue on the directory | Ensure the process has write access to the working directory |
| One-time job never fires | ISO 8601 timestamp is in the past | APScheduler drops past-dated jobs; use a future timestamp |
