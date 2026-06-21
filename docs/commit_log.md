# Project Git Commit Log

This document tracks every commit made during the development of the **RepoProof** platform. Each entry logs the commit hash, timestamp, message, and a detailed summary of what features were added or changed.

---

## Commit History

### Commit 1: Initial Blueprints
*   **Hash**: `983e8f7` (Initial Commit)
*   **Timestamp**: 2026-06-20 17:20:00 UTC+5:30
*   **Message**: `docs: add system design blueprints and checklist`
*   **Description**:
    *   Moved all system architecture, database schema, API design, queue, storage, docker, and observability specs to `/RepoProof/docs/`.
    *   Added the interactive build checklist `checklist.md`.
    *   Configured the AI session context files.
*   **Files Modified/Created**:
    *   [system_architecture.md](file:///d:/cold-mail/RepoProof/docs/system_architecture.md)
    *   [database_schema.md](file:///d:/cold-mail/RepoProof/docs/database_schema.md)
    *   [api_design.md](file:///d:/cold-mail/RepoProof/docs/api_design.md)
    *   [frontend_architecture.md](file:///d:/cold-mail/RepoProof/docs/frontend_architecture.md)
    *   [queue_worker_design.md](file:///d:/cold-mail/RepoProof/docs/queue_worker_design.md)
    *   [storage_design.md](file:///d:/cold-mail/RepoProof/docs/storage_design.md)
    *   [observability_design.md](file:///d:/cold-mail/RepoProof/docs/observability_design.md)
    *   [docker_architecture.md](file:///d:/cold-mail/RepoProof/docs/docker_architecture.md)
    *   [implementation_roadmap.md](file:///d:/cold-mail/RepoProof/docs/implementation_roadmap.md)
    *   [checklist.md](file:///d:/cold-mail/RepoProof/docs/checklist.md)
    *   [error_context.md](file:///d:/cold-mail/RepoProof/docs/error_context.md)
    *   [session_context.md](file:///d:/cold-mail/RepoProof/docs/session_context.md)

### Commit 2: Commit Log Setup
*   **Hash**: `a5de0fc`
*   **Timestamp**: 2026-06-20 17:50:00 UTC+5:30
*   **Message**: `docs: create commit log file to track changes`
*   **Description**:
    *   Created this commit log tracking document to maintain context for future iterations.

### Commit 3: Backend Package Management Migration
*   **Hash**: `5488025`
*   **Timestamp**: 2026-06-20 18:27:00 UTC+5:30
*   **Message**: `feat: migrate backend dependency management to uv and pyproject.toml`
*   **Description**:
    *   Created `backend/pyproject.toml` using standard PEP 621 tags to hold loose top-level dependencies.
    *   Configured the `backend/Dockerfile` to fetch the binary of the Rust-based package manager `uv` and use it for dependency installation.
    *   Wrote the initial FastAPI `app/main.py` entrypoint and Celery task client `app/celery_app.py`.
    *   Set up root `docker-compose.yml` pre-wired for Postgres, Redis, MinIO, Celery and Langfuse.
    *   Deleted the old `backend/requirements.txt` file.

---

### Commit 4: Blueprints Update (Sandbox, Memory, GraphRAG, Clarification Gate)
*   **Hash**: `085ab8d`
*   **Timestamp**: 2026-06-20 18:52:00 UTC+5:30
*   **Message**: `docs: update design blueprints to match uv, pyproject.toml, sandbox models, preference memory, graphRAG and clarification gates`
*   **Description**:
    *   Updated the system architecture blueprint adding sections on directory-mount security (Sandbox), user preference feedback loops (Reflection), GraphRAG (Token Optimization), and Clarification Gates (Anti-hallucination validation).
    *   Synced `checklist.md`, `implementation_roadmap.md`, and `session_context.md` files to reflect `pyproject.toml` and `uv` package manager configurations.
    *   Fixed absolute file path links in documentation keys.

### Commit 5: Dependency Version Freeze
*   **Hash**: `740d609`
*   **Timestamp**: 2026-06-20 19:20:00 UTC+5:30
*   **Message**: `chore: freeze backend package dependency versions and log git WSL error`
*   **Description**:
    *   Froze all loose backend dependencies in `pyproject.toml` to exact versions compiled and validated in the docker environment.
    *   Documented package freeze details and WSL2 root git dubious ownership error in `error_context.md`.
    *   Defined the `context_navigator` custom subagent to handle project memory retrieval.

### Commit 6: Phase 1 Foundation Completion
*   **Hash**: `371df3a`
*   **Timestamp**: 2026-06-20 19:45:00 UTC+5:30
*   **Message**: `feat: complete phase 1 foundation with health checks, alembic init, nextjs scaffolding, and langfuse pinning`
*   **Description**:
    *   Bootstrapped database migrations with Alembic initialization.
    *   Added `backend/app/database.py` and `backend/app/redis_client.py` and connected them to database/Redis clients.
    *   Updated `backend/app/main.py` healthcheck to ping PostgreSQL and Redis and fail dynamically on errors.
    *   Scaffolded Next.js 16 under `/frontend` with Tailwind CSS, TypeScript, and App Router.
    *   Pinned the Langfuse image to `langfuse/langfuse:2` in `docker-compose.yml` to prevent clickhouse requirement crash.
    *   Verified all container healthchecks and local routing communication.

---

### Commit 7: Phase 2 Ingestion and WSL Stability
*   **Hash**: `f094872`
*   **Timestamp**: 2026-06-21 02:20:00 UTC+5:30
*   **Message**: `Phase 2: Complete GitHub Ingestion and stabilize WSL/Redis environment`
*   **Description**:
    *   Designed user profile and repository tables (`User`, `Repository`, `AnalysisJob`) and applied the initial Alembic schema migration.
    *   Implemented GitHub client wrapper to query user profile, public repositories, and raw profile README markdown.
    *   Built FastAPI endpoints (`/users/ingest` and `/repositories`) and Celery task (`ingest_user_profile_task`) to fetch and store user profiles.
    *   Stabilized the Redis health check in `docker-compose.yml` to prevent container restarts and cache key loss.
    *   Configured the host Windows `.wslconfig` with `vmIdleTimeout=3600000` (1 hour) and `localhostForwarding=true` to prevent auto-shutdown and enable native host routing.
    *   Created `seed_profile.py` inside the backend container to bypass rate-limits and cache the custom markdown README of `Atulmishra22`.
    *   Upgraded the `/dashboard` Next.js frontend with premium dark styling, loading skeletons, and connection failure alerts.

### Commit 8: Phase 3 LangGraph Analysis Pipeline and Frontend Real-time Polling
*   **Hash**: `e5b83a1`
*   **Timestamp**: 2026-06-21 13:00:00 UTC+5:30
*   **Message**: `feat: complete Phase 3 Analysis Pipeline and frontend integration`
*   **Description**:
    *   Set up LangGraph 0.2+ orchestrator with PostgreSQL State Checkpointer (`PostgresSaver`) and psycopg connection pool.
    *   Wrote repository cloning logic and directory structure walker nodes to construct flat file tree JSON, uploading it to MinIO storage.
    *   Implemented heuristic facts extraction node scanning for packages, frameworks, dependencies, and file metrics.
    *   Added Celery task wrapper and API endpoints (`POST /repositories/{id}/analyze` and `GET /repositories/{id}/analysis/{job_id}`).
    *   Extended main database router to self-heal stalled background analysis tasks.
    *   Connected frontend dashboard cards to trigger analysis, recover active jobs, poll real-time status, and display currently executing LangGraph nodes.

### Commit 9: Phase 4 LLM Integration & Fact Extraction
*   **Hash**: `c064edd`
*   **Timestamp**: 2026-06-21 17:31:00 UTC+5:30
*   **Message**: `feat: implement LLM fact extraction, validation nodes, pricing config, and dashboard UI display`
*   **Description**:
    *   Configured LiteLLM proxy inside `config.yaml` to route `gpt-4o-mini` to `gemini/gemini-3.1-flash-lite` using active credentials.
    *   Created structured Pydantic schemas `ExtractedFact` and `FactExtractionResult` in `llm_schemas.py`.
    *   Implemented `extract_llm_facts_node` and rule-based `validate_facts_node` inside `analysis_graph.py` to fetch, validate, and verify snippets.
    *   Integrated Langfuse tracing to log runs, monitor token usage, and record exact running cost in Postgres.
    *   Exposed `/api/v1/repositories/{id}/analysis-result` in `main.py` and developed a premium modal UI on dashboard to render results.

### Commit 10: Phase 5 Human-In-The-Loop Review
*   **Hash**: `1204df2`
*   **Timestamp**: 2026-06-21 19:55:00 UTC+5:30
*   **Message**: `feat: implement Phase 5 human-in-the-loop review pipeline, WebSockets status broadcasting, and Zustand review UI`
*   **Description**:
    *   Added intermediate result saving node and pass-through review node in `analysis_graph.py`, compiling the workflow with `interrupt_before=["await_human_review"]`.
    *   Modified Celery tasks inside `tasks.py` to handle the graph interrupt state and added `resume_analysis_workflow_task`.
    *   Implemented FastAPI REST endpoints `/reviews/{job_id}/facts` (updating checkpointer state and resuming graph) and `/reviews/{job_id}/chat` (interactive AI pairing partner using codebase context).
    *   Added WebSocket routing `/api/v1/ws/reviews` backed by Redis Pub/Sub listener to broadcast analysis job status transitions to connected clients.
    *   Added Zustand store `reviewStore.ts` and created the interactive double-column Review Page under `/dashboard/review/[jobId]/page.tsx` with dynamic controls, copy utilities, and action panels.





