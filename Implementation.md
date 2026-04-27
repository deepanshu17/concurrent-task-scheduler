# ChronoFlow — Implementation Plan

> Author: Senior SRE  
> Status: **Pre-implementation — awaiting answers to open questions before coding begins**  
> Scope: Full system skeleton + fully operational `execute_command` and `http_request` executors. The remaining three executors (`execute_sql`, `send_email`, `write_file`) are stubbed safely so the system loads, runs, and logs without crashing.

---

## 0. Guiding Principles


| Principle                                           | How it manifests here                                                                                                                                                                                                                                     |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Never crash the scheduler**                       | Every executor, file-parse path, and watcher callback is wrapped in `try/except`; exceptions surface as `FAILURE` log records                                                                                                                             |
| **Fail loudly at config time, silently at runtime** | Bad JSON → logged + skipped at startup; unknown `task_type` → `FAILURE` result, not an exception                                                                                                                                                          |
| **Pluggable by design**                             | Adding a new executor = one new file + one line in `registry.py`. Zero changes elsewhere                                                                                                                                                                  |
| **Observable**                                      | Every execution (success or failure) produces a structured JSON log line; human-readable console logs also emitted via stdlib `logging`                                                                                                                   |
| **Stub, don't remove**                              | Unimplemented executors (`execute_sql`, `send_email`, `write_file`) return a `FAILURE` result with a clear `"not_implemented"` message — they are registered in `TASK_REGISTRY` and the system routes to them correctly; they just don't do real work yet |


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
  ├── executor_cls = TASK_REGISTRY.get(job.task_type)
  │     └── if None → result = ExecutionResult(status="FAILURE", output="unknown task type: ...")
  │
  ├── result = executor_cls().execute(job.task_config)   # wrapped in try/except
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

All five types are registered unconditionally. The three stubs are live entries that return `FAILURE("not implemented")` — they do not raise, they do not skip, they produce observable log records.

```python
TASK_REGISTRY: dict[str, type[TaskExecutor]] = {
    "execute_command": ExecuteCommandExecutor,
    "http_request":    HttpRequestExecutor,
    "execute_sql":     ExecuteSQLExecutor,      # stub
    "send_email":      SendEmailExecutor,       # stub
    "write_file":      WriteFileExecutor,       # stub
}
```

---

## 6. Implemented Executors (Phase 1)

### 6.1 `execute_command`

**Config keys:**


| Key       | Type   | Required | Default                | Notes                                      |
| --------- | ------ | -------- | ---------------------- | ------------------------------------------ |
| `command` | `str`  | yes      | —                      | Full shell command string                  |
| `timeout` | `int`  | no       | `CMD_TIMEOUT_SEC` (60) | Seconds before `subprocess.TimeoutExpired` |
| `shell`   | `bool` | no       | `true`                 | See security note                          |


**Implementation notes:**

- Uses `subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)`
- `shell=True` is the pragmatic default — matches the README examples (`rm -rf /tmp/...`, pipeline commands). SRE context: we own the job files, this is not a public API.
- `output` field contains `stdout` on success; `stderr` (or combined) on failure
- `returncode != 0` → `FAILURE`; `TimeoutExpired` → `FAILURE` with clear message
- stdout is truncated to **4 096 chars** in the log to prevent log bloat from verbose scripts

**Result mapping:**

```
returncode == 0      → SUCCESS, output = stdout[:4096]
returncode != 0      → FAILURE, output = f"exit {rc}: {stderr[:4096]}"
TimeoutExpired       → FAILURE, output = f"timed out after {timeout}s"
Exception            → FAILURE, output = traceback string
```

### 6.2 `http_request`

**Config keys:**


| Key          | Type         | Required | Default                 | Notes                                                             |
| ------------ | ------------ | -------- | ----------------------- | ----------------------------------------------------------------- |
| `method`     | `str`        | yes      | —                       | GET / POST / PUT / DELETE / PATCH                                 |
| `url`        | `str`        | yes      | —                       | Full URL                                                          |
| `headers`    | `dict`       | no       | `{}`                    | Merged with auto-set headers                                      |
| `body`       | `dict | str` | no       | `None`                  | If dict → JSON-encoded; `Content-Type: application/json` auto-set |
| `timeout`    | `int`        | no       | `HTTP_TIMEOUT_SEC` (30) | Seconds                                                           |
| `verify_ssl` | `bool`       | no       | `true`                  | Set to false only for internal endpoints                          |


**Implementation notes:**

- Uses `urllib.request.urlopen` with a manually built `urllib.request.Request` object
- If `body` is a `dict`, it is JSON-serialised and `Content-Type: application/json` is added
- Response body is decoded (UTF-8, errors=`replace`) and truncated to **4 096 chars**
- HTTP 4xx / 5xx status codes → `FAILURE` (urllib raises `HTTPError` for these)
- `URLError` (DNS failure, connection refused, timeout) → `FAILURE`
- SSL: `verify_ssl=false` creates an unverified `ssl.SSLContext` — logged at WARNING level when used

**Result mapping:**

```
2xx response         → SUCCESS, output = f"HTTP {status}: {body[:4096]}"
HTTPError (4xx/5xx)  → FAILURE, output = f"HTTP {status}: {reason}"
URLError             → FAILURE, output = f"connection error: {reason}"
TimeoutError         → FAILURE, output = f"timed out after {timeout}s"
Exception            → FAILURE, output = traceback string
```

---

## 7. Stub Executors (Phase 2 — safe placeholders)

`execute_sql`, `send_email`, and `write_file` each follow this exact pattern:

```python
class ExecuteSQLExecutor(TaskExecutor):
    def execute(self, config: dict) -> ExecutionResult:
        return ExecutionResult(
            job_id=config.get("_job_id", "unknown"),
            executed_at=datetime.utcnow(),
            status="FAILURE",
            output="execute_sql is not yet implemented",
        )
```

**Why `FAILURE` and not a silent skip?** It surfaces in the execution log so operators know a job is defined but non-functional — preferable to silent success that hides misconfiguration.

> **Note on `_job_id` in config**: `run_job` injects `_job_id` into `task_config` before passing to the executor. This avoids the executor needing access to the `Job` dataclass directly.

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
| `executed_at` | `str`                   | ISO 8601 UTC (`datetime.utcnow().isoformat() + "Z"`) |
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

### Phase 1 test scope (matches current implementation scope)


| File                             | Coverage focus                                                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_job_parser.py`       | Valid cron, valid ISO 8601, missing keys, malformed JSON, unknown task type                                                                                  |
| `tests/test_executors.py`        | `execute_command`: success, non-zero exit, timeout; `http_request`: 2xx success, 4xx, 5xx, DNS failure, JSON body encoding; stub executors: return `FAILURE` |
| `tests/test_scheduler_core.py`   | `add_job`, `remove_job`, duplicate job_id, unknown task_type routing                                                                                         |
| `tests/test_watcher.py`          | created/modified/deleted events trigger correct scheduler calls                                                                                              |
| `tests/test_execution_logger.py` | Log line is valid JSON, all fields present, file append mode                                                                                                 |


### What we do NOT test yet

- `execute_sql`, `send_email`, `write_file` real execution (stubs only)
- Live cron scheduling (we mock APScheduler — no real waits)
- High-concurrency race conditions (unit test scope)

### Key mocking strategy

```
subprocess.run          → mock for execute_command
urllib.request.urlopen  → mock for http_request
apscheduler.schedulers  → MagicMock for scheduler core
watchdog events         → instantiate handler directly, call on_created/on_modified/on_deleted
open() / file writes    → mock or tmp_path for logger
```

---

## 11. File-by-File Implementation Order

1. `requirements.txt` + `config.py` + `models.py`
2. `scheduler/job.py` (parser + trigger factory)
3. `scheduler/core.py` (APScheduler wrapper)
4. `tasks/base.py` + `tasks/registry.py`
5. `tasks/execute_command.py` ← **fully implemented**
6. `tasks/http_request.py` ← **fully implemented**
7. `tasks/execute_sql.py` + `tasks/send_email.py` + `tasks/write_file.py` ← **stubs**
8. `logger/execution_logger.py`
9. `scheduler/watcher.py`
10. `main.py`
11. `tests/` (all five files)
12. `jobs.d/` sample files (one for each implemented task type)

---

## 12. Open Questions (answers needed before coding)

See the companion section below — these affect code-level decisions.

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

### `jobs.d/sample-sql-stub.json`

```json
{
  "job_id": "sql-stub-demo",
  "description": "Will log FAILURE/not-implemented until Phase 2",
  "schedule": "0 3 * * *",
  "task": {
    "type": "execute_sql",
    "db_url": "sqlite:///app.db",
    "query": "DELETE FROM logs WHERE created_at < date('now','-30 days')"
  }
}
```

