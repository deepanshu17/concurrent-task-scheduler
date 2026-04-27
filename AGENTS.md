# ChronoFlow — Agent Planning Document

> Interview build · target completion: ~60 minutes  
> Goal: a working, well-logged, in-memory job scheduler that any agent or contributor can pick up and extend.

---

## 1. Project Goal

Build a **lightweight, in-memory job scheduling service** in Python that:

- Watches a directory for JSON job-definition files
- Schedules each job using either a **cron string** (recurring) or an **ISO 8601 timestamp** (one-time)
- Executes the task defined in the job using a pluggable executor model
- Logs every execution with `job_id`, `timestamp`, and `SUCCESS | FAILURE`
- Reacts to file-system changes (add / update / delete) **without restarting**

---

## 2. Supported Task Types (Top 5)

| # | Type | What it does | Key stdlib / dep |
|---|------|-------------|-----------------|
| 1 | `execute_command` | Run a shell command via `subprocess` | `subprocess` (stdlib) |
| 2 | `execute_sql` | Execute a SQL statement on a SQLite file or any SQLAlchemy URL | `sqlite3` (stdlib) |
| 3 | `send_email` | Send an email over SMTP with subject + body | `smtplib` + `email` (stdlib) |
| 4 | `http_request` | Make an HTTP GET/POST/PUT/DELETE with optional headers & body | `urllib` (stdlib) |
| 5 | `write_file` | Write or append text content to a file path | `pathlib` (stdlib) |

All five use **zero third-party dependencies** except the scheduler itself.

---

## 3. Stack & Design Decisions

| Concern | Choice | Reason |
|---------|--------|--------|
| Language | Python 3.11+ | Stdlib covers all 5 task types; fast to prototype |
| Scheduler engine | **APScheduler 3.x** | Supports cron + date triggers, in-memory, thread-safe, battle-tested |
| File watching | **watchdog** | Cross-platform FS events; minimal setup |
| Concurrency | `ThreadPoolExecutor` (via APScheduler) | Lets overlapping jobs run in parallel without asyncio complexity |
| Config format | JSON | Matches assignment spec; no extra parser needed |
| Logging | stdlib `logging` + structured `ExecutionRecord` | Keeps output readable and machine-parseable |
| Persistence | None | In-memory only; state rebuilt from `jobs.d/` on restart |
| SQL backend | SQLite (default) | Zero-server; path configured in job JSON |

**Why APScheduler over `schedule` lib?**  
`schedule` has no native cron support and is single-threaded. APScheduler handles both trigger types, concurrency, and misfired job policies out of the box.

---

## 4. Project Structure

```
assignment/
├── AGENTS.md                  # ← this file
├── README.md
├── requirements.txt
├── main.py                    # entry point: wires everything up and blocks
├── config.py                  # JOBS_DIR path, log level, executor pool size
├── models.py                  # shared dataclasses: Job, ExecutionResult
│
├── scheduler/
│   ├── __init__.py
│   ├── core.py                # JobScheduler: wraps APScheduler, owns job registry
│   ├── watcher.py             # watchdog FileSystemEventHandler
│   └── job.py                 # JSON parser + trigger factory (imports Job from models)
│
├── tasks/
│   ├── __init__.py
│   ├── base.py                # TaskExecutor ABC  →  execute(config) -> ExecutionResult
│   ├── registry.py            # TASK_REGISTRY dict: str → TaskExecutor subclass
│   ├── execute_command.py
│   ├── execute_sql.py
│   ├── send_email.py
│   ├── http_request.py
│   └── write_file.py
│
├── logger/
│   ├── __init__.py
│   └── execution_logger.py    # logs ExecutionResult as structured JSON lines
│
├── jobs.d/                    # watched directory — drop JSON files here
│   ├── sample-command.json
│   ├── sample-sql.json
│   ├── sample-email.json
│   ├── sample-http.json
│   └── sample-writefile.json
│
└── tests/
    ├── conftest.py                # shared fixtures (tmp jobs.d dir, mock scheduler)
    ├── test_job_parser.py         # parse_job(), make_trigger() — cron vs ISO 8601
    ├── test_executors.py          # each TaskExecutor in isolation
    ├── test_scheduler_core.py     # add/remove/run job lifecycle
    ├── test_watcher.py            # file-system events trigger correct scheduler calls
    └── test_execution_logger.py   # log output format and file writes
```

---

## 5. Core Data Models

Both dataclasses live in `models.py` at the project root — a neutral home that no single package owns. `scheduler/`, `tasks/`, and `logger/` all import from it; none of them depend on each other for shared types.

### Job (dataclass)

```python
@dataclass
class Job:
    job_id: str          # unique identifier from JSON
    description: str = ""
    schedule: str        # cron string OR ISO 8601 timestamp
    task_type: str       # maps to a key in TASK_REGISTRY
    task_config: dict    # passed as-is to the executor
    source_file: Path    # which .json file this came from
```

### ExecutionResult (dataclass)

```python
@dataclass
class ExecutionResult:
    job_id: str
    executed_at: datetime
    status: Literal["SUCCESS", "FAILURE"]
    output: str          # stdout / return value / error message
```

---

## 6. Key Interfaces

### TaskExecutor (ABC)

```python
class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, config: dict) -> ExecutionResult:
        ...
```

Adding a new task type = **one new file** that subclasses `TaskExecutor`, registered in `registry.py`. The scheduler never changes.

### TASK_REGISTRY

```python
TASK_REGISTRY: dict[str, type[TaskExecutor]] = {
    "execute_command": ExecuteCommandExecutor,
    "execute_sql":     ExecuteSQLExecutor,
    "send_email":      SendEmailExecutor,
    "http_request":    HttpRequestExecutor,
    "write_file":      WriteFileExecutor,
}
```

---

## 7. System Flow

```
startup
  └─ main.py
       ├─ load config (JOBS_DIR, pool size, log level)
       ├─ init JobScheduler  (starts APScheduler with ThreadPoolExecutor)
       ├─ scan jobs.d/ → parse each JSON → schedule each job
       └─ start watchdog Observer on jobs.d/
              │
              ├─ FileCreatedEvent  → parse JSON → scheduler.add_job()
              ├─ FileModifiedEvent → scheduler.remove_job() → scheduler.add_job()
              └─ FileDeletedEvent  → scheduler.remove_job()

job fires (APScheduler thread)
  └─ scheduler.run_job(job)
       ├─ resolve executor = TASK_REGISTRY[job.task_type]
       ├─ result = executor.execute(job.task_config)
       └─ execution_logger.log(result)
              └─ writes JSON line:
                 {"job_id": "...", "executed_at": "...", "status": "SUCCESS", "output": "..."}
```

---

## 8. Schedule Trigger Logic

```python
def make_trigger(schedule: str):
    try:
        dt = datetime.fromisoformat(schedule)   # one-time
        return DateTrigger(run_date=dt)
    except ValueError:
        return CronTrigger.from_crontab(schedule)  # recurring
```

---

## 9. Job Definition Schema

```jsonc
{
  "job_id": "unique-string",          // required, must be unique across all files
  "description": "Human-readable",    // optional
  "schedule": "<cron | ISO 8601>",    // required
  "task": {
    "type": "<task_type>",            // required, must exist in TASK_REGISTRY
    // ... task-specific fields below
  }
}
```

### Per-task config fields

**`execute_command`**
```json
{ "type": "execute_command", "command": "echo hello" }
```

**`execute_sql`**
```json
{ "type": "execute_sql", "db_url": "sqlite:///app.db", "query": "DELETE FROM logs WHERE created_at < date('now','-30 days')" }
```

**`send_email`**
```json
{ "type": "send_email", "smtp_host": "localhost", "smtp_port": 1025, "from": "scheduler@local", "to": ["ops@local"], "subject": "Report ready", "body": "See attached." }
```

**`http_request`**
```json
{ "type": "http_request", "method": "POST", "url": "https://hooks.example.com/notify", "headers": {}, "body": {} }
```

**`write_file`**
```json
{ "type": "write_file", "path": "/var/log/heartbeat.log", "content": "alive\n", "mode": "append" }
```

---

## 10. Build Order (60-min Interview Plan)

| Time | Milestone |
|------|-----------|
| 0–5 min | `requirements.txt`, `config.py`, `main.py` skeleton |
| 5–15 min | `scheduler/job.py` — dataclass, JSON parser, trigger factory |
| 15–25 min | `scheduler/core.py` — APScheduler wrapper, add/remove/run |
| 25–35 min | `tasks/base.py`, `tasks/registry.py`, `tasks/execute_command.py` (MVP working end-to-end) |
| 35–45 min | Remaining 4 executors (`execute_sql`, `send_email`, `http_request`, `write_file`) |
| 45–52 min | `scheduler/watcher.py` — watchdog integration |
| 52–56 min | `logger/execution_logger.py` — structured JSON-line logs |
| 56–60 min | `tests/` — run pytest; drop sample `jobs.d/*.json`, live smoke test |

---

## 11. Error Handling Principles

- Each executor wraps its logic in `try/except`; exceptions become `FAILURE` results, never crash the scheduler thread.
- File parse errors (bad JSON, missing fields) are logged and the file is skipped — the scheduler keeps running.
- APScheduler misfire grace period set to 60 s so jobs that fire slightly late still run.

---

## 12. Testing Strategy

### Philosophy
- Tests are **fast and offline** — no real SMTP server, no real HTTP endpoints, no real cron waits
- Use `unittest.mock` / `pytest-mock` to stub external calls; test only the logic we own
- Each executor is tested in complete isolation from the scheduler

### Test file breakdown

| File | What it tests | Key technique |
|------|--------------|---------------|
| `test_job_parser.py` | `parse_job()` produces correct `Job`; cron string → `CronTrigger`; ISO 8601 → `DateTrigger`; bad JSON raises gracefully | Parametrize valid + invalid inputs |
| `test_executors.py` | Each of the 5 executors returns `SUCCESS` / `FAILURE` `ExecutionResult` correctly | Mock `subprocess.run`, `sqlite3.connect`, `smtplib.SMTP`, `urllib.request.urlopen`, `open` |
| `test_scheduler_core.py` | `add_job` registers with APScheduler; `remove_job` deregisters; duplicate `job_id` is handled | Mock APScheduler; assert calls |
| `test_watcher.py` | `FileCreatedEvent` → `add_job`; `FileModifiedEvent` → remove + add; `FileDeletedEvent` → `remove_job` | Use `tmp_path` fixture; fire events manually |
| `test_execution_logger.py` | Log line is valid JSON; contains correct fields; `FAILURE` results are also written | Write to `tmp_path`; parse output with `json.loads` |

### Running tests

```bash
pytest tests/ -v                      # run all
pytest tests/test_executors.py -v     # single file
pytest tests/ --tb=short -q           # compact output (good for interview demo)
```

### `conftest.py` shared fixtures

```python
@pytest.fixture
def tmp_jobs_dir(tmp_path):
    return tmp_path / "jobs.d"        # isolated per test, auto-cleaned

@pytest.fixture
def mock_scheduler():
    return MagicMock()                # stands in for JobScheduler
```

---

## 13. Dependencies (`requirements.txt`)

```
apscheduler==3.10.4
watchdog==4.0.1
pytest==8.2.0
pytest-mock==3.14.0
```

Everything else (`subprocess`, `sqlite3`, `smtplib`, `urllib`, `pathlib`, `logging`) is Python stdlib.
