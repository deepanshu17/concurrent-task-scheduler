# ChronoFlow — Implementation Plan

> Author: Senior SRE  
> Status: **Implemented** — all five task executors are functional; scheduler, watcher, and execution logger match this document.  
> Scope: In-memory scheduling (APScheduler), JSON jobs under `JOBS_DIR`, watchdog-driven reloads, and stdlib-backed executors for all supported `task.type` values.

---

## 0. Guiding Principles


| Principle                                           | How it manifests here                                                                                                                                                                                                                                     |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Never crash the scheduler**                       | Every executor, file-parse path, and watcher callback is wrapped in `try/except`; exceptions surface as `FAILURE` log records                                                                                                                             |
| **Fail loudly at config time, silently at runtime** | Bad JSON → logged + skipped at startup; unknown `task_type` → `FAILURE` result, not an exception                                                                                                                                                          |
| **Pluggable by design**                             | Adding a new executor = one new file + one line in `registry.py`. Zero changes elsewhere                                                                                                                                                                  |
| **Observable**                                      | Every execution (success or failure) produces a structured JSON log line; human-readable console logs also emitted via stdlib `logging`                                                                                                                   |
| **Executor errors stay inside the job**             | Each executor catches failures and returns `ExecutionResult(status="FAILURE", output=...)`; `run_job` only sees a traceback if `execute()` itself raises |


---

## 1. Dependency & Environment

### `requirements.txt`

```
apscheduler==3.10.4
watchdog==4.0.1
pytest==8.2.0
pytest-mock==3.14.0
```

No third-party HTTP or SQL libraries. All five task types rely on stdlib only.

### Python version

Target: **Python 3.11+**. We rely on `str | None` union syntax (PEP 604, available from 3.10+), `Literal` and `dataclasses` from stdlib `typing`, and `tomllib` / `exception notes` that land in 3.11. No backports required.

---

## 2. Configuration (`config.py`)

A single module that exposes typed constants. Values can be overridden by environment variables so deployments don't require code edits.

```
JOBS_DIR          → env: CHRONOFLOW_JOBS_DIR      default: ./jobs.d
LOG_FILE          → env: CHRONOFLOW_LOG_FILE       default: ./chronoflow.log
LOG_LEVEL         → env: CHRONOFLOW_LOG_LEVEL      default: INFO
EXECUTOR_POOL_SIZE→ env: CHRONOFLOW_POOL_SIZE      default: 5
MISFIRE_GRACE_SEC → env: CHRONOFLOW_MISFIRE_GRACE  default: 60
HTTP_TIMEOUT_SEC  → env: CHRONOFLOW_HTTP_TIMEOUT   default: 30
CMD_TIMEOUT_SEC   → env: CHRONOFLOW_CMD_TIMEOUT    default: 60
```

`jobs.d/` is auto-created on startup if absent — the system should not require manual directory setup.

---

## 3. Data Models (`models.py`)

Unchanged from AGENTS.md spec. Two `@dataclass`s — neutral ground imported by all three sub-packages.

```python
@dataclass
class Job:
    job_id:      str
    schedule:    str
    task_type:   str
    task_config: dict
    source_file: Path
    description: str = ""

@dataclass
class ExecutionResult:
    job_id:      str
    executed_at: datetime
    status:      Literal["SUCCESS", "FAILURE"]
    output:      str
```

**Note on `Job.source_file`**: used by the watcher to reverse-look up which jobs to remove when a file is deleted or modified. The registry in `core.py` maintains a `dict[str, Job]` keyed on `job_id` and a secondary `dict[Path, list[str]]` mapping file → list of job_ids it defined.

---

## 4. Scheduler Layer (`scheduler/`)

### 4.1 `scheduler/job.py` — Parser + Trigger Factory

`**parse_job(path: Path) -> list[Job]**`

- Opens the file, `json.loads` the content
- Validates required keys: `job_id`, `schedule`, `task.type`
- Returns a **list** (one file can define multiple jobs — future-proofs the design even though sample files are one-per-file)
- On any `KeyError`, `json.JSONDecodeError`, or `ValueError`: logs the error with the file path, returns `[]` — caller never sees an exception

`**make_trigger(schedule: str) -> DateTrigger | CronTrigger`**

```python
def make_trigger(schedule: str):
    try:
        dt = datetime.fromisoformat(schedule)
        return DateTrigger(run_date=dt)
    except ValueError:
        return CronTrigger.from_crontab(schedule)
```

If both branches fail (malformed cron), the `CronTrigger` raises `ValueError` — caught in the caller (`core.add_job`), which logs and skips the job.

### 4.2 `scheduler/core.py` — JobScheduler

Wraps APScheduler's `BackgroundScheduler` with a `ThreadPoolExecutor`.

**Public API:**


| Method                              | Behaviour                                                                                         |
| ----------------------------------- | ------------------------------------------------------------------------------------------------- |
| `start()`                           | Starts APScheduler; called once from `main.py`                                                    |
| `shutdown()`                        | Graceful stop; registered with `atexit`                                                           |
| `add_job(job: Job)`                 | Creates trigger, registers with APScheduler, adds to `_job_registry` and `_file_registry`         |
| `remove_job(job_id: str)`           | Removes from APScheduler + both registries; no-op if job not found                                |
| `remove_jobs_from_file(path: Path)` | Looks up `_file_registry[path]` and removes each job_id                                           |
| `run_job(job: Job)`                 | Called by APScheduler on each fire; resolves executor, calls `execute()`, passes result to logger |


**Duplicate `job_id` handling**: if `add_job` is called with a `job_id` already in `_job_registry`, the old entry is removed first (remove-then-add semantics). This means a `FileModifiedEvent` on a file that redefines the same ID is idempotent and safe.

`**run_job` execution flow:**

```
run_job(job)
  │
  ├── config = {**job.task_config, "job_id": job.job_id}
  │
  ├── executor_cls = TASK_REGISTRY.get(job.task_type)
  │     └── if None → result = ExecutionResult(status="FAILURE", output="unknown task type: ...")
  │
  ├── result = executor_cls().execute(config)   # wrapped in try/except
  │     └── any unhandled exception → result = FAILURE with traceback string
  │
  └── execution_logger.log(result)
```

### 4.3 `scheduler/watcher.py` — File-System Watcher

`JobFileHandler(FileSystemEventHandler)` observes only `*.json` files in `JOBS_DIR` (non-recursive).


| Event         | Action                                                                                 |
| ------------- | -------------------------------------------------------------------------------------- |
| `on_created`  | `parse_job(path)` → `scheduler.add_job(job)` for each                                  |
| `on_modified` | `scheduler.remove_jobs_from_file(path)` → `parse_job(path)` → `scheduler.add_job(job)` |
| `on_deleted`  | `scheduler.remove_jobs_from_file(path)`                                                |


**Debounce consideration**: Some editors (vim, PyCharm) emit two rapid `modified` events per save (write-truncate + write-content). We handle this by catching `JobLookupError` (APScheduler's "job not found") in `remove_job` gracefully rather than implementing a timer debounce — keeps it simple and safe.

---

## 5. Task Executor Layer (`tasks/`)

### 5.1 `tasks/base.py` — ABC

```python
class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, config: dict) -> ExecutionResult:
        ...
```

No constructor arguments. Each executor is stateless — instantiated fresh on every `run_job` call.

### 5.2 `tasks/registry.py` — TASK_REGISTRY

All five types are registered unconditionally. Each executor is stateless and returns `SUCCESS` or `FAILURE` with a string `output`.

```python
TASK_REGISTRY: dict[str, type[TaskExecutor]] = {
    "execute_command": ExecuteCommandExecutor,
    "http_request":    HttpRequestExecutor,
    "execute_sql":     ExecuteSQLExecutor,
    "send_email":      SendEmailExecutor,
    "write_file":      WriteFileExecutor,
}
```

---

## 6. Implemented Executors

### 6.1 `execute_command`

**Config keys:**


| Key       | Type   | Required | Default                | Notes                                      |
| --------- | ------ | -------- | ---------------------- | ------------------------------------------ |
| `command` | `str`  | yes      | —                      | Full shell command string                  |
| `timeout_sec` | `int` / `float` | no | `300` | Seconds before `subprocess.TimeoutExpired` |
| `shell`   | `bool` | no       | `true`                 | If `true`, command runs through the shell; if `false`, `shlex.split` + argv list |
| `output_limit` | `int` | no | `4096` | Max combined stdout+stderr characters stored in `output` |


**Implementation notes:**

- Uses `subprocess.run(..., timeout=timeout_sec)` where `timeout_sec` comes from `tasks.timeout_config.timeout_sec_from_config`
- Default `shell=True` supports pipelines and shell features when job authors need them; set `shell=false` for argv-only execution
- `output` combines stdout and stderr (truncated to `output_limit`)
- `returncode != 0` → `FAILURE`; `TimeoutExpired` → `FAILURE` with a timeout message

**Result mapping:**

```
returncode == 0      → SUCCESS, output = combined stdout+stderr (truncated)
returncode != 0      → FAILURE, output = combined stdout+stderr (truncated)
TimeoutExpired       → FAILURE, timeout message
Exception            → FAILURE, output = str(exception)
```

### 6.2 `http_request`

**Config keys:**


| Key          | Type         | Required | Default                 | Notes                                                             |
| ------------ | ------------ | -------- | ----------------------- | ----------------------------------------------------------------- |
| `method`     | `str`        | no       | `GET`                   | GET / POST / PUT / DELETE / PATCH                                 |
| `url`        | `str`        | yes      | —                       | Full URL                                                          |
| `headers`    | `dict`       | no       | `{}`                    | Merged with auto-set headers                                      |
| `body`       | `dict | str` | no       | `None`                  | If dict → JSON-encoded; `Content-Type: application/json` auto-set |
| `timeout_sec` | `int` / `float` | no    | `30` | Seconds for `urlopen` timeout |
| `verify_ssl` | `bool`       | no       | `true`                  | If `false`, uses an unverified SSL context (internal endpoints only) |
| `output_limit` | `int` | no | `4096` | Max response body bytes read into `output` |


**Implementation notes:**

- Uses `urllib.request.urlopen` with a manually built `urllib.request.Request` object
- If `body` is a `dict`, it is JSON-serialised and `Content-Type: application/json` is added
- Response body is read up to `output_limit` bytes (plus one byte to detect overflow), decoded as UTF-8 (`errors=replace`), then truncated in the stored string if needed
- HTTP 4xx / 5xx status codes → `FAILURE` (urllib raises `HTTPError` for these)
- `URLError` (DNS failure, connection refused, timeout) → `FAILURE`
- SSL: `verify_ssl=false` creates an unverified `ssl.SSLContext`

**Result mapping:**

```
2xx response         → SUCCESS, output includes status and decoded body (truncated)
HTTPError (4xx/5xx)  → FAILURE (raised by urllib)
URLError / timeouts  → FAILURE, connection / timeout message from exception
Exception            → FAILURE, output = str(exception)
```

### 6.3 `execute_sql`

**Config keys:**

| Key | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `db_url` | `str` | yes | — | `sqlite:///path`, `sqlite:///:memory:`, `:memory:`, or a bare filesystem path |
| `query` | `str` | yes | — | Single SQL statement |
| `max_rows` | `int` | no | `50` | For `SELECT`-like results, max rows fetched into the success `output` preview |

**Behaviour:**

- Opens SQLite via `sqlite3.connect`
- If the statement looks like a read query (`SELECT` prefix or cursor has `description`), fetches up to `max_rows` rows and returns column names + row preview in `output`
- Otherwise commits and reports `rows_affected` using `total_changes` when available, else `cursor.rowcount`

### 6.4 `send_email`

**Config keys:**

| Key | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `smtp_host` | `str` | yes | — | |
| `smtp_port` | `int` | yes | — | |
| `from` | `str` | yes | — | Sender address |
| `to` | `list[str]` | yes | — | Non-empty list of recipients |
| `subject` | `str` | no | `""` | |
| `body` | `str` | no | `""` | Plain-text body |
| `timeout_sec` | `int` / `float` | no | `30` | SMTP socket timeout |
| `username` | `str` | no | — | If both `username` and `password` are non-empty, `SMTP.login` is called |
| `password` | `str` | no | — | Used with `username` for `SMTP.login` |

### 6.5 `write_file`

**Config keys:**

| Key | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `path` | `str` | yes | — | File path |
| `content` | `str` | no | `""` | Written as text |
| `mode` | `str` | no | `overwrite` | `append` or `overwrite`; aliases `write` / `w` → overwrite, `a` → append |
| `encoding` | `str` | no | `utf-8` | |

**Behaviour:** Creates parent directories as needed; opens file in append or write mode.

---

## 8. Execution Logger (`logger/execution_logger.py`)

### Output format

One JSON object per line (NDJSON / JSON Lines) written to `LOG_FILE`:

```json
{"job_id": "report-001", "executed_at": "2026-04-27T12:00:00.123456Z", "status": "SUCCESS", "output": "Sales report generated."}
```

### Implementation

- Opens `LOG_FILE` in append mode on each write (no file handle held open — safe across log rotation)
- Also emits a human-readable line via `logging.info` / `logging.error` to stdout for live tailing
- Thread-safe: file appends are atomic on all POSIX systems for writes < PIPE_BUF; for safety, a module-level `threading.Lock` guards the file open/write/close sequence

### Log record schema


| Field         | Type                    | Notes                                                |
| ------------- | ----------------------- | ---------------------------------------------------- |
| `job_id`      | `str`                   | From `ExecutionResult`                               |
| `executed_at` | `str`                   | ISO 8601 from `ExecutionResult.executed_at` (append `Z` only if naive) |
| `status`      | `"SUCCESS" | "FAILURE"` | From `ExecutionResult`                               |
| `output`      | `str`                   | Truncated to 4 096 chars before write                |


---

## 9. Entry Point (`main.py`)

```
1. Configure stdlib logging (level, format)
2. Ensure JOBS_DIR exists (mkdir -p semantics)
3. Instantiate JobScheduler → scheduler.start()
4. Register atexit → scheduler.shutdown()
5. Scan JOBS_DIR for *.json → parse_job() → scheduler.add_job()
6. Instantiate JobFileHandler(scheduler) → watchdog Observer
7. observer.schedule(handler, JOBS_DIR, recursive=False)
8. observer.start()
9. Block on observer.join() (or signal handler for SIGTERM/SIGINT)
```

Signal handling: `SIGINT` and `SIGTERM` both call `scheduler.shutdown()` + `observer.stop()` cleanly before exit.

---

## 10. Testing Plan

### Current test scope


| File                             | Coverage focus                                                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_job_parser.py`       | Valid cron, valid ISO 8601, missing keys, malformed JSON, unknown task type                                                                                  |
| `tests/test_executors.py`        | Happy-path smoke for all five executors with stdlib calls mocked (`subprocess`, `sqlite3`, `smtplib`, `urllib`) or `tmp_path` for `write_file`               |
| `tests/test_scheduler_core.py`   | `add_job`, `remove_job`, duplicate job_id, unknown task_type routing                                                                                         |
| `tests/test_watcher.py`          | created/modified/deleted events trigger correct scheduler calls                                                                                              |
| `tests/test_execution_logger.py` | Log line is valid JSON, all fields present, file append mode                                                                                                 |


### What we do NOT test (by design in this repo)

- Live cron waits, real remote HTTP/SMTP, or production-sized concurrency (unit scope only)

### Key mocking strategy

```
subprocess.run          → mock for execute_command
sqlite3.connect       → mock for execute_sql (lightweight fake connection)
smtplib.SMTP          → mock for send_email
urllib.request.urlopen  → mock for http_request
apscheduler.schedulers  → MagicMock for scheduler core
watchdog events         → instantiate handler directly, call on_created/on_modified/on_deleted
open() / file writes    → mock or tmp_path for logger / write_file
```

---

## 11. File layout (reference)

Typical layout after implementation:

1. `requirements.txt` + `config.py` + `models.py`
2. `scheduler/job.py`, `scheduler/core.py`, `scheduler/watcher.py`
3. `tasks/base.py`, `tasks/registry.py`, `tasks/timeout_config.py`, and one module per executor
4. `logger/execution_logger.py`
5. `main.py`
6. `tests/` and `jobs.d/` / `test_jobs/` sample JSON

---

## 12. Open questions

None tracked in this document — behaviour is defined by the code and tests in-repo.

---

## Appendix: Sample Job Definitions

### `jobs.d/sample-command.json`

```json
{
  "job_id": "heartbeat-cmd",
  "description": "Echo alive every minute",
  "schedule": "* * * * *",
  "task": {
    "type": "execute_command",
    "command": "echo alive"
  }
}
```

### `jobs.d/sample-http.json`

```json
{
  "job_id": "webhook-ping",
  "description": "POST to a webhook every 5 minutes",
  "schedule": "*/5 * * * *",
  "task": {
    "type": "http_request",
    "method": "POST",
    "url": "https://httpbin.org/post",
    "headers": {"X-Source": "chronoflow"},
    "body": {"status": "alive"}
  }
}
```

### `jobs.d/sample-sql.json` (example)

```json
{
  "job_id": "sql-maintenance",
  "description": "Example SQL job",
  "schedule": "0 3 * * *",
  "task": {
    "type": "execute_sql",
    "db_url": "sqlite:///app.db",
    "query": "DELETE FROM logs WHERE created_at < date('now','-30 days')"
  }
}
```

