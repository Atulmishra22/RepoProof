# DOCUMENT 5: QUEUE AND WORKER DESIGN

This document describes the distributed task queue and worker architecture for the platform. We utilize Celery 5 with Redis 7 as the message broker to handle all asynchronous work.

---

## 5.1 Celery Task Definitions

### 1. Ingest User Profile Task
*   **TASK**: `app.tasks.ingest_user_profile_task`
*   **QUEUE**: `default`
*   **PRIORITY**: medium
*   **INPUT**: `{ "username": "string — GitHub username" }`
*   **OUTPUT**: Syncs user profile metadata, caches profile README inside Redis, and upserts user repository records into the PostgreSQL `repositories` table.
*   **TIMEOUT**: 120 seconds (hard kill)
*   **SOFT TIMEOUT**: 100 seconds (graceful stop signal)
*   **MAX RETRIES**: 3
*   **RETRY BACKOFF**: exponential (10s, 30s, 60s).
*   **ON FAILURE**: Logs failure details and keeps repository analysis status as `pending`.
*   **TRIGGERS**: Called when a user submits a GitHub username in the ingestion form.

---

### 2. Run Analysis Workflow Task
*   **TASK**: `app.tasks.run_analysis_workflow_task`
*   **QUEUE**: `default`
*   **PRIORITY**: high
*   **INPUT**: `{ "repository_id": "UUID", "job_id": "UUID" }`
*   **OUTPUT**: Starts the LangGraph orchestrator, clones repository source tree, runs code fact extraction, and saves checkpoints to Postgres.
*   **TIMEOUT**: 300 seconds (hard kill)
*   **SOFT TIMEOUT**: 240 seconds (graceful stop signal)
*   **ON FAILURE**: Updates `analysis_jobs` status to `failed` and logs error message.
*   **TRIGGERS**: Triggered when a user requests analysis on an ingested repository.
*   **TRIGGERS NEXT**: Pauses and saves state checkpoint at `await_human_review` interrupt node, notifying user via WebSockets.

---

### 3. Resume Analysis Workflow Task
*   **TASK**: `app.tasks.resume_analysis_workflow_task`
*   **QUEUE**: `default`
*   **PRIORITY**: high
*   **INPUT**: `{ "job_id": "UUID", "updated_facts": "list[dict] — optional user edited/approved facts" }`
*   **OUTPUT**: Updates LangGraph checkpoint with candidate facts and resumes execution. Executes output document compilation (resume, README, LinkedIn summary, developer portfolio), uploads final files to object storage, and updates job status to `complete`.
*   **COMPILATION DETAILS & SELF-HEALING**:
    *   **ATS Optimizer**: Runs an intermediate reasoning step to select high-impact verbs/keywords matching ATS guidelines.
    *   **LaTeX Compilation**: Renders a standard Jake's style LaTeX template and compiles to PDF via `pdflatex` subprocess.
    *   **AI Self-Healing Compiler Loop**: If compilation fails, grabs the last 30 lines of the compile log and feeds the LaTeX code back to the LLM to diagnose and repair it (re-compiles up to 3 times).
    *   **Diagnostic Logs**: Persists LaTeX errors in the `AnalysisJob.error_message` column.
*   **TIMEOUT**: 240 seconds (hard kill)
*   **ON FAILURE**: Updates `analysis_jobs` and repository statuses to `failed` and records failure trace in `error_message`.
*   **TRIGGERS**: Called when a user confirms/approves their facts checklist on the Review Page.

---

### 4. Planned Auxiliary Tasks (Deferred to Production)
*   `app.tasks.cron.expire_stale_reviews`: Hourly Celery Beat sweep checking for reviews pending for >48 hours, auto-failing the stale jobs.
*   `app.tasks.cron.cleanup_old_jobs`: Daily sweep purging temporary repositories and jobs older than 30 days.

## 5.2 Queue Topology

We configure four distinct queues in Redis to isolate execution workloads and prevent resource starvation.

```
                  ┌───────────────────────┐
                  │      REDIS 7          │
                  │   MESSAGE BROKER      │
                  └──────────┬────────────┘
                             │
      ┌──────────────────────┼──────────────────────┐
      ▼                      ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  analysis    │       │  generation  │       │notifications │
│  Queue       │       │  Queue       │       │  Queue       │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                      │                      │
       ▼                      ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Worker Node A│       │ Worker Node B│       │ Worker Node C│
│ (Clone, parse│       │ (Draft doc,  │       │ (WS, Emails, │
│  repository) │       │  LLM calls)  │       │  Discord)    │
└──────────────┘       └──────────────┘       └──────────────┘
```

### Queue Workload Routing
1.  **`analysis`**: Handles repository cloning, file parsing, and LLM-driven fact extraction. These tasks are CPU and memory-intensive.
2.  **`generation`**: Dedicated to downstream document synthesis. These tasks are LLM bound and depend on third-party APIs.
3.  **`notifications`**: Dispatches WebSockets events and emails. These tasks are lightweight and need to run quickly without blocking on repository clones.
4.  **`default`**: Runs low-priority administrative cron tasks (cleanup, statistics, expirations).

### Scaling Strategy
When traffic increases, adding generic workers can lead to issues where heavy repository downloads starve lighter notification tasks.
*   **Worker Specialization**: In a high-traffic environment, workers are started with the `-Q` flag to pin them to specific queues:
    ```bash
    # Worker focused on UI events and alerts
    celery -A app.celery worker -Q notifications --concurrency=4
    # Worker focused on heavy tasks
    celery -A app.celery worker -Q analysis -c 1 --max-memory-per-child=400000
    ```
*   To scale the platform, we scale the `analysis` workers first, as repository cloning and parsing are the primary resource bottlenecks.

### Celery Beat Scheduling
A dedicated scheduler process (`celery beat`) runs alongside the workers. It reads schedules from configuration files and publishes tasks to the Redis broker at specified intervals, acting as our cron engine.

---

## 5.3 Task Result Storage Strategy

### Why we avoid the Redis Result Backend:
By default, many tutorials configure Celery to save task return values back to Redis (`CELERY_RESULT_BACKEND = "redis://"`). This is an anti-pattern in production systems for two reasons:
1.  **Memory Exhaustion**: Storing large, complex task returns (like extracted repository facts or state objects) in Redis consumes expensive RAM. If users do not actively clean up their results, Redis will eventually run out of memory and crash.
2.  **Polling Overloads**: To check task progress, the API must poll Redis repeatedly. At scale, this polling overhead creates a performance bottleneck.

### The Production Solution: PostgreSQL State Tracking
Instead of saving task results to Redis, we store them directly in the relational database:
1.  The API initializes a job record in the `analysis_jobs` table, setting the status to `queued`.
2.  When a worker picks up the task, it updates the record's status to `running` and saves the starting timestamp.
3.  As the worker executes the LangGraph workflow, each node updates the `current_node` column in PostgreSQL at the end of its run.
4.  On task failure, the worker writes the exception details directly to the `error_message` column and sets the status to `failed`.
5.  On task success, the worker writes the final output keys to the database, updates the status to `complete`, and saves the completion timestamp.

### Real-Time Updates Without Database Polling
*   **The Pipeline**:
    ```
    Celery Worker (Updates Job Row)
          │
          ▼
    Publishes Update Event ──► Redis Pub/Sub ──► FastAPI WebSocket Node ──► Browser UI
    ```
*   This approach avoids database polling. The client establishes a single, low-overhead WebSocket connection, and the database is queried only once the worker notifies the client that the job has completed.
