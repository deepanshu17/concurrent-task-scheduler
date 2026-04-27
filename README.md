# Concurrent Task Scheduler

A lightweight in-memory Python job scheduler that loads JSON job definitions from a watched directory, runs tasks on cron or one-time schedules with concurrency, and updates the schedule when job files are added, modified, or deleted - no database, no restart.

To clone the repo, set up a virtual environment, install dependencies, start the scheduler (`python main.py`), and run the test suite, follow **[RUNNING.md](RUNNING.md)**.

## Problem Statement

Modern applications need to run background tasks on a predefined schedule. These tasks range from sending daily email digests and generating reports to performing routine data cleanup. A reliable and dynamic job scheduler is a critical component for automating these workflows.

## Objective

Design and implement a lightweight, in-memory job scheduling service. The service will read job definitions from a configuration directory, execute the defined tasks according to their specified schedules, and log the outcomes.

---

## Key Requirements & Considerations

### 1. Dynamic Job Management

The scheduler must monitor a directory (e.g., `/etc/scheduler/jobs.d/`) for job definition files in JSON format. It must react to file system changes **without requiring a service restart**:


| Event                  | Behaviour                                              |
| ---------------------- | ------------------------------------------------------ |
| New file added         | Job is immediately parsed and added to the schedule    |
| Existing file modified | Scheduler updates or reschedules the corresponding job |
| File deleted           | Job is removed from the schedule                       |


### 2. Flexible Scheduling Formats

The service must support two types of time-based schedules:

- **One-Time** — a specific future timestamp in ISO 8601 format (e.g., `2025-10-26T15:00:00Z`)
- **Recurring** — a cron string (e.g., `*/5 * * * *` for every 5 minutes)

### 3. Extensible Task Execution

The system must be designed to support different kinds of tasks. For this implementation, only one task type is required:

- **`execute_command`** — runs a shell command

However, the design must make it straightforward to add new task types in the future (e.g., `http_request`) **without altering the core scheduling logic**.

### 4. Concurrency and Logging

- The scheduler must be able to **run multiple jobs concurrently** if their schedules overlap.
- Each job execution must produce a simple log entry recording:
  - Unique job ID
  - Execution timestamp
  - Status: `SUCCESS` or `FAILURE`

### 5. In-Memory Operation

The scheduler does not need a persistent database. All scheduling and job state is managed in memory and can be rebuilt from the configuration files upon startup.

---

## Job Definition File Format

Job definitions are JSON files placed in the watched directory.

### Example 1 — Recurring Job (`daily-report.json`)

```json
{
  "job_id": "report-001",
  "description": "Generate the daily sales report.",
  "schedule": "0 1 * * *",
  "task": {
    "type": "execute_command",
    "command": "/usr/bin/python /opt/scripts/generate_sales_report.py"
  }
}
```

### Example 2 — One-Time Job (`onetime-cleanup.json`)

```json
{
  "job_id": "cleanup-xyz",
  "description": "Perform a one-time cleanup of temporary files.",
  "schedule": "2025-09-20T02:00:00Z",
  "task": {
    "type": "execute_command",
    "command": "rm -rf /tmp/stale-data/*"
  }
}
```
