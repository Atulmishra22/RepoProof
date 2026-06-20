# AI Resume Context & Handover Note

> **ATTENTION AI AGENT**: If you are starting a new session or resuming work on this repository, **read this file first**. It contains the exact state of the project, saving token context and preventing you from having to read the entire codebase.

---

## 1. Project Identity & Architecture
*   **Project**: GitHub Repository Intelligence Platform
*   **Core Blueprint**:
    *   System Architecture: [system_architecture.md](file:///d:/cold-mail/docs/system_architecture.md)
    *   Database Schema: [database_schema.md](file:///d:/cold-mail/docs/database_schema.md)
    *   API Design: [api_design.md](file:///d:/cold-mail/docs/api_design.md)
    *   Frontend Architecture: [frontend_architecture.md](file:///d:/cold-mail/docs/frontend_architecture.md)
    *   Docker Setup: [docker_architecture.md](file:///d:/cold-mail/docs/docker_architecture.md)
    *   Queue Design: [queue_worker_design.md](file:///d:/cold-mail/docs/queue_worker_design.md)
    *   Storage Design: [storage_design.md](file:///d:/cold-mail/docs/storage_design.md)
    *   Observability: [observability_design.md](file:///d:/cold-mail/docs/observability_design.md)
    *   Roadmap: [implementation_roadmap.md](file:///d:/cold-mail/docs/implementation_roadmap.md)

---

## 2. Current Status
*   **Current Phase**: Phase 1: Foundation
*   **Checklist State**: Located at [checklist.md](file:///d:/cold-mail/docs/checklist.md) (All items currently pending).
*   **Last Action Taken**: Created all architectural design documents and checklist files. Configured local Docker installation approach (Docker Engine inside WSL2 Ubuntu without Docker Desktop).
*   **Runtime Logs & Errors**: Tracked in [error_context.md](file:///d:/cold-mail/docs/error_context.md).

---

## 3. Handover Instruction: Where to Resume
When the user gives the command to resume, you must execute **Phase 1: Foundation** tasks in order:
1.  **Verify WSL2 Docker**: Ask the user if Docker is installed and running in WSL2 Ubuntu (`docker ps` check).
2.  **Create Project Folder Structure**:
    *   `/backend`
    *   `/frontend`
3.  **Write Foundation Files**:
    *   `/backend/requirements.txt` (FastAPI, uvicorn, celery, redis, sqlalchemy, alembic, pgvector, pydantic, langgraph).
    *   `/docker-compose.yml` (Configuring Postgres 16, Redis 7, MinIO, LiteLLM, Langfuse).
4.  **Alembic Setup**: Initialize database migration scripts.
