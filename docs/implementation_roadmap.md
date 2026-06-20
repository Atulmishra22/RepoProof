# DOCUMENT 9: IMPLEMENTATION ROADMAP

This document outlines the phased build strategy and a compressed 3-week development plan for a solo developer.

---

## Phases

### PHASE 1: Foundation
*   **GOAL**: Establish the local runtime environment across the entire stack.
*   **DEMO**: Running `docker compose up` starts all services, database migrations run successfully, FastAPI returns a 200 health check, and a Next.js page renders.
*   **DURATION**: 3 Days.
*   **WHAT TO BUILD**:
    1.  Create the backend directory structure, install dependencies (FastAPI, Pydantic v2, Alembic, Celery).
    2.  Write base Dockerfiles for backend services and configure `docker-compose.yml` (Postgres, Redis, MinIO).
    3.  Create the Next.js project skeleton using shadcn/ui and Zustand.
    4.  Configure Alembic to manage migrations and write a basic health check endpoint.
*   **FIRST TEST THAT MUST PASS**: `curl -f http://localhost:8000/api/v1/health` returns `{"status":"ok"}`.
*   **HOW TO KNOW YOU'RE DONE**: All Docker services run healthy and you can access the Next.js landing page on `localhost:3000`.
*   **DB CHANGES**: Create `users` table.
*   **NEW API ENDPOINTS**: `GET /api/v1/health`
*   **NEW ENV VARS**: `DATABASE_URL`, `REDIS_URL`.

---

### PHASE 2: GitHub Ingestion
*   **GOAL**: Implement the pipeline to ingest repositories and query the GitHub API.
*   **DEMO**: Submit a GitHub URL on the dashboard, see metadata fetched, save the repository to the database, and display a queued job.
*   **DURATION**: 3 Days.
*   **WHAT TO BUILD**:
    1.  Write the GitHub API client integration to fetch repository details and languages.
    2.  Implement the database models for `repositories` and `analysis_jobs`.
    3.  Define the Celery task `ingest_repository` and configure routing to the `analysis` queue.
    4.  Build the Next.js Dashboard page and Repository Submission form.
*   **FIRST TEST THAT MUST PASS**: Calling the ingestion endpoint with `https://github.com/fastapi/fastapi` creates a `repositories` record with correct star counts and owners.
*   **HOW TO KNOW YOU'RE DONE**: Submitting a URL via the UI shows the repository card on the dashboard with a `pending` status badge.
*   **DB CHANGES**: Create `repositories` and `analysis_jobs` tables.
*   **NEW API ENDPOINTS**:
    *   `POST /api/v1/repositories`
    *   `GET /api/v1/repositories`
    *   `GET /api/v1/repositories/{id}`
*   **NEW ENV VARS**: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`.

---

### PHASE 3: Analysis Pipeline (No LLM)
*   **GOAL**: Build the LangGraph orchestrator and compile file structures without using third-party APIs.
*   **DEMO**: Trigger an analysis run and watch the LangGraph workflow execute locally, cloning the repository tree and extracting files.
*   **DURATION**: 4 Days.
*   **WHAT TO BUILD**:
    1.  Install LangGraph 0.2+ and configure the Postgres checkpoint system (`langgraph-checkpoint-postgres`).
    2.  Write the `clone_or_fetch_file_tree` node using Python `git` libraries to fetch repository files.
    3.  Implement a heuristic-based fact extractor node (rules checking file count, language weight, dependencies) to verify graph flow.
    4.  Build the Celery task `run_analysis_workflow` to run the compiled graph.
*   **FIRST TEST THAT MUST PASS**: Triggering a job runs the graph end-to-end, producing a JSON map of the repository's files in MinIO.
*   **HOW TO KNOW YOU'RE DONE**: An analysis run completes, displaying step-by-step progress nodes in the terminal.
*   **DB CHANGES**: None.
*   **NEW API ENDPOINTS**:
    *   `POST /api/v1/repositories/{id}/analyze`
    *   `GET /api/v1/repositories/{id}/analysis/{job_id}`
*   **NEW ENV VARS**: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.

---

### PHASE 4: LLM Integration + Fact Extraction
*   **GOAL**: Extract concrete technical claims from the cloned code using an LLM.
*   **DEMO**: Submit a repository, watch the worker use an LLM to extract facts, validate them structurally, and display them in the database.
*   **DURATION**: 3 Days.
*   **WHAT TO BUILD**:
    1.  Configure LiteLLM to route calls to the Gemini 1.5 Flash API.
    2.  Replace the heuristic extractor with an LLM prompt that takes file tree context and returns structured JSON claims (Pydantic model).
    3.  Write the `validate_facts` rule validation node (file and schema checks).
    4.  Integrate Langfuse to trace the extraction call and record token usage in the database.
*   **FIRST TEST THAT MUST PASS**: The extraction node returns a structured array of facts, each citing a valid file path and line range.
*   **HOW TO KNOW YOU'RE DONE**: Running the analysis generates real technical claims in the database linked to the job ID.
*   **DB CHANGES**: Create `code_facts` and `system_events` tables.
*   **NEW API ENDPOINTS**: `GET /api/v1/repositories/{id}/analysis/{job_id}/facts`
*   **NEW ENV VARS**: `LITELLM_PROXY_URL`, `GEMINI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

---

### PHASE 5: Human-In-The-Loop
*   **GOAL**: Implement the workflow interrupt and resumption mechanism.
*   **DEMO**: Start an analysis; the worker pauses at the review checkpoint, updates the UI via WebSockets, and resumes generation when the user confirms their decisions.
*   **DURATION**: 5 Days.
*   **WHAT TO BUILD**:
    1.  Configure the LangGraph state machine with an interrupt boundary at the `await_human_review` node.
    2.  Write the FastAPI WebSocket endpoint to broadcast `review_required` notifications using Redis Pub/Sub.
    3.  Build the interactive Zustand-managed Review Page in Next.js.
    4.  Implement the `PATCH /reviews/{id}/facts` endpoint to update facts and trigger the `resume_analysis_workflow` task.
*   **FIRST TEST THAT MUST PASS**: Sending a patch request to the reviews endpoint resumes the suspended graph execution past the interrupt checkpoint.
*   **HOW TO KNOW YOU'RE DONE**: The entire workflow runs, pauses, updates the UI in real-time, and resumes upon user confirmation.
*   **DB CHANGES**: Create `human_reviews` table.
*   **NEW API ENDPOINTS**:
    *   `GET /api/v1/reviews/pending`
    *   `GET /api/v1/reviews/{review_id}`
    *   `PATCH /api/v1/reviews/{review_id}/facts`
    *   `POST /api/v1/reviews/{review_id}/reject`
    *   `ws://api/ws/{user_id}`
*   **NEW ENV VARS**: None.

---

### PHASE 6: Output Generation
*   **GOAL**: Generate and export final documents using approved facts.
*   **DEMO**: View generated resumes, LinkedIn summaries, and readmes in the browser, and download them.
*   **DURATION**: 3 Days.
*   **WHAT TO BUILD**:
    1.  Write LLM prompt nodes for the remaining outputs (resume, LinkedIn, readme, portfolio) using approved facts.
    2.  Implement S3 file export logic to upload markdown files to Cloudflare R2/MinIO.
    3.  Build the R2 presigned URL generator in the API layer.
    4.  Design the Next.js Outputs dashboard displaying tabs for each generated format.
*   **FIRST TEST THAT MUST PASS**: Clicking the download button retrieves a working, temporary presigned download link.
*   **HOW TO KNOW YOU'RE DONE**: You can view, copy, and download all four generated document types from the UI.
*   **DB CHANGES**: Create `generated_outputs` and `output_downloads` tables.
*   **NEW API ENDPOINTS**:
    *   `GET /api/v1/repositories/{id}/outputs`
    *   `GET /api/v1/outputs/{id}`
    *   `POST /api/v1/outputs/{id}/regenerate`
    *   `GET /api/v1/outputs/{id}/download`
*   **NEW ENV VARS**: None.

---

### PHASE 7: Polish and Deploy
*   **GOAL**: Secure the application, deploy to production, and enable monitoring.
*   **DEMO**: Log in with GitHub OAuth in production, submit a repo, review facts, and download your resume.
*   **DURATION**: 4 Days.
*   **WHAT TO BUILD**:
    1.  Set up NextAuth.js OAuth flows using the Postgres adapter.
    2.  Add rate-limiting middleware to API routes using Redis.
    3.  Deploy the frontend to Vercel, the database to Supabase, and Celery workers to Render.
    4.  Configure the daily cleanup cron jobs.
*   **FIRST TEST THAT MUST PASS**: Logging in with OAuth redirects to the dashboard.
*   **HOW TO KNOW YOU'RE DONE**: The application runs in production with secure OAuth routing.
*   **DB CHANGES**: Create `usage_metrics` table.
*   **NEW API ENDPOINTS**:
    *   `POST /api/v1/auth/github`
    *   `POST /api/v1/auth/signout`
    *   `GET /api/v1/auth/me`
*   **NEW ENV VARS**: `NEXTAUTH_SECRET`, `SUPABASE_DATABASE_URL`.

---

## The 3-Week Build Order

If you are on a tight schedule, this plan focuses on core features while cutting out non-essential elements.

### What gets cut:
*   **Prometheus + Grafana Metrics**: (Deferred to v2) - We rely on Langfuse logs and Render dashboards instead.
*   **NextAuth.js Multi-provider OAuth**: (Deferred to v2) - We use a mock token-based header auth during local development, or a single-button GitHub login flow in production.
*   **Sentence-Transformers local embeddings**: (Deferred to v2) - We pass approved facts directly to the LLM via prompt context rather than doing a vector similarity pre-search.
*   **Output Version History in UI**: (Deferred to v2) - Regeneration overwrites the current output version rather than maintaining historical copies.
*   **Celery Beat Scheduled Crons**: (Deferred to v2) - We clean up database rows manually or rely on basic database trigger timeouts instead of running a separate Celery Beat scheduler daemon.

---

### Day-by-Day Calendar

```
WEEK 1: Foundation, Ingestion, and LangGraph Basics
├── Day 1: Build Docker Compose file (Postgres, Redis, MinIO) & initialize FastAPI.
├── Day 2: Set up the Next.js frontend repository using Tailwind CSS and shadcn/ui.
├── Day 3: Build database models for Users and Repos; run migrations.
├── Day 4: Write the GitHub API repository metadata ingestion task.
├── Day 5: Write the git clone script using tempfile paths.
├── Day 6: Set up LangGraph and compile the base graph nodes.
└── Day 7: Connect the ingestion pipeline to LangGraph; verify state saves locally.

WEEK 2: LLMs, Fact Extraction, and WebSockets
├── Day 8: Connect LiteLLM and run the Gemini 1.5 Flash fact-extraction prompts.
├── Day 9: Implement Pydantic fact structures and validate output fields.
├── Day 10: Configure Langfuse to trace extraction calls.
├── Day 11: Set up the FastAPI WebSocket endpoint.
├── Day 12: Build the frontend Status page and track graph node changes in real-time.
├── Day 13: Implement the await_human_review interrupt node.
└── Day 14: Connect the review state to the database and resume pipeline on confirmation.

WEEK 3: Outputs, Deployment, and Polish
├── Day 15: Write prompts to generate resumes and LinkedIn summaries from approved facts.
├── Day 16: Write files to MinIO and implement presigned download links.
├── Day 17: Build the Next.js Outputs tabbed dashboard.
├── Day 18: Connect GitHub OAuth using NextAuth.js.
├── Day 19: Add Redis rate-limiting middleware to API endpoints.
├── Day 20: Deploy the database to Supabase and services to Render/Vercel.
└── Day 21: Verify production deployments end-to-end; write portfolio docs.
```
