# DOCUMENT 1: SYSTEM ARCHITECTURE

## 1.1 Functional Requirements

*   **GitHub URL Submission**
    *   *User Story:* As a Job Seeker, I want to paste a public GitHub repository URL into the platform so that the system can begin analyzing my project.
*   **Repository Analysis**
    *   *User Story:* As a Developer, I want the system to parse my repository’s languages, folder structure, commits, and `README.md` so that it understands the technological makeup of my project without manual entry.
*   **Fact Extraction with Citations**
    *   *User Story:* As a Job Seeker, I want the system to extract concrete technical facts (e.g., "Implemented JWT auth", "Configured Redis cache") from the code and cite the exact file paths and line numbers so that my resume claims are fully verifiable.
*   **Human-In-The-Loop (HiTL) Fact Review**
    *   *User Story:* As a Job Seeker, I want to review, edit, approve, or reject the extracted facts before they are used to write copy, so that I can prevent AI hallucinations and keep my resume 100% accurate.
*   **Content Generation**
    *   *User Story:* As an Applicant, I want the system to generate ATS-friendly resume bullet points, a LinkedIn project description, a polished README, and portfolio documentation from my approved facts, so that I can market my project across multiple platforms.
*   **Output Versioning**
    *   *User Story:* As an Applicant, I want to edit facts and regenerate my outputs, maintaining a history of previous versions, so that I can compare designs and target different job descriptions.
*   **User History & Dashboard**
    *   *User Story:* As a returning User, I want to see a dashboard of my analyzed repositories, their analysis status, and saved outputs so that I can access them whenever I apply for a new job.
*   **Rate Limiting Per Provider**
    *   *User Story:* As a System Administrator, I want to rate-limit requests to LLM APIs based on my free-tier quotas so that the service remains available and doesn't crash due to rate limits.

---

## 1.2 Non-Functional Requirements

*   **API Latency**:
    *   **P50 (Standard request/response)**: < 150ms (fetched from cache/Postgres).
    *   **P95 (Standard request/response)**: < 500ms.
    *   *Note: Async operations (like repo analysis) are excluded from HTTP response latency targets; they return immediately with a `job_id` (latency < 100ms).*
*   **Analysis Job Duration**:
    *   **Expected duration**: 30 to 90 seconds (under normal LLM response times for factual analysis of a medium repository).
    *   **Max Hard Timeout**: 5 minutes (300 seconds) after which a Celery task is killed, and the job is marked `timed_out` in the database.
*   **Concurrency**:
    *   Maximum **1 active analysis job per user** at any time on the free tier to prevent queue starvation.
    *   Maximum **5 concurrent jobs globally** across the free Render/Railway tier.
*   **Data Retention**:
    *   In-memory repository files (temp folder cloned to worker) are deleted **immediately** after fact extraction finishes (retaining files on a free-tier worker disk is a security and storage liability).
    *   Extracted facts, user states, and generated copy are retained in Postgres indefinitely until the user deletes their account or repo entry.
*   **Error Rate Budget**:
    *   < 1% API error rate on non-LLM endpoints.
    *   LLM-related nodes in the graph must tolerate transient API failures by executing up to **3 retries** with exponential backoff before throwing a workflow error.
*   **LLM Token Usage Cap**:
    *   Max **200k tokens** per analysis run (input + output) across all LLM steps to preserve free-tier quotas on Gemini/Groq.
*   **Storage Limits**:
    *   Max **50MB** of generated markdown/text outputs stored in MinIO/R2 per user.

---

## 1.3 High-Level System Architecture Diagram

```
                                +-------------------------------------------+
                                |                BROWSER                    |
                                |       Next.js 16 App Router Client        |
                                +--------------------+----------------------+
                                                     |
                                                     | (1) HTTPS Auth / REST / GraphQL
                                                     | (2) WS (Job Events: ws://...)
                                                     v
                                +--------------------+----------------------+
                                |              NEXT.js BFF                  |
                                |     (Vercel - Serverless Edge / API)      |
                                +----+---------------+------------------+---+
                                     |               |                  |
                                     | (3) HTTP      | (4) SQL Auth     | (5) Session Cache
                                     v               v                  v
+--------------------+          +----+---------------+----+       +-----+-------------+
|    GITHUB API      | <--------+     FASTAPI BACKEND     |       |    REDIS 7        |
|  (External REST)   | (HTTP)   |  (Render Free App Node) |       | (Cache & Broker)  |
+--------------------+          +----+---------------+----+       +--+-------------+--+
                                     |               |               ^             |
                        (6) Trace    |               | (7) SQL       | (8) Publish | (9) Queue
                        Telemetry    v               v               |     WS Msg  v     Task
+--------------------+          +----+----+     +----+----+       +--+-------------+--+
|      LANGFUSE      | <--------+ LITELLM |     | SUPABASE|       |  CELERY WORKER    |
| (Self-Hosted Docker| (HTTP API|  PROXY  |     |POSTGRES |       | (Render Background|
|     on Render)     |  Client) | (Docker)|     |  (16)   |       |   Worker Node)    |
+--------------------+          +----+----+     +----+----+       +--+-------------+--+
                                     |                               |
                                     | (10) LLM requests             | (11) Executes
                                     v                               |      LangGraph Pipeline
                        +------------+------------+                  |
                        |      FREE LLM APIs      | <----------------+
                        | (Gemini, Groq, Together)|
                        +-------------------------+
                                     ^
                                     | (12) Read/Write outputs & code tree
                                     v
                        +------------+------------+
                        |     CLOUDFLARE R2       |
                        |   (S3-compatible bucket)|
                        +-------------------------+
```

### The Human-In-The-Loop (HiTL) Interrupt Flow in the Architecture:
```
[Celery Worker: node_extract_facts] 
       │
       ▼ (Workflow finishes fact extraction & validation)
[Celery Worker: node_await_human_review]
       │
       ├─► 1. Save State Checkpoint to Postgres
       ├─► 2. Publish "review_required" Event via Redis Pub/Sub ──► Next.js BFF (WS) ──► Browser
       └─► 3. Task SUSPENDS (Terminates gracefully; releases Celery worker thread)
                                                                       │
                                                       (User edits & approves facts in UI)
                                                                       │
[Celery Worker: resume_task] ◄─── 5. Trigger new Celery Task ◄─── Next.js BFF ◄─┘
       │                               (resumes with job_id & approved facts payload)
       ▼ (Workflow reads checkpoint and proceeds)
[Celery Worker: node_generate_resume_bullets]
```

---

## 1.4 Component Responsibilities

### Next.js 16 Client & BFF (Backend-for-Frontend)
*   **WHAT**: React application hosted on Vercel acting as both the presentation layer (using Tailwind CSS + shadcn/ui) and an API proxy layer (BFF) handling NextAuth.js sessions.
*   **WHY**: Next.js App Router allows server-side rendering (SSR) for landing pages (SEO optimization) while keeping the API endpoints close to the frontend for light validation, auth checks, and WebSockets session mapping.
*   **FREE**: Hosted on Vercel's free tier.
*   **LIMIT**: Severely constrained by Vercel serverless function timeouts (10s on free tier). Thus, it *cannot* do heavy operations; it must defer all GitHub ingestion and AI runs to FastAPI/Celery.

### FastAPI Backend
*   **WHAT**: High-performance ASGI Python API server serving REST endpoints, executing WebSockets handlers, and dispatching Celery tasks.
*   **WHY**: FastAPI integrates natively with Pydantic v2 (type safety/validation) and uses Python's asynchronous ecosystem, making it perfect for handling real-time WebSocket connections and quickly handing off heavy computation to Celery.
*   **FREE**: Hosted on Render.com's web service free tier.
*   **LIMIT**: Render free services spin down after 15 minutes of inactivity (causing cold starts up to 50s). In production, this would trigger load balancer timeouts.

### Celery Worker
*   **WHAT**: A distributed task consumer running on a separate Docker container, listening to Redis queues to execute the LangGraph state machine.
*   **WHY**: Analyzing a code tree and running LLM agents takes minutes. Running this on the main API thread would block server loops and timeout clients. Celery executes these operations safely in the background.
*   **FREE**: Hosted on Render.com's background worker free tier.
*   **LIMIT**: Render free workers share a restricted memory footprint (512MB RAM). Cloning large repositories directly into worker memory will cause Out-Of-Memory (OOM) crashes.

### Supabase PostgreSQL 16 (+ pgvector)
*   **WHAT**: Relational database storing user metadata, repository analytics, facts, checkpoints, and output versions. Includes `pgvector` for storing embedding coordinates of code facts.
*   **WHY**: Standardizing on Postgres gives us transaction support for version management, relational schema integrity, and semantic vector storage in a single database technology.
*   **FREE**: Supabase free tier database (500MB database limit).
*   **LIMIT**: Vector operations and indices (like HNSW) consume significant RAM. At scale, the free tier will run out of memory, causing query degradation.

### Redis 7
*   **WHAT**: In-memory data store acting as the Celery task broker, WebSocket pub/sub engine, and rate-limiting cache.
*   **WHY**: Low-latency message brokerage. Using Redis pub/sub allows the FastAPI API nodes to listen to state changes inside the worker and broadcast them immediately to the frontend.
*   **FREE**: Upstash Redis free tier (10,000 commands/day).
*   **LIMIT**: Upstash free rate limits commands. If the app has multiple clients polling or sending heavy message rates over WebSockets, the quota is quickly exhausted.

### Cloudflare R2
*   **WHAT**: S3-compatible, zero-egress-fee object storage bucket.
*   **WHY**: Storing raw repository clones or JSON representations of repository file trees directly in Postgres is expensive. Cloudflare R2 provides flat file storage with zero egress fees, which is ideal for a budget.
*   **FREE**: Cloudflare R2 free tier (10GB storage, 1M Class A operations/month).
*   **LIMIT**: File download/upload latency is higher than local storage, adding overhead during repository cloning processes.

### LiteLLM Proxy
*   **WHAT**: A lightweight, self-hosted proxy wrapper that translates OpenAI format calls to Gemini, Groq, or Together.ai APIs.
*   **WHY**: Rather than writing custom integration code for 4 different LLM client libraries, we write code for standard OpenAI calls once. LiteLLM handles fallback, routing, and usage logs.
*   **FREE**: Open-source, runs inside our Docker Compose environment alongside the FastAPI server.
*   **LIMIT**: LiteLLM adds a minor network hop latency (approx 20-50ms) to every API call.

---

## 1.5 LangGraph State Machine Design

### State Machine Diagram (ASCII)

```
       [START]
          │
          ▼
┌──────────────────────────────────┐
│   fetch_repository_metadata      │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│     clone_or_fetch_file_tree     │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│        extract_code_facts        │ (LLM Call)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│          validate_facts          │ (Regex / Rules - No LLM)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│        store_facts_to_db         │
└─────────────────┬────────────────┘
                  │
                  ▼
  [INTERRUPT: await_human_review]    <--- Execution state saved to DB.
                  │                       Task suspends.
                  │
                  ▼ (User posts approved facts to API, triggering resume)
┌──────────────────────────────────┐
│    generate_resume_bullets       │ (LLM Call)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│     generate_linkedin_desc       │ (LLM Call)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│         generate_readme          │ (LLM Call)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│      generate_portfolio_doc      │ (LLM Call)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│        store_all_outputs         │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│           notify_user            │ (Websocket / Email trigger)
└─────────────────┬────────────────┘
                  │
                  ▼
                [END]
```

### Node Specifications

1.  **`fetch_repository_metadata`**
    *   *Inputs*: `repo_url`
    *   *Outputs*: `repo_metadata`
    *   *LLM Call*: No.
    *   *Can Fail*: Yes. (e.g., repository is private, or network timeout).
    *   *Failure Behavior*: Set `error` in state, increment `retry_count`, transitions to `END`.
2.  **`clone_or_fetch_file_tree`**
    *   *Inputs*: `repo_url`
    *   *Outputs*: `file_tree` (as a structured map saved to R2, key path saved in state).
    *   *LLM Call*: No.
    *   *Can Fail*: Yes (e.g., repository is too large > 100MB).
    *   *Failure Behavior*: Abort, set `error`, transitions to `END`.
3.  **`extract_code_facts`**
    *   *Inputs*: `file_tree`, `repo_metadata`
    *   *Outputs*: `extracted_facts`
    *   *LLM Call*: Yes. Gemini 1.5 Flash. (~150,000 input tokens max context, cost: $0.00).
    *   *Can Fail*: Yes (Rate limits, token length error).
    *   *Failure Behavior*: Exponential backoff retry (up to 3 times). If hard fail, transition to `END` with error.
4.  **`validate_facts`**
    *   *Inputs*: `extracted_facts`
    *   *Outputs*: `validated_facts`
    *   *LLM Call*: No. (Uses fast, rule-based Pydantic models to assert facts contain a valid `evidence_file_path` that exists in the `file_tree`, a `confidence_score` > 0.6, and a non-empty `evidence_snippet`).
    *   *Can Fail*: No. (Failing facts are filtered out; remaining facts proceed).
5.  **`store_facts_to_db`**
    *   *Inputs*: `validated_facts`, `job_id`
    *   *Outputs*: None (writes directly to Postgres database table `code_facts`).
    *   *LLM Call*: No.
    *   *Can Fail*: Yes (DB connection error).
    *   *Failure Behavior*: Standard transactional rollback, retry database connection twice.
6.  **`await_human_review` (Interrupt Node)**
    *   *Inputs*: `validated_facts`
    *   *Outputs*: `human_approved_facts`, `human_review_status`
    *   *LLM Call*: No.
    *   *Can Fail*: No. This node acts as a passive container. The LangGraph compiler uses it as an interrupt boundary.
7.  **`generate_resume_bullets`**
    *   *Inputs*: `human_approved_facts`, `target_job_description`
    *   *Outputs*: `resume_bullets`
    *   *LLM Call*: Yes. Groq (Llama 3 70B for high-quality professional text output). (~4,000 input tokens. Cost: $0.00).
    *   *Can Fail*: Yes.
    *   *Failure Behavior*: Retry up to 3 times, write error to state on total failure.
8.  **`generate_linkedin_desc`**
    *   *Inputs*: `human_approved_facts`
    *   *Outputs*: `linkedin_desc`
    *   *LLM Call*: Yes. Gemini 1.5 Flash.
    *   *Can Fail*: Yes.
9.  **`generate_readme`**
    *   *Inputs*: `human_approved_facts`
    *   *Outputs*: `readme_content`
    *   *LLM Call*: Yes. Gemini 1.5 Flash.
    *   *Can Fail*: Yes.
10. **`generate_portfolio_doc`**
    *   *Inputs*: `human_approved_facts`
    *   *Outputs*: `portfolio_doc`
    *   *LLM Call*: Yes. Gemini 1.5 Flash.
    *   *Can Fail*: Yes.
11. **`store_all_outputs`**
    *   *Inputs*: `resume_bullets`, `linkedin_desc`, `readme_content`, `portfolio_doc`
    *   *Outputs*: None (saves all text fields to Postgres `generated_outputs` and uploads raw backups to Cloudflare R2).
    *   *LLM Call*: No.
    *   *Can Fail*: Yes.
12. **`notify_user`**
    *   *Inputs*: `job_id`, `error`
    *   *Outputs*: None (publishes job success/fail event message to Redis WS queue).
    *   *LLM Call*: No.
    *   *Can Fail*: No.

---

### LangGraph State Schema Design

The `ResumeAgentState` is defined as a `TypedDict`. Below is the logical data layout:

| Field Name | Type | Purpose | Writer Node | Reader Node(s) |
|---|---|---|---|---|
| `repo_url` | `str` | Target repository to analyze. | Frontend (Init) | `fetch_repository_metadata`, `clone_or_fetch_file_tree` |
| `repo_metadata` | `dict` | Star count, owner, repo size, languages. | `fetch_repository_metadata` | `extract_code_facts` |
| `file_tree` | `list[str]` | Flat list of all relative file paths. | `clone_or_fetch_file_tree` | `extract_code_facts`, `validate_facts` |
| `extracted_facts` | `list[dict]`| Raw, unverified AI claims from code. | `extract_code_facts` | `validate_facts` |
| `validated_facts` | `list[dict]`| Facts that passed structural rules. | `validate_facts` | `store_facts_to_db`, `await_human_review` |
| `human_approved_facts`| `list[dict]`| Selected and verified user-approved facts.| User (BFF Input API) | All output generation nodes |
| `human_review_status` | `Literal` | Review state: `"pending"`, `"approved"`, `"edited"`. | User (BFF Input API) | Graph control loops |
| `resume_bullets` | `list[str]` | Generated resume experience text. | `generate_resume_bullets` | `store_all_outputs` |
| `linkedin_desc` | `str` | Structured project description. | `generate_linkedin_desc` | `store_all_outputs` |
| `readme_content` | `str` | Polished Markdown README. | `generate_readme` | `store_all_outputs` |
| `portfolio_doc` | `str` | Long-form project breakdown page. | `generate_portfolio_doc` | `store_all_outputs` |
| `job_id` | `UUID` | Pointer to the `analysis_jobs` database row. | Frontend (Init) | All Nodes (for logging & checkpoint linkage) |
| `error` | `str | None`| Error trace message if state failed. | Any failing node | `store_all_outputs`, `notify_user` |
| `retry_count` | `int` | Counter tracking current API retries. | Any retrying node | Any retrying node |

---

### LangGraph Checkpoint Strategy

*   **Checkpoint Backend**: LangGraph state checkpointers are saved to PostgreSQL using the `langgraph-checkpoint-postgres` library (using Supabase).
*   **Checkpoint Timing**: A state snapshot is written to Postgres at the end of **every single node execution** (transactional).
*   **Server Crash Recovery**: If the Celery worker dies mid-workflow (e.g., due to memory crash or Render restart):
    1.  The graph state remains stored in the DB at the last successfully completed node.
    2.  When the service boots back up, we read the current `langgraph_thread_id` and the latest status from the `analysis_jobs` table.
    3.  A Celery task restart request fetches the last valid checkpoint and calls `.compile().resume(thread_id)`. The engine skips successfully run nodes and resumes exactly where it died.
*   **Human-In-The-Loop Implementation**: Checkpointing is the engine behind our HiTL logic. By defining the `await_human_review` node as an interrupt node, the compiler executes everything up to that node, saves the checkpoint to PostgreSQL, and safely halts execution without blocking any memory threads or waiting connections.

---

## 1.6 Human-In-The-Loop Flow (Step-by-Step)

```
[Start Pipeline]
       │
       ▼
   [Validate Facts] ──► Write facts to `code_facts` (is_human_approved = False)
       │
       ▼
[Reach node 'await_human_review']
       │
       ▼
1. Compiler triggers "interrupt". Saves State to Postgres via checkpoint manager.
       │
       ▼
2. Celery worker updates `analysis_jobs` status to `interrupted`. Task terminates.
       │
       ▼
3. Worker publishes message "review_required" containing `job_id` to Redis Pub/Sub.
       │
       ▼
4. FastAPI Server (listening to Pub/Sub) catches the message and forwards it via WebSocket to Client.
       │
       ▼
5. React Client receives WS event: {event: "review_required", job_id: "..."}
       │
       ▼
6. UI redirects user to /repositories/[id]/review. Displays extracted facts.
       │
       ▼
7. User reviews the claims, makes inline edits to claims, or rejects items (sets toggle).
       │
       ▼
8. User clicks "Confirm Facts". Client POSTs payload to API endpoint `/reviews/{review_id}/approve`.
       │
       ▼
9. API Updates DB facts table. Dispatches Celery task `resume_analysis_workflow` with thread_id.
       │
       ▼
10. Celery worker re-instantiates graph, loads checkpoint state from DB, updates state fields,
    and runs graph.resume() past the interrupt block.
```

### Edge-Case Mechanisms:

*   **What if the user never responds (Timeout Policy)?**
    *   A hourly scheduled Celery beat task (`expire_stale_reviews`) scans the database for `human_reviews` that have been in `pending` state for more than **48 hours**.
    *   The task marks the review as `timed_out`, sets the `analysis_job` status to `failed` with error "Review timeout", and deletes the temporary files associated with the job in object storage.
*   **What if the server crashes between step 2 and step 8?**
    *   No active process or thread is running in memory while waiting for human input. The Celery worker exited immediately after saving the checkpoint.
    *   If the backend crashes and restarts, the database checkpoint remains intact. When the user eventually returns to the review page and submits their edits, the API will hit the same database, find the checkpoint, and start a fresh Celery worker thread to continue execution.
