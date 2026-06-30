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
│          clone_repo              │ (Git clone & walk file tree)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│         extract_facts            │ (Heuristic package scan)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│       extract_llm_facts          │ (LiteLLM structured facts)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│         validate_facts           │ (Verification of snippets)
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│        save_intermediate         │ (Upload drafts, set AWAITING_REVIEW)
└─────────────────┬────────────────┘
                  │
                  ▼
  [INTERRUPT: await_human_review]    <--- Execution state saved via PostgresSaver.
                  │                       Task suspends.
                  │
                  ▼ (User updates facts & clicks Resume, triggering Celery)
┌──────────────────────────────────┐
│       compile_documents          │ (LLM ATS reasoning + LaTeX compiling
└─────────────────┬────────────────┘  with 3-step AI self-healing compiler loop)
                  │
                  ▼
┌──────────────────────────────────┐
│        upload_metadata           │ (Upload final outputs & set COMPLETE)
└─────────────────┬────────────────┘
                  │
                  ▼
                [END]
```

### Node Specifications

1.  **`clone_repo`**
    *   *Inputs*: `github_url`
    *   *Outputs*: `file_tree`, `local_path`
    *   *LLM Call*: No.
    *   *Can Fail*: Yes. (e.g., repository is private, or git checkout timeout).
    *   *Failure Behavior*: Set `error` in state, transitions to `upload_metadata`.
2.  **`extract_facts`**
    *   *Inputs*: `file_tree`, `local_path`
    *   *Outputs*: `extracted_facts` (heuristic stack facts)
    *   *LLM Call*: No.
    *   *Can Fail*: No.
3.  **`extract_llm_facts`**
    *   *Inputs*: `file_tree`, `local_path`
    *   *Outputs*: `extracted_facts` (combined heuristic and LLM structured claims)
    *   *LLM Call*: Yes. LiteLLM (`gpt-4o-mini` routed to `gemini-3.1-flash-lite`).
    *   *Can Fail*: Yes (Rate limits, API proxy errors).
    *   *Failure Behavior*: Set `error`, transitions to `upload_metadata`.
4.  **`validate_facts`**
    *   *Inputs*: `extracted_facts`, `local_path`
    *   *Outputs*: `extracted_facts` (filtered, verified facts)
    *   *LLM Call*: No. (Normalizes whitespace and performs substring searches on cited files to verify evidence snippets).
5.  **`save_intermediate`**
    *   *Inputs*: `extracted_facts`, `file_tree`
    *   *Outputs*: None (uploads draft `analysis_result.json` and `file_tree.json` to MinIO, updates DB status to `AWAITING_REVIEW`, and posts Redis broadcast event).
    *   *LLM Call*: No.
    *   *Can Fail*: Yes.
6.  **`await_human_review` (Interrupt Node)**
    *   *Inputs*: `extracted_facts`
    *   *Outputs*: `extracted_facts` (updated with user revisions)
    *   *LLM Call*: No.
    *   *Can Fail*: No. Compiled with `interrupt_before=["await_human_review"]` as a checkpoint boundary.
7.  **`compile_documents`**
    *   *Inputs*: `extracted_facts`
    *   *Outputs*: `generated_outputs` (files written to MinIO, and metadata in Postgres)
    *   *LLM Call*: Yes. LiteLLM (`gpt-4o-mini`).
    *   *Behavior & AI Self-Healing*:
        *   **ATS Optimizer Reasoning**: Analyzes facts, chooses active verbs, maps technical keywords to ATS criteria.
        *   **One-Page Layout Budget**: Spacing and sizes formatted to fit exactly 1 page.
        *   **LaTeX Compilation**: Outputs LaTeX string, runs `pdflatex` in subprocess. If compilation fails with error codes, reads log file, calls the LLM with error logs for self-healing repair, and retries compilation (up to 3 times).
        *   **Standard Markdown Output**: Generates LinkedIn Profile Summary, GitHub Profile README, and Developer Portfolio landing page copy.
8.  **`upload_metadata`**
    *   *Inputs*: `extracted_facts`, `local_path`
    *   *Outputs*: None (uploads final compile summaries, marks DB status as `COMPLETE`, publishes Redis complete signal, and purges the cloned local temp directory).
    *   *LLM Call*: No.

---

### LangGraph State Schema Design

The `AnalysisState` is defined as a `TypedDict`. Below is the logical data layout:

| Field Name | Type | Purpose | Writer Node | Reader Node(s) |
|---|---|---|---|---|
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

## 1.7 Security & Sandbox Execution Model

To run untrusted agent actions and protect user repository confidentiality, we implement a multi-layered Least Privilege isolation model:
*   **Private Repository Data Isolation**: Restricts private repositories using the `verify_github_ownership` FastAPI Dependency guard. Private repositories must map to the logged-in owner's database `user_id`, verified against their active GitHub OAuth token.
*   **3-Level Caching Security**:
    *   *Level 1 (Meta)*: Redis-backed shared metadata keys (`github_meta:{username}`).
    *   *Level 2 (Public)*: Redis-backed public repository list caching (`github_public_repos:{username}`).
    *   *Level 3 (Private)*: Stored in PostgreSQL ONLY under strict `user_id` query scoping. Private repository data is **never** written to Redis to eliminate data exposure in public in-memory stores.
*   **Read-Only Bind Mounts (`ro`)**: Cloned GitHub repository files are mapped into worker containers as Read-Only volumes. The agent can read and parse source files but has no filesystem permissions to modify, inject, or delete repository code.
*   **Rootless Execution**: All processes within the FastAPI and Celery worker containers run as a non-privileged user (`USER 1000:1000`). Root access is blocked globally.
*   **Ephemeral Package Target Isolation**: If the agent must download a dependency or run an custom tool, it installs packages inside a virtualized target directory (`/tmp/agent_env/`) using `uv pip install --target`. We update the running Python environment path dynamically (`sys.path.append`).
*   **Subprocess Container Sandboxing**: For executing dynamic code or running shell operations, we spin up secondary throw-away containers, execute the script, capture stdout/stderr, and immediately delete the container.

---

## 1.8 Human-in-the-Loop Feedback & User Preference Memory

To prevent the agent from repeating formatting mistakes or generating unwanted styles across sessions, we implement a reflective memory pipeline:
*   **Reflection Step**: When a user modifies or rejects claims on the fact-review page, a background task triggers an LLM to compare the original vs. edited versions, extracting general user preferences.
*   **User Preference Storage**: Extracted rules (e.g. "Do not list local script commands", "Focus heavily on cloud architecture") are saved in the PostgreSQL `user_preferences` table under the user's ID.
*   **Prompt Injection**: At the start of any new analysis or generation task, the backend queries the database for these style rules and injects them directly into the system prompt as custom user guidelines.

---

## 1.9 Context Optimization & Project Knowledge Graph (GraphRAG)

To reduce token burn and latency during code analysis, we organize the codebase as a dependency graph:
*   **Dependency Graph (`project_graph.json`)**: We generate a lightweight JSON-structured map of codebase dependencies, file imports, and data links.
*   **Pruned Retrieval**: When the agent executes a specific task, it consults the project graph first to identify the minimal subset of files required for context. Only these specific file contents are retrieved and fed to the LLM, keeping the token context window small and relevant.

---

## 1.10 Context Ingestion & Clarification Gate

To prevent hallucinations, guessed contact info, or filler words, we implement a context-validation gateway:
*   **Pydantic Audit Check**: Before starting document generation, the `check_missing_context` node runs a Pydantic schema validation over the active state, checking for missing contact info (phone, email, name) or target parameters (target title, target stack).
*   **Clarification Interrupt**: If critical fields are missing, the graph records the queries inside `missing_context_questions` and enters an interrupt state (`await_user_context`).
*   **Questionnaire UI**: The frontend pauses the pipeline and presents the user with an inline form requesting the missing information. Once submitted, the data is saved, and the graph resumes generation with complete, accurate context.

