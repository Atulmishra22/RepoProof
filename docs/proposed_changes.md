# Proposed Changes — Principal Engineer Review
**Date**: 2026-06-22
**Source**: Architecture review session — covers security, caching, data isolation, AI pipeline, and production readiness.
**Status**: Phase 8A (Security + UX) and Phase 8B (RQS Scoring & Recommendations) are IMPLEMENTED.

> [!IMPORTANT]
> **Agent Startup Rule**: Before implementing ANY feature or fix, read this file top to bottom.
> Then cross-reference `docs/database_schema.md`, `docs/system_architecture.md`, and
> `docs/implementation_roadmap.md` to understand the full intended design.
> These proposed changes take priority over continuing previous work.

---

## Priority Legend
- CRITICAL — Security vulnerability or UX blocker. Implement first.
- HIGH — Architectural correctness. Implement in Phase 8.
- MEDIUM — Production readiness. Implement in Phase 9.
- LEARNING/FUTURE — Document for awareness, implement later.

---

## CRITICAL: Security — Private Repo Data Isolation

### Change 1: Add is_private column to Repository model
**File**: backend/app/models.py
**Why**: No way to distinguish public from private repos in DB. OAuth user's private repos can leak to other users via the cache reuse query on line 54 of tasks.py.

`python
is_private: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="false",
    comment="True if GitHub marked this repo private. Private repos are never shared across users."
)
`
**Migration required**: alembic revision --autogenerate -m "add_is_private_to_repositories"

---

### Change 2: Fix the shared cache reuse query in tasks.py
**File**: backend/app/tasks.py line 54
**Why**: Current query fetches ALL repos for a GitHub owner regardless of user_id. If User A (OAuth) stored private repos, User B picks them up — data leak.

`python
# BEFORE (buggy):
existing_repos = db.query(Repository).filter(Repository.owner == username).all()

# AFTER (safe):
existing_repos = db.query(Repository).filter(
    Repository.owner == username,
    Repository.is_private == False  # CRITICAL filter
).all()
`

---

### Change 3: Store is_private flag when ingesting repos
**File**: backend/app/tasks.py — repo upsert loop
**Why**: GitHub API returns "private": true/false per repo. Must be stored.

`python
repo = Repository(
    user_id=user.id,
    is_private=repo_data.get("private", False),
    ...
)
`

---

### Change 4: Split repositories endpoint into public + private
**File**: backend/app/main.py
**Why**: Single GET /repositories cannot safely serve both without ownership check.

`
GET /api/v1/repos/{username}/public   — No ownership required, public repos
GET /api/v1/repos/{username}/private  — Guard required, owner only
`

---

### Change 5: Implement verify_github_ownership guard dependency
**File**: backend/app/main.py
**Why**: FastAPI Dependency that runs BEFORE endpoint body. If any check fails, 403 returned and endpoint never runs.

`python
async def verify_github_ownership(username: str, current_user: User = Depends(get_current_user)) -> User:
    if current_user.auth_provider != "github":
        raise HTTPException(403, "Private repos require GitHub OAuth login")
    if current_user.github_username != username:
        raise HTTPException(403, "You are not the verified owner of this GitHub account")
    account = db.query(Account).filter(Account.user_id == current_user.id, Account.provider == "github").first()
    if not account or not account.access_token:
        raise HTTPException(403, "GitHub OAuth token missing or expired. Please re-login.")
    return current_user
`

---

### Change 6: Smart 3-Level Cache Architecture
**Why**: Cache stores METADATA (flags) not private data. Redis = public only. Private = PostgreSQL only.

`
LEVEL 1 — META cache (Redis, shared, safe):
  Key:   github_meta:{username}
  Data:  { has_public: true, has_private: true, profile_cached: true }
  TTL:   24 hours

LEVEL 2 — PUBLIC repos cache (Redis, shared, safe):
  Key:   github_public_repos:{username}
  Data:  list of public repos
  TTL:   24 hours

LEVEL 3 — PRIVATE repos (PostgreSQL ONLY, NEVER Redis):
  Table: repositories WHERE is_private=True AND user_id={owner.id}
  No TTL — persistent, user controls deletion
`

CAUTION: Never create a Redis key for private repo data. Redis has no per-key access control.
If port 6379 is accidentally exposed, any key is readable via redis-cli with no auth.
See the Redis Security learning note at the bottom.

---

## CRITICAL: UX Blocker — Hardcoded Username

### Change 7: Remove hardcoded "Atulmishra22" fallback
**File**: backend/app/main.py line 255

`python
# BEFORE (broken — any user without github_username sees Atulmishra22 data):
target_username = current_user.github_username or username or "Atulmishra22"

# AFTER (correct):
target_username = current_user.github_username or username
if not target_username:
    return { "repositories": [], "profile": None, "onboarding_required": True }
`

---

### Change 8: Add onboarding_required flag to API response
**File**: backend/app/main.py — GET /repositories
**Why**: Frontend needs a flag to show onboarding screen instead of blank dashboard.

`python
return {
    "repositories": [], "profile": None,
    "onboarding_required": True,
    "message": "Connect your GitHub account or enter a GitHub username to get started."
}
`

---

### Change 9: Add onboarding screen in frontend dashboard
**File**: frontend/src/app/dashboard/page.tsx
**Why**: First-time users see blank/broken dashboard. Need clear call to action.

If API returns onboarding_required: true
  -> Show "Welcome to RepoProof"
  -> Input: "Enter a GitHub username to analyze"
  -> OR Button: "Connect GitHub Account" -> OAuth redirect

---

## HIGH: Change Detection — No Token Burn on Unchanged Repos

### Change 10: Check last_commit_at before re-analyzing
**File**: backend/app/main.py — POST /repositories/{id}/analyze
**Why**: Every Analyze click burns full LLM tokens even if repo hasnt changed.

`python
if repo.last_analyzed_at and repo.last_commit_at:
    if repo.last_commit_at <= repo.last_analyzed_at:
        return {
            "status": "cached",
            "message": "Repository unchanged since last analysis. Serving existing results.",
            "job_id": latest_job_id
        }
`

Frontend: Show "No new commits detected" with "Force re-analyze" option.

---

## HIGH: Multi-Repo Resume (Core Feature Gap)

### Change 11: Add impact_score to Repository model
**File**: backend/app/models.py

`python
impact_score: Mapped[Optional[float]] = mapped_column(
    Numeric(5, 2), nullable=True,
    comment="Score 0-10 used to rank repos for multi-repo resume selection."
)
`

Scoring heuristic (no LLM needed):
  +2.0 pts: star count (capped)
  +2.0 pts: last commit within 6 months (recency)
  +0.3 pts per language (complexity)
  +1.5 pts: has tests
  +1.5 pts: has CI/CD (.github/workflows)
  +1.0 pts: README > 500 chars

---

### Change 12: Multi-repo resume endpoint + merge_facts LangGraph node
**Files**: backend/app/main.py, backend/app/analysis_graph.py

New endpoint: POST /api/v1/users/me/resume
Payload: { "repo_ids": ["uuid1", "uuid2", "uuid3"] }

New LangGraph node: merge_facts_node
  - Takes approved facts from N repos
  - Deduplicates overlapping skills
  - Enforces 1-page constraint (1500 word budget)
  - Generates unified narrative across all repos

Frontend flow:
  Dashboard -> "Build Resume" button
  -> Show all analyzed repos with impact_score ratings
  -> AI recommends top 3 with explanation
  -> User drag/drop reorder or swap
  -> Confirm -> trigger multi-repo pipeline

---

## MEDIUM: Close Design-Implementation Gap

These were designed in docs/ but never implemented in code.

### Change 13: code_facts as proper DB table (not JSONB blob)
Facts currently stored in LangGraph state as JSONB. Move to proper code_facts rows.
Reference: docs/database_schema.md Section 4.

### Change 14: fact_embeddings table + pgvector
Reference: docs/database_schema.md Section 5.
After HITL approval, embed each fact using sentence-transformers/all-MiniLM-L6-v2 (free, local).
Store in fact_embeddings with HNSW index. Use during generation for semantic retrieval.

`sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE fact_embeddings (
    id UUID PRIMARY KEY, code_fact_id UUID NOT NULL UNIQUE,
    embedding VECTOR(768) NOT NULL, model_used VARCHAR(100) NOT NULL, ...
);
CREATE INDEX idx_fact_embeddings_hnsw ON fact_embeddings USING hnsw (embedding vector_cosine_ops);
`

### Change 15: user_preferences table + reflection pipeline
Reference: docs/system_architecture.md Section 1.8.
After HITL: background Celery task compares original vs edited facts.
LLM extracts preference rules, stored per user, injected into next analysis prompt.

### Change 16: GraphRAG pruned context retrieval
Reference: docs/system_architecture.md Section 1.9.
Build project dependency graph. Fetch only minimum relevant files for LLM context.
Token reduction: 60-80%.

### Change 17: Clarification gate before document generation
Reference: docs/system_architecture.md Section 1.10.
check_missing_context node validates contact info and target role exist before generating.
If missing, interrupt -> present questionnaire to user -> resume after response.

---

## MEDIUM: Production Observability

### Change 18: Prometheus /metrics endpoint
**File**: backend/app/main.py
One install: prometheus-fastapi-instrumentator. Implement all 9 metrics from docs/observability_design.md.

`python
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)
`

### Change 19: Replace logging with structlog (JSON logs)
Replace all logger = logging.getLogger() calls with structlog.
Output: JSON with trace_id, user_id, job_id on every line.
Reference: docs/observability_design.md Section 7.3.

### Change 20: Add Correlation ID middleware
**File**: backend/app/main.py
Every request gets UUID that travels: FastAPI -> Celery args -> LangGraph state -> Langfuse trace.

`python
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    # Bind to context var, pass to all downstream tasks
`

---

## LEARNING: Redis Security (Do Not Implement Now — Learn the Concept)

In current Docker setup, Redis is exposed on port 6379 with no password.
Any machine on the same network can connect directly, bypassing FastAPI entirely:

`ash
# Direct Redis attack — bypasses ALL FastAPI guards:
redis-cli -h localhost -p 6379
KEYS *                              # enumerate all cached keys
GET "github_profile:Atulmishra22"   # read any key, no auth required
`

This is why private data must never be stored in Redis regardless of endpoint guards.
The endpoint guard protects the API path. The "no private data in Redis" rule protects
against direct Redis access — two separate attack surfaces.

How to secure Redis for production:
`
requirepass strong_password_here   # in redis.conf
bind 127.0.0.1                     # refuse external connections
protected-mode yes
# In docker-compose: use expose: [6379] NOT ports: ["6379:6379"]
`

Implement this before any cloud deployment.

---

## Implementation Order for the Agent

PHASE 8A — Security + UX (implement first):
  [x] Change 1:  Add is_private to Repository model + migration
  [x] Change 2:  Fix cache reuse query (is_private=False filter)
  [x] Change 3:  Store is_private from GitHub API response
  [x] Change 4:  Split repositories into public/private endpoints
  [x] Change 5:  Implement verify_github_ownership guard
  [x] Change 6:  Implement 3-level cache with meta key in ingestion task
  [x] Change 7:  Remove hardcoded Atulmishra22 fallback
  [x] Change 8:  Add onboarding_required to API response
  [x] Change 9:  Add onboarding screen in frontend dashboard
  [x] Change 10: Add change detection (last_commit_at check before analysis)

PHASE 8B — Core Feature (RQS Recommendation):
  [x] Change 11: Add RQS score dynamically using async git tree walks + cache in Redis
  [x] Change 12: Pre-checked repository grids, selection rules (max 3), and batch analysis

PHASE 9 — Close Design Gap:
  [ ] Change 13: code_facts as proper DB table
  [ ] Change 14: fact_embeddings + pgvector
  [ ] Change 15: user_preferences + reflection pipeline
  [ ] Change 16: GraphRAG pruned context
  [ ] Change 17: Clarification gate

PHASE 10 — Observability:
  [ ] Change 18: Prometheus /metrics endpoint
  [ ] Change 19: structlog JSON structured logs
  [ ] Change 20: Correlation ID middleware

FUTURE (post-deployment):
  [ ] Redis password + private network
  [ ] GitHub webhooks for auto last_commit_at update (OAuth users)
  [ ] GitHub App for better webhook management
