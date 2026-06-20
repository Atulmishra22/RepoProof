# DOCUMENT 5: QUEUE AND WORKER DESIGN

This document describes the distributed task queue and worker architecture for the platform. We utilize Celery 5 with Redis 7 as the message broker to handle all asynchronous work.

---

## 5.1 Celery Task Definitions

### 1. Ingest Repository
*   **TASK**: `app.tasks.ingestion.ingest_repository`
*   **QUEUE**: `analysis`
*   **PRIORITY**: medium
*   **INPUT**: `{ "repository_id": "UUID", "user_id": "UUID" }`
*   **OUTPUT**: `{ "success": "boolean" }` stored in the PostgreSQL `repositories` table (updates metadata fields and toggles status to `pending`).
*   **TIMEOUT**: 60 seconds (hard kill)
*   **SOFT TIMEOUT**: 45 seconds (graceful stop signal)
*   **MAX RETRIES**: 3
*   **RETRY BACKOFF**: exponential (10s, 30s, 60s), max delay 120 seconds.
*   **ON FAILURE**: Sets the repository `analysis_status` to `failed` and logs the exception in `system_events`.
*   **TRIGGERS**: Called when a user submits a new repository URL via the frontend.
*   **TRIGGERS NEXT**: Auto-triggers `run_analysis_workflow` on success.

---

### 2. Run Analysis Workflow
*   **TASK**: `app.tasks.pipeline.run_analysis_workflow`
*   **QUEUE**: `analysis`
*   **PRIORITY**: high
*   **INPUT**: `{ "job_id": "UUID", "repository_id": "UUID" }`
*   **OUTPUT**: State checkpoints stored in PostgreSQL via the LangGraph checkpointer.
*   **TIMEOUT**: 300 seconds (hard kill)
*   **SOFT TIMEOUT**: 240 seconds (graceful stop signal)
*   **MAX RETRIES**: 0 (no task-level retries; the graph handles retries internally per node).
*   **RETRY BACKOFF**: None.
*   **ON FAILURE**: Updates `analysis_jobs` status to `failed`, sets the repository status to `failed`, and logs the error details.
*   **TRIGGERS**: Triggered on successful repository metadata ingestion or manually by the user.
*   **TRIGGERS NEXT**: Triggers `notify_review_required` when the graph reaches the `await_human_review` interrupt checkpoint.

---

### 3. Resume Analysis Workflow
*   **TASK**: `app.tasks.pipeline.resume_analysis_workflow`
*   **QUEUE**: `generation`
*   **PRIORITY**: high
*   **INPUT**:  
    `{ "job_id": "UUID", "review_id": "UUID", "approved_facts": "list[dict]", "rejected_fact_ids": "list[UUID]" }`
*   **OUTPUT**: Finalized documents written to the database `generated_outputs` and files saved to Cloudflare R2.
*   **TIMEOUT**: 180 seconds (hard kill)
*   **SOFT TIMEOUT**: 150 seconds (graceful stop signal)
*   **MAX RETRIES**: 0 (workflow resume handles internal transient LLM API retries).
*   **RETRY BACKOFF**: None.
*   **ON FAILURE**: Sets `analysis_jobs` and repository statuses to `failed`, releasing resources and logging the failure.
*   **TRIGGERS**: Triggered when a user approves/edits facts via the review portal API.
*   **TRIGGERS NEXT**: Triggers `generate_embeddings` on success.

---

### 4. Generate Embeddings
*   **TASK**: `app.tasks.embeddings.generate_embeddings`
*   **QUEUE**: `analysis`
*   **PRIORITY**: low
*   **INPUT**: `{ "job_id": "UUID", "approved_fact_ids": "list[UUID]" }`
*   **OUTPUT**: 768-dimensional float arrays saved to the `fact_embeddings` table.
*   **TIMEOUT**: 120 seconds (hard kill)
*   **SOFT TIMEOUT**: 90 seconds (graceful stop signal)
*   **MAX RETRIES**: 3
*   **RETRY BACKOFF**: exponential (5s, 15s, 30s), max delay 60 seconds.
*   **ON FAILURE**: Logs failure to `system_events`. Embeddings can be re-run manually; a failure does not block the user from accessing their generated resume.
*   **TRIGGERS**: Triggered on successful completion of the resume generation step.
*   **TRIGGERS NEXT**: None.

---

### 5. Notify Review Required
*   **TASK**: `app.tasks.notifications.notify_review_required`
*   **QUEUE**: `notifications`
*   **PRIORITY**: medium
*   **INPUT**: `{ "job_id": "UUID", "user_id": "UUID", "review_id": "UUID" }`
*   **OUTPUT**: Publishes WebSocket message to Redis channel `user:events:{user_id}` and triggers an email notification.
*   **TIMEOUT**: 30 seconds (hard kill)
*   **SOFT TIMEOUT**: 20 seconds (graceful stop signal)
*   **MAX RETRIES**: 5
*   **RETRY BACKOFF**: exponential (10s, 60s, 300s).
*   **ON FAILURE**: Logs failure to `system_events` (does not break the core workflow; the user can still find the review task on their dashboard).
*   **TRIGGERS**: Triggered when the analysis workflow hits the interrupt checkpoint.
*   **TRIGGERS NEXT**: None.

---

### 6. Expire Stale Reviews
*   **TASK**: `app.tasks.cron.expire_stale_reviews`
*   **QUEUE**: `default`
*   **PRIORITY**: low
*   **INPUT**: `{}`
*   **OUTPUT**: Updates expired reviews to `timed_out` status and sets their jobs to `failed`.
*   **TIMEOUT**: 60 seconds (hard kill)
*   **SOFT TIMEOUT**: 45 seconds (graceful stop signal)
*   **MAX RETRIES**: 1
*   **RETRY BACKOFF**: None.
*   **ON FAILURE**: Logs warning alert to `system_events`.
*   **TRIGGERS**: Triggered by Celery Beat scheduler once every hour.
*   **TRIGGERS NEXT**: None.

---

### 7. Cleanup Old Jobs
*   **TASK**: `app.tasks.cron.cleanup_old_jobs`
*   **QUEUE**: `default`
*   **PRIORITY**: low
*   **INPUT**: `{}`
*   **OUTPUT**: Purges data older than 30 days from `analysis_jobs` and deletes temporary files from Cloudflare R2.
*   **TIMEOUT**: 300 seconds (hard kill)
*   **SOFT TIMEOUT**: 240 seconds (graceful stop)
*   **MAX RETRIES**: 0.
*   **RETRY BACKOFF**: None.
*   **ON FAILURE**: Logs failure to `system_events`.
*   **TRIGGERS**: Triggered by Celery Beat scheduler daily at 00:00 UTC.
*   **TRIGGERS NEXT**: None.

---

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
