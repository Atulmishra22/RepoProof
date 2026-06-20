# AI Resume Context & Handover Note

> **ATTENTION AI AGENT**: If you are starting a new session or resuming work on this repository, **read this file first**. It contains the exact state of the project, saving token context and preventing you from having to read the entire codebase.

---

## 1. Project Identity & Architecture
*   **Project**: GitHub Repository Intelligence Platform
*   **Core Blueprint**:
    *   System Architecture: [system_architecture.md](file:///d:/cold-mail/RepoProof/docs/system_architecture.md)
    *   Database Schema: [database_schema.md](file:///d:/cold-mail/RepoProof/docs/database_schema.md)
    *   API Design: [api_design.md](file:///d:/cold-mail/RepoProof/docs/api_design.md)
    *   Frontend Architecture: [frontend_architecture.md](file:///d:/cold-mail/RepoProof/docs/frontend_architecture.md)
    *   Docker Setup: [docker_architecture.md](file:///d:/cold-mail/RepoProof/docs/docker_architecture.md)
    *   Queue Design: [queue_worker_design.md](file:///d:/cold-mail/RepoProof/docs/queue_worker_design.md)
    *   Storage Design: [storage_design.md](file:///d:/cold-mail/RepoProof/docs/storage_design.md)
    *   Observability: [observability_design.md](file:///d:/cold-mail/RepoProof/docs/observability_design.md)
    *   Roadmap: [implementation_roadmap.md](file:///d:/cold-mail/RepoProof/docs/implementation_roadmap.md)

---

## 2. Current Status
*   **Current Phase**: Phase 2: GitHub Ingestion
*   **Checklist State**: Located at [checklist.md](file:///d:/cold-mail/RepoProof/docs/checklist.md) (Phase 1 completed, Phase 2 pending).
*   **Last Action Taken**: Completed Phase 1: Foundation. Initialized Alembic database migrations, enriched `/api/v1/health` with deep Postgres + Redis connection status checks, scaffolded the Next.js 16 frontend with Tailwind CSS v4, and resolved Langfuse's ClickHouse startup requirements by pinning to image version `2`.
*   **Runtime Logs & Errors**: Tracked in [error_context.md](file:///d:/cold-mail/RepoProof/docs/error_context.md).

---

## 3. Handover Instruction: Where to Resume
When the user gives the command to resume, you must execute **Phase 2: GitHub Ingestion** tasks:
1.  **Implement Models**: Write SQLAlchemy models for `users`, `repositories`, and `analysis_jobs` inside `/backend/app/models.py`.
2.  **Generate Migration**: Create and run the Alembic migration scripts to create the database tables.
3.  **GitHub API Wrapper**: Build the GitHub API client wrapper to fetch repo stats.
