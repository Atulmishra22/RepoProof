# GitHub Repository Intelligence Platform: Implementation Checklist

This checklist tracks the implementation progress of the platform. Items will be marked as completed (`[x]`) as we proceed. If any errors occur, they will be resolved, logged in the `docs/error_context.md` file, and noted here.

---

## [x] Phase 1: Foundation
- [x] Create base workspace folders (`/backend`, `/frontend`, `/docs`).
- [x] Create backend `pyproject.toml` and configure the `uv` package manager.
- [x] Configure `docker-compose.yml` containing PostgreSQL 16, Redis 7, and MinIO.
- [x] Initialize Alembic for database migrations.
- [x] Write the FastAPI base app skeleton with `GET /api/v1/health` check.
- [x] Create Next.js 16 skeleton with shadcn/ui and basic router pages.
- [x] Verify container connectivity (FastAPI connecting to Postgres and Redis).
- [x] **First Milestone Test**: Confirm container healthcheck statuses and endpoint ping returns 200.

---

## [x] Phase 2: GitHub Ingestion
- [x] Implement database models for `users`, `repositories`, and `analysis_jobs`.
- [x] Write Alembic migration script to construct initial tables.
- [x] Build GitHub API client wrapper to fetch user profile, public repositories, and raw profile README markdown.
- [x] Implement `ingest_user_profile_task` Celery task.
- [x] Set up BFF REST routes `POST /api/v1/users/ingest` and `GET /api/v1/repositories`.
- [x] Build Next.js Dashboard page showcasing profile README, stats, and repository lists.
- [x] **First Milestone Test**: Submitting a GitHub username triggers ingestion task, populates database, and caches profile README in Redis.

---

## [x] Phase 3: Analysis Pipeline (No LLM)
- [x] Set up LangGraph 0.2+ orchestrator with PostgreSQL State Checkpointer.
- [x] Write file-cloning logic to pull repo branches to temp worker storage.
- [x] Write the `clone_or_fetch_file_tree` graph node (builds flat file tree JSON).
- [x] Write a heuristic-based fact extractor node (rules checking file count, language weight, dependencies).
- [x] Create Celery task `run_analysis_workflow` to run the compiled graph.
- [x] **First Milestone Test**: Submitting a repository creates a folder structure and completes analysis without external LLMs.

---

## [x] Phase 4: LLM Integration & Fact Extraction
- [x] Deploy local LiteLLM container configured to route calls to the Gemini API (`gemini-3.1-flash-lite`).
- [x] Set up Gemini API keys and test communication.
- [x] Write the LLM extraction prompt using structural Pydantic schemas.
- [x] Implement `validate_facts` rule-based verification node.
- [x] Integrate Langfuse tracing to monitor node operations and token counts.
- [x] **First Milestone Test**: Repository parsing returns structured facts citing files and line numbers.

---

## [x] Phase 5: Human-In-The-Loop
- [x] Insert the `await_human_review` interrupt node inside LangGraph.
- [x] Write the FastAPI WebSocket gateway to broadcast updates using Redis Pub/Sub.
- [x] Implement Next.js Zustand stores (`useAnalysisStore`, `useReviewStore`) to track real-time job states.
- [x] Build the interactive Review checklist UI on the frontend.
- [x] Create REST routes `GET /api/v1/reviews/{id}` and `PATCH /api/v1/reviews/{id}/facts`.
- [x] Hook up Celery task `resume_analysis_workflow` to load database checkpoints.
- [x] **First Milestone Test**: Analysis halts at review node, updates UI, and resumes upon user confirmation.

---

## [ ] Phase 6: Output Generation
- [ ] Define `GeneratedOutput` and `OutputDownload` database models and execute Alembic migrations.
- [ ] Install LaTeX compilation packages (`texlive-latex-base`, `texlive-fonts-recommended`, `texlive-latex-extra`) in backend/worker Docker containers.
- [ ] Design LLM templates to synthesize approved facts into final copies (LinkedIn summary, GitHub README, Portfolio page).
- [ ] Implement the ATS Optimizer Reasoning stage before resume generation to select high-impact verbs/keywords.
- [ ] Implement Jake's LaTeX resume template with dynamic single-page budget layout controls.
- [ ] Build the 3-step AI Self-Healing compiler retry loop using LaTeX logs to fix formatting/compilation failures.
- [ ] Save LaTeX compilation error logs and diagnostics to `AnalysisJob.error_message`.
- [ ] Write final document compiler nodes in LangGraph and connect to the workflow.
- [ ] Configure file uploading tasks to Cloudflare R2 / MinIO for `.pdf`, `.md`, and `.txt` files.
- [ ] Build presigned URL generator in FastAPI backend.
- [ ] Create frontend premium outputs page (`/dashboard/outputs/[repoId]`) with copy-to-clipboard, version selector, and download triggers.
- [ ] **First Milestone Test**: Presigned URL download returns the correct PDF/markdown/text formats, and AI self-healing successfully diagnoses and repairs invalid LaTeX syntax.

---

## [ ] Phase 7: Polish and Deploy
- [ ] Implement NextAuth.js GitHub OAuth flow.
- [ ] Add Redis rate-limiting middleware to API routes.
- [ ] Set up the hourly review expiration and daily data purge cron tasks.
- [ ] Deploy backend worker nodes to Render, database to Supabase, and frontend to Vercel.
- [ ] **First Milestone Test**: OAuth login, ingestion, and generation workflows function in production.

---

## [x] Phase 8A: Security + UX
- [x] Add is_private column to Repository model + migration.
- [x] Fix shared cache reuse query in tasks.py (filter private repos).
- [x] Store is_private flag when ingesting repositories.
- [x] Split repositories endpoint into public + private routes.
- [x] Implement verify_github_ownership guard dependency.
- [x] Implement smart 3-level cache architecture.
- [x] Remove hardcoded "Atulmishra22" fallbacks.
- [x] Return onboarding_required flag in GET /repositories response.
- [x] Add onboarding screen overlay in frontend dashboard.
- [x] Compare last_commit_at and last_analyzed_at to skip analysis of unchanged repositories.
- [x] Set up Playwright E2E testing framework and write integration test checking live authentication, onboarding, and repository listing.
- [x] Implement review page layout scrollbar to prevent page stretching on long checklist facts.
- [x] Implement ingestion mapping isolation in background tasks to prevent mixing repositories across different users.
- [x] **First Milestone Test**: Mismatched users get 403 when querying private repos; correct users load private repos directly from DB, unchanged repo analyses return a cached status, and other users' public repos ingest into their own isolated profile records.

---

## [x] Phase 8B: Top 3 Repository Recommendations
- [x] Add recursive Git Tree fetching method in async and sync GitHub Clients.
- [x] Implement Repository Quality Score (RQS) algorithm combining size, stars/forks (log-scaled), freshness, and code quality modifiers.
- [x] Run RQS calculations in parallel using asyncio.gather with automatic Redis caching based on commit timestamps.
- [x] Extend `/repositories` API response to return recommendation_score and recommended flags.
- [x] Add multi-select checkbox controls to repository cards in Next.js dashboard grid.
- [x] Render recommended star badges and RQS score indicators on repo cards.
- [x] Build batch-analysis button triggering sequential analysis for checked repositories.
- [x] **First Milestone Test**: Top 3 repositories are pre-selected on data load, 0-star repos with unit tests are recommended correctly, and batch analysis triggers only for the selected repos.
