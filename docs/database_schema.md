# DOCUMENT 2: DATABASE SCHEMA

This document describes the database design for the GitHub Repository Intelligence Platform. The schema is optimized for PostgreSQL 16 with the `pgvector` extension. All tables use UUIDs for primary keys, maintain audit timestamps, explicitly document column purposes via SQL comments, and enforce clear referential integrity rules.

---

## Database Namespace Separation & Normalization Trade-offs

To prevent schema conflicts and isolate concerns between our FastAPI backend and the Prisma-based Langfuse analytics dashboard, we separated their databases:
1. **`repo_intel` Database**: Used by the FastAPI backend for application entities (`users`, `repositories`, `analysis_jobs`, etc.).
2. **`langfuse` Database**: Used exclusively by the Langfuse telemetry server.

### Dual User Tables & Normalization Rationale
Because these databases are physically separate, a user record exists in two places:
- `langfuse.users` (managed by Langfuse using text-based IDs to track dashboard admin access).
- `repo_intel.users` (managed by the FastAPI application using UUID constraints to track repository ownership).

While this duplicates user records, it is an intentional architectural trade-off to:
- **Prevent Schema Conflicts**: Langfuse's internal Prisma migrations could otherwise modify table structures (e.g. changing user ID constraints), breaking backend foreign keys.
- **Ensure Loose Coupling**: FastAPI's domain entities and Alembic migrations remain completely independent of the telemetry subsystem's lifecycle.
- **Isolate Data Boundaries**: Telemetry and application logs are kept distinct from primary transactional user databases.

---

## Database Enums

Before defining tables, the following custom enum types are registered:

```sql
CREATE TYPE subscription_tier_enum AS ENUM ('free', 'pro');
CREATE TYPE analysis_status_enum AS ENUM ('pending', 'analyzing', 'awaiting_review', 'generating', 'complete', 'failed');
CREATE TYPE job_status_enum AS ENUM ('queued', 'running', 'interrupted', 'complete', 'failed', 'timed_out');
CREATE TYPE fact_type_enum AS ENUM ('technology_used', 'pattern_detected', 'metric', 'architecture', 'dependency');
CREATE TYPE review_status_enum AS ENUM ('pending', 'approved', 'rejected', 'edited', 'timed_out');
CREATE TYPE output_type_enum AS ENUM ('resume_bullets', 'linkedin_desc', 'readme', 'portfolio_doc');
CREATE TYPE download_format_enum AS ENUM ('txt', 'md', 'pdf', 'json');
```

---

## Tables Design

### 1. `users`
This table stores user identities, authentication references, subscription limits, and account lifecycle states. It acts as the anchor table for resource ownership in the application.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    github_username VARCHAR(100) NULL,
    auth_provider VARCHAR(50) NOT NULL,
    subscription_tier subscription_tier_enum NOT NULL DEFAULT 'free',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS 'Primary user account table containing credentials, subscription tiers, and login tracking.';
COMMENT ON COLUMN users.id IS 'Primary key UUID for user uniqueness.';
COMMENT ON COLUMN users.email IS 'Unique email used for sign-in and communication.';
COMMENT ON COLUMN users.github_username IS 'Nullable GitHub username associated via OAuth connection.';
COMMENT ON COLUMN users.auth_provider IS 'Identity provider used (e.g., github, google, credentials).';
COMMENT ON COLUMN users.subscription_tier IS 'Determines LLM usage limits and premium feature accesses.';
COMMENT ON COLUMN users.is_active IS 'Flag for soft-ban or account suspension.';
COMMENT ON COLUMN users.last_login_at IS 'Timestamp tracking user activity for session invalidation.';
COMMENT ON COLUMN users.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN users.updated_at IS 'Record last update timestamp.';
```

---

### 2. `repositories`
This table represents GitHub repositories submitted by users for parsing. It tracks aggregate repository metadata fetched from the GitHub API and holds the cumulative analysis state.

```sql
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    github_url VARCHAR(2048) NOT NULL,
    github_repo_id BIGINT NOT NULL,
    owner VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    primary_language VARCHAR(50) NULL,
    languages JSONB NOT NULL DEFAULT '{}'::jsonb,
    star_count INTEGER NOT NULL DEFAULT 0,
    last_commit_at TIMESTAMP WITH TIME ZONE NULL,
    analysis_status analysis_status_enum NOT NULL DEFAULT 'pending',
    last_analyzed_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_repositories_user_id FOREIGN KEY (user_id) 
        REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON TABLE repositories IS 'Analyzed repository metadata synced from the GitHub API.';
COMMENT ON COLUMN repositories.id IS 'Primary key UUID for repository records.';
COMMENT ON COLUMN repositories.user_id IS 'Owner of this repository record. Cascade deletes repository when user is removed.';
COMMENT ON COLUMN repositories.github_url IS 'Full public HTTP repository URL.';
COMMENT ON COLUMN repositories.github_repo_id IS 'Unique repository ID generated by GitHub’s API to identify renamed repos.';
COMMENT ON COLUMN repositories.owner IS 'Organization or user name owning the repo.';
COMMENT ON COLUMN repositories.name IS 'Name of the repository.';
COMMENT ON COLUMN repositories.default_branch IS 'Active default branch (e.g., main or master) used for file pulling.';
COMMENT ON COLUMN repositories.primary_language IS 'Primary language of the repo as detected by GitHub.';
COMMENT ON COLUMN repositories.languages IS 'JSON map of all languages used and their byte count (from GitHub API).';
COMMENT ON COLUMN repositories.star_count IS 'Popularity metric of the repo to weigh project complexity.';
COMMENT ON COLUMN repositories.last_commit_at IS 'Repository staleness indicator used to check if re-indexing is needed.';
COMMENT ON COLUMN repositories.analysis_status IS 'Aggregated user-facing status representing the state of the active analysis.';
COMMENT ON COLUMN repositories.last_analyzed_at IS 'Timestamp of the latest completed execution run.';
```
*   **FK Justification**: `user_id` has `ON DELETE CASCADE`. If a user deletes their profile, all their ingested repositories must be purged to respect privacy and storage boundaries.

---

### 3. `analysis_jobs`
This table tracks background execution states of the LangGraph orchestrator engine run inside Celery. It measures computational duration, traces errors, and tracks token consumption.

```sql
CREATE TABLE analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL,
    user_id UUID NOT NULL,
    celery_task_id UUID NULL,
    langgraph_thread_id UUID NOT NULL,
    status job_status_enum NOT NULL DEFAULT 'queued',
    current_node VARCHAR(100) NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    started_at TIMESTAMP WITH TIME ZONE NULL,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    llm_tokens_used INTEGER NOT NULL DEFAULT 0,
    llm_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.000000,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_analysis_jobs_repository_id FOREIGN KEY (repository_id)
        REFERENCES repositories (id) ON DELETE CASCADE,
    CONSTRAINT fk_analysis_jobs_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON TABLE analysis_jobs IS 'Execution records of LangGraph pipelines dispatched via Celery.';
COMMENT ON COLUMN analysis_jobs.id IS 'Primary key UUID for the job.';
COMMENT ON COLUMN analysis_jobs.repository_id IS 'Repository being processed. Cascade deletes job records on repo removal.';
COMMENT ON COLUMN analysis_jobs.user_id IS 'Target user initiating the job. Cascade deletes job records on user deletion.';
COMMENT ON COLUMN analysis_jobs.celery_task_id IS 'Celery identifier to control, query, or terminate the OS process.';
COMMENT ON COLUMN analysis_jobs.langgraph_thread_id IS 'State key mapping the job run to the LangGraph Postgres checkpointer.';
COMMENT ON COLUMN analysis_jobs.status IS 'Job execution state. Helps UI render correct loading overlays.';
COMMENT ON COLUMN analysis_jobs.current_node IS 'Last active node in the LangGraph execution flow.';
COMMENT ON COLUMN analysis_jobs.retry_count IS 'Total retries attempted across LLM wrapper transient failures.';
COMMENT ON COLUMN analysis_jobs.error_message IS 'Raw stack trace or structured error description on execution failure.';
COMMENT ON COLUMN analysis_jobs.started_at IS 'Timestamp marking when the Celery task started execution.';
COMMENT ON COLUMN analysis_jobs.completed_at IS 'Timestamp marking when job concluded (failed or completed).';
COMMENT ON COLUMN analysis_jobs.llm_tokens_used IS 'Sum of prompt and completion tokens used throughout this job.';
COMMENT ON COLUMN analysis_jobs.llm_cost_usd IS 'Calculated dollar cost of the run based on model token pricing metrics.';
```
*   **FK Justification**: `repository_id` and `user_id` both use `ON DELETE CASCADE`. If a repository is removed, its analysis history has no context and should be cleared.

---

### 4. `code_facts`
This table stores the factual technical data points extracted by the LLM from source code and README configurations. These claims must be verified by the user in the HiTL loop.

```sql
CREATE TABLE code_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_job_id UUID NOT NULL,
    fact_type fact_type_enum NOT NULL,
    fact_text TEXT NOT NULL,
    evidence_file_path VARCHAR(2048) NOT NULL,
    evidence_line_start INTEGER NOT NULL,
    evidence_line_end INTEGER NOT NULL,
    evidence_snippet TEXT NOT NULL,
    confidence_score NUMERIC(3, 2) NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    is_validated BOOLEAN NOT NULL DEFAULT FALSE,
    is_human_approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_code_facts_analysis_job_id FOREIGN KEY (analysis_job_id)
        REFERENCES analysis_jobs (id) ON DELETE CASCADE
);

COMMENT ON TABLE code_facts IS 'Granular, source-cited facts extracted by LLMs from the analyzed repository.';
COMMENT ON COLUMN code_facts.id IS 'Primary key UUID for the code fact.';
COMMENT ON COLUMN code_facts.analysis_job_id IS 'Analysis job that generated this fact. Cascade deletes facts when job is removed.';
COMMENT ON COLUMN code_facts.fact_type IS 'Category of technical information (e.g. library dependency vs. algorithm choice).';
COMMENT ON COLUMN code_facts.fact_text IS 'Plain-text natural language statement describing the technical implementation.';
COMMENT ON COLUMN code_facts.evidence_file_path IS 'Repository relative path showing where the code resides.';
COMMENT ON COLUMN code_facts.evidence_line_start IS '1-indexed start line number in the source file.';
COMMENT ON COLUMN code_facts.evidence_line_end IS '1-indexed end line number in the source file.';
COMMENT ON COLUMN code_facts.evidence_snippet IS 'The exact line(s) of source code extracted to substantiate the claim.';
COMMENT ON COLUMN code_facts.confidence_score IS 'LLM output rating describing structural certainty of the fact.';
COMMENT ON COLUMN code_facts.is_validated IS 'True if rule-based static syntax/file checks passed.';
COMMENT ON COLUMN code_facts.is_human_approved IS 'True if user has explicitly checked and approved this fact in the review UI.';
```
*   **FK Justification**: `analysis_job_id` uses `ON DELETE CASCADE`. If an analysis job is deleted, all corresponding facts should be removed to free up space.

---

### 5. `fact_embeddings`
This table stores the vector embeddings of approved facts. It uses `pgvector` to enable semantic retrieval when compiling resume bullets or portfolio sections.

```sql
-- Ensure pgvector extension is installed
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE fact_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_fact_id UUID NOT NULL UNIQUE,
    embedding VECTOR(768) NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_fact_embeddings_code_fact_id FOREIGN KEY (code_fact_id)
        REFERENCES code_facts (id) ON DELETE CASCADE
);

COMMENT ON TABLE fact_embeddings IS 'Vector coordinates of code facts to enable semantic semantic lookup during document compilation.';
COMMENT ON COLUMN fact_embeddings.id IS 'Primary key UUID.';
COMMENT ON COLUMN fact_embeddings.code_fact_id IS 'Linked code fact. Unique constraint enforces 1:1 mapping. Cascade deletes on fact removal.';
COMMENT ON COLUMN fact_embeddings.embedding IS '768-dimensional float coordinate array representing the semantic value.';
COMMENT ON COLUMN fact_embeddings.model_used IS 'Name of embedding model used (e.g., sentence-transformers/all-MiniLM-L6-v2).';
```
*   **FK Justification**: `code_fact_id` is unique and uses `ON DELETE CASCADE`. If a fact is deleted, its vector embedding is useless and should be removed.

---

### 6. `human_reviews`
This table captures the state and historical payloads of the Human-In-The-Loop interrupt process. It keeps track of original and modified snapshots.

```sql
CREATE TABLE human_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_job_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status review_status_enum NOT NULL DEFAULT 'pending',
    decision_at TIMESTAMP WITH TIME ZONE NULL,
    original_facts JSONB NOT NULL,
    approved_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    edited_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    rejection_reason TEXT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_human_reviews_analysis_job_id FOREIGN KEY (analysis_job_id)
        REFERENCES analysis_jobs (id) ON DELETE CASCADE,
    CONSTRAINT fk_human_reviews_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON TABLE human_reviews IS 'Audits of the Human-In-The-Loop flow capturing user edits, approvals, and actions.';
COMMENT ON COLUMN human_reviews.id IS 'Primary key UUID.';
COMMENT ON COLUMN human_reviews.analysis_job_id IS 'Linked execution run. Cascade deletes review records if job is deleted.';
COMMENT ON COLUMN human_reviews.user_id IS 'User performing the review. Cascade deletes review records on user deletion.';
COMMENT ON COLUMN human_reviews.status IS 'Current status of the review (pending, approved, rejected, edited, timed_out).';
COMMENT ON COLUMN human_reviews.decision_at IS 'When user clicked confirm or cancel on this batch.';
COMMENT ON COLUMN human_reviews.original_facts IS 'JSON snapshot of all facts initially generated by the extraction node.';
COMMENT ON COLUMN human_reviews.approved_facts IS 'JSON array containing facts approved without adjustments.';
COMMENT ON COLUMN human_reviews.edited_facts IS 'JSON array containing facts modified by the user during the review.';
COMMENT ON COLUMN human_reviews.rejection_reason IS 'Nullable user input detailing why a run was rejected.';
COMMENT ON COLUMN human_reviews.expires_at IS 'Staleness timestamp. Triggers automated cron cleanup.';
```
*   **FK Justification**: Cascade relationships ensure that deleting user profiles or jobs immediately clears associated pending/completed review metadata.

---

### 7. `generated_outputs`
This table hosts finalized outputs (resumes, portfolios, LinkedIn descriptions) created by the downstream LLM compilation nodes from approved facts.

```sql
CREATE TABLE generated_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_job_id UUID NOT NULL,
    output_type output_type_enum NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_current_version BOOLEAN NOT NULL DEFAULT TRUE,
    llm_model_used VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    generation_duration_ms INTEGER NOT NULL DEFAULT 0,
    minio_object_key VARCHAR(1024) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_generated_outputs_analysis_job_id FOREIGN KEY (analysis_job_id)
        REFERENCES analysis_jobs (id) ON DELETE CASCADE
);

COMMENT ON TABLE generated_outputs IS 'Generated resumes, readmes, and profiles derived from verified repository facts.';
COMMENT ON COLUMN generated_outputs.id IS 'Primary key UUID.';
COMMENT ON COLUMN generated_outputs.analysis_job_id IS 'Job run that generated this text output. Cascade deletes on job removal.';
COMMENT ON COLUMN generated_outputs.output_type IS 'Format target (e.g. resume bullet list, markdown readme).';
COMMENT ON COLUMN generated_outputs.content IS 'The actual string text output generated.';
COMMENT ON COLUMN generated_outputs.version IS 'Incremental counter tracking revision counts of the outputs.';
COMMENT ON COLUMN generated_outputs.is_current_version IS 'Boolean flag indicating which version is active/visible.';
COMMENT ON COLUMN generated_outputs.llm_model_used IS 'LLM model descriptor used for tracing and cost tracking.';
COMMENT ON COLUMN generated_outputs.prompt_tokens IS 'Tokens sent in input.';
COMMENT ON COLUMN generated_outputs.completion_tokens IS 'Tokens generated in output.';
COMMENT ON COLUMN generated_outputs.generation_duration_ms IS 'Time taken for the generation API call to complete.';
COMMENT ON COLUMN generated_outputs.minio_object_key IS 'Cloudflare R2 storage path for file retrieval.';
```
*   **FK Justification**: Cascade behavior keeps output files in sync with jobs. If a job is deleted, the generated database records are removed.

---

### 8. `output_downloads`
This table captures auditing logs detailing every instance a user downloads one of their compiled artifacts.

```sql
CREATE TABLE output_downloads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id UUID NOT NULL,
    user_id UUID NOT NULL,
    format download_format_enum NOT NULL,
    downloaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    presigned_url_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_output_downloads_output_id FOREIGN KEY (output_id)
        REFERENCES generated_outputs (id) ON DELETE CASCADE,
    CONSTRAINT fk_output_downloads_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON TABLE output_downloads IS 'Access audit trail logging user download actions and presigned URL properties.';
COMMENT ON COLUMN output_downloads.id IS 'Primary key UUID.';
COMMENT ON COLUMN output_downloads.output_id IS 'Reference to the downloaded generated file record. Cascade deletes on output removal.';
COMMENT ON COLUMN output_downloads.user_id IS 'User requesting download. Cascade deletes download logs on user deletion.';
COMMENT ON COLUMN output_downloads.format IS 'Downloaded format (txt, md, pdf, or json).';
COMMENT ON COLUMN output_downloads.downloaded_at IS 'Exact access timestamp.';
COMMENT ON COLUMN output_downloads.presigned_url_expires_at IS 'Expiration timestamp for the presigned storage download URL.';
```
*   **FK Justification**: CASCADE guarantees referential cleanliness. Removing a user profile cleans up access log tracking data.

---

### 9. `usage_metrics`
This table aggregates daily computational statistics for monitoring and billing.

```sql
CREATE TABLE usage_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    date DATE NOT NULL,
    llm_provider VARCHAR(100) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.000000,
    analysis_count INTEGER NOT NULL DEFAULT 0,
    generation_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_usage_metrics_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uq_user_date_model UNIQUE (user_id, date, model_name)
);

COMMENT ON TABLE usage_metrics IS 'Daily aggregated user token and resource usage patterns for limits enforcement.';
COMMENT ON COLUMN usage_metrics.id IS 'Primary key UUID.';
COMMENT ON COLUMN usage_metrics.user_id IS 'User reference. Cascade deletes usage data on user removal.';
COMMENT ON COLUMN usage_metrics.date IS 'Target summary date.';
COMMENT ON COLUMN usage_metrics.llm_provider IS 'Hosting API name (e.g. Groq, Gemini).';
COMMENT ON COLUMN usage_metrics.model_name IS 'Model name identifier (e.g. gemini-1.5-flash).';
COMMENT ON COLUMN usage_metrics.total_tokens IS 'Total tokens consumed on this date/model combination.';
COMMENT ON COLUMN usage_metrics.total_cost_usd IS 'Calculated dollar cost.';
COMMENT ON COLUMN usage_metrics.analysis_count IS 'Completed repository parsing jobs.';
COMMENT ON COLUMN usage_metrics.generation_count IS 'Completed output generation files.';
```
*   **FK Justification**: CASCADE cleans up tracking summaries if the parent user account is terminated.

---

### 10. `system_events`
This table logs security-sensitive actions and job transitions. It is designed to be append-only.

```sql
CREATE TABLE system_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE system_events IS 'Immutable, append-only security auditing log capturing system events.';
COMMENT ON COLUMN system_events.id IS 'Primary key UUID.';
COMMENT ON COLUMN system_events.entity_type IS 'Target database table reference (e.g. users, analysis_jobs).';
COMMENT ON COLUMN system_events.entity_id IS 'Target record primary key UUID.';
COMMENT ON COLUMN system_events.event_type IS 'Action type name (e.g., job_failed, tier_upgraded, user_authenticated).';
COMMENT ON COLUMN system_events.payload IS 'Context JSON payload.';
COMMENT ON COLUMN system_events.created_at IS 'Log capture timestamp.';
```
*   **Constraint Design**: This table has no Foreign Key checks or triggers. This decouples event-logging from resource deletions, maintaining an immutable security trail even after a user is deleted (referencing the historical user UUID without breaking).

---

## Database Indexes

```sql
-- Users
CREATE INDEX idx_users_email ON users(email);

-- Repositories
CREATE INDEX idx_repositories_user_id ON repositories(user_id);
CREATE INDEX idx_repositories_status ON repositories(analysis_status);

-- Analysis Jobs
CREATE INDEX idx_analysis_jobs_repo_id ON analysis_jobs(repository_id);
CREATE INDEX idx_analysis_jobs_user_id ON analysis_jobs(user_id);
CREATE INDEX idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX idx_analysis_jobs_thread_id ON analysis_jobs(langgraph_thread_id);

-- Code Facts
CREATE INDEX idx_code_facts_job_id ON code_facts(analysis_job_id);
CREATE INDEX idx_code_facts_validated_approved ON code_facts(is_validated, is_human_approved);

-- Human Reviews
CREATE INDEX idx_human_reviews_job_id ON human_reviews(analysis_job_id);
CREATE INDEX idx_human_reviews_status ON human_reviews(status);
CREATE INDEX idx_human_reviews_expires ON human_reviews(expires_at) WHERE status = 'pending';

-- Generated Outputs
CREATE INDEX idx_generated_outputs_job_id ON generated_outputs(analysis_job_id);

-- System Events
CREATE INDEX idx_system_events_entity ON system_events(entity_type, entity_id);
```

### Index Justification:
*   `idx_users_email`: Used for email lookup during authentication.
*   `idx_repositories_user_id` & `idx_analysis_jobs_user_id`: Essential for loading user dashboard tables.
*   `idx_analysis_jobs_thread_id`: Critical for retrieving state checkpoints during LangGraph resume requests.
*   `idx_code_facts_job_id` & `idx_generated_outputs_job_id`: Speeds up joins when retrieving extracted facts and outputs on repository pages.
*   `idx_human_reviews_expires`: Filtered index optimizing the hourly cron job sweep (`expire_stale_reviews`) by ignoring resolved review records.

---

## Vector Search Design & pgvector Indexing

### Vector Index Configuration
For semantic similarity retrieval over extracted code facts, we index the `fact_embeddings` table.

```sql
-- Create HNSW index on the embedding vector using Cosine Similarity
CREATE INDEX idx_fact_embeddings_hnsw ON fact_embeddings 
USING hnsw (embedding vector_cosine_ops);
```

#### Why HNSW over IVFFlat?
1.  **Recall Accuracy**: Hierarchical Navigable Small World (HNSW) graphs maintain high query recall accuracy (typically >95%) even as search datasets grow.
2.  **No Training Phase Required**: IVFFlat requires a training step with a pre-existing dataset to cluster data points into lists before it can be queried. If the index isn't retrained, search quality degrades. HNSW is build-and-go; it adapts as data points are incrementally added.
3.  **Low Latency**: HNSW query speeds are extremely fast. While HNSW requires more RAM (to store the proximity graph) and takes longer to build, it is perfect for this project's scale, where search latency is critical and the dataset size fits comfortably within the Supabase free tier RAM limit.

---

### Similarity Search SQL Query
During downstream resume and portfolio generation, the backend retrieves facts that match the target job description. The following query performs a Cosine Distance lookup (`<=>` operator):

```sql
CREATE OR REPLACE FUNCTION match_code_facts(
    query_embedding VECTOR(768),
    match_threshold FLOAT,
    match_limit INTEGER,
    target_user_id UUID
)
RETURNS TABLE (
    fact_id UUID,
    fact_text TEXT,
    evidence_file_path VARCHAR(2048),
    evidence_snippet TEXT,
    similarity FLOAT
) 
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cf.id AS fact_id,
        cf.fact_text,
        cf.evidence_file_path,
        cf.evidence_snippet,
        (1 - (fe.embedding <=> query_embedding)) AS similarity
    FROM fact_embeddings fe
    JOIN code_facts cf ON fe.code_fact_id = cf.id
    JOIN analysis_jobs aj ON cf.analysis_job_id = aj.id
    WHERE aj.user_id = target_user_id
      AND cf.is_human_approved = TRUE
      AND (1 - (fe.embedding <=> query_embedding)) > match_threshold
    ORDER BY fe.embedding <=> query_embedding ASC
    LIMIT match_limit;
END;
$$;
```

#### SQL Query Logic:
1.  Filters results to only return **approved** facts (`is_human_approved = TRUE`) belonging to the requesting user (`aj.user_id = target_user_id`).
2.  Uses the cosine distance operator (`<=>`) to sort records.
3.  Computes similarity as `1 - Cosine Distance`.
4.  Filters out results below the similarity threshold to keep the context payload clean.
