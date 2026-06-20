# DOCUMENT 3: API DESIGN

This document outlines the REST and WebSocket API design for the GitHub Repository Intelligence Platform. All request/response payloads are validated using Pydantic v2 on the FastAPI backend.

---

## 1. Authentication Endpoints

### POST /auth/github
ENDPOINT: POST /api/v1/auth/github  
DESCRIPTION: Exchanges the GitHub OAuth temporary code for a JWT access token, creates a new user profile if one does not exist, or updates the `last_login_at` timestamp.  
AUTH: public  
ASYNC: no  
REQUEST:  
  Body: `{ "code": "string — OAuth authorization code from GitHub callback redirect" }`  
RESPONSE (200):  
  `{ "token": "string — JWT authentication token", "user": { "id": "UUID", "email": "string", "github_username": "string", "subscription_tier": "free" } }`  
RESPONSE (errors):  
  400: Invalid or expired GitHub OAuth authorization code  
  429: OAuth exchange rate limit hit (GitHub API limits)  
RATE LIMIT: 5 requests per minute per IP  
TRIGGERS: None  

### POST /auth/signout
ENDPOINT: POST /api/v1/auth/signout  
DESCRIPTION: Blacklists the current JWT token in Redis to terminate the session.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Body: `{}`  
RESPONSE (200):  
  `{ "success": "boolean — True if sign out succeeded" }`  
RESPONSE (errors):  
  400: Token already expired or invalid  
RATE LIMIT: 10 requests per minute per user  
TRIGGERS: None  

### GET /auth/me
ENDPOINT: GET /api/v1/auth/me  
DESCRIPTION: Retrieves the authenticated user profile based on the JWT bearer token.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "id": "UUID — User ID", "email": "string", "github_username": "string", "subscription_tier": "free", "is_active": "boolean", "last_login_at": "string" }`  
RESPONSE (errors):  
  401: Unauthorized or expired token  
RATE LIMIT: 60 requests per minute per user  
TRIGGERS: None  

---

## 2. Repositories Endpoints

### POST /repositories
ENDPOINT: POST /api/v1/repositories  
DESCRIPTION: Ingests a public GitHub URL, verifies its existence via GitHub's API, and saves the repository record to the database with a `pending` analysis status.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Body: `{ "github_url": "string — GitHub public repository HTTPS URL" }`  
RESPONSE (200):  
  `{ "id": "UUID — Registered repository database ID", "owner": "string", "name": "string", "github_repo_id": "integer", "analysis_status": "pending", "created_at": "string" }`  
RESPONSE (errors):  
  400: Repository is private, invalid URL structure, or already registered by this user  
  404: Repository not found on GitHub  
  429: Too many repositories created  
RATE LIMIT: 10 requests per hour per user  
TRIGGERS: None  

### GET /repositories
ENDPOINT: GET /api/v1/repositories  
DESCRIPTION: Returns a paginated list of repositories registered by the authenticated user.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: `?page=integer&size=integer`  
RESPONSE (200):  
  `{ "items": [ { "id": "UUID", "owner": "string", "name": "string", "primary_language": "string", "analysis_status": "string", "star_count": "integer", "last_analyzed_at": "string" } ], "total": "integer", "page": "integer", "size": "integer" }`  
RESPONSE (errors):  
  401: Unauthorized  
RATE LIMIT: 60 requests per minute per user  
TRIGGERS: None  

### GET /repositories/{id}
ENDPOINT: GET /api/v1/repositories/{id}  
DESCRIPTION: Retrieves details of a specific repository owned by the user, including metadata and analysis state.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "id": "UUID", "github_url": "string", "owner": "string", "name": "string", "default_branch": "string", "primary_language": "string", "languages": "object — JSON map of language byte distribution", "star_count": "integer", "analysis_status": "string", "last_analyzed_at": "string", "created_at": "string" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Repository record not found  
RATE LIMIT: 60 requests per minute per user  
TRIGGERS: None  

### DELETE /repositories/{id}
ENDPOINT: DELETE /api/v1/repositories/{id}  
DESCRIPTION: Deletes a repository record. Triggers cascade deletion of all jobs, facts, and output files in object storage.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Body: `{}`  
RESPONSE (200):  
  `{ "success": "boolean — True if resource was deleted" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Repository record not found  
RATE LIMIT: 10 requests per minute per user  
TRIGGERS: `cleanup_old_jobs` task to purge MinIO/R2 artifact files.  

---

## 3. Analysis Endpoints

### POST /repositories/{id}/analyze
ENDPOINT: POST /api/v1/repositories/{id}/analyze  
DESCRIPTION: Triggers a background Celery task to execute the LangGraph pipeline for the repository. Checks active limits first.  
AUTH: required  
ASYNC: yes (returns job_id)  
REQUEST:  
  Body: `{}`  
RESPONSE (200):  
  `{ "job_id": "UUID — Generated analysis job ID", "repository_id": "UUID", "status": "queued" }`  
RESPONSE (errors):  
  400: Repository is already being analyzed (active job running)  
  401: Unauthorized  
  429: Active job queue limit exceeded (1 active job limit per user on free tier)  
RATE LIMIT: 3 requests per hour per user  
TRIGGERS: Celery task: `run_analysis_workflow`  

### GET /repositories/{id}/analysis/{job_id}
ENDPOINT: GET /api/v1/repositories/{id}/analysis/{job_id}  
DESCRIPTION: Returns execution details, progress indicators, current nodes, and resource usage metrics for a job.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "id": "UUID", "repository_id": "UUID", "status": "string — queued/running/interrupted/complete/failed/timed_out", "current_node": "string — active LangGraph node", "retry_count": "integer", "started_at": "string", "completed_at": "string", "llm_tokens_used": "integer", "error_message": "string" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Job ID not found for this repository  
RATE LIMIT: 60 requests per minute per user  
TRIGGERS: None  

### GET /repositories/{id}/analysis/{job_id}/facts
ENDPOINT: GET /api/v1/repositories/{id}/analysis/{job_id}/facts  
DESCRIPTION: Retrieves the list of facts extracted during the target job. Used by the UI during loading or review states.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: `?only_validated=boolean`  
RESPONSE (200):  
  `{ "facts": [ { "id": "UUID", "fact_type": "string", "fact_text": "string", "evidence_file_path": "string", "evidence_line_start": "integer", "evidence_line_end": "integer", "evidence_snippet": "string", "confidence_score": "float", "is_validated": "boolean", "is_human_approved": "boolean" } ] }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Job ID or facts not found  
RATE LIMIT: 30 requests per minute per user  
TRIGGERS: None  

---

## 4. Human Review Endpoints

### GET /reviews/pending
ENDPOINT: GET /api/v1/reviews/pending  
DESCRIPTION: Returns all pending Human-In-The-Loop review tasks waiting for user action.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "reviews": [ { "review_id": "UUID", "job_id": "UUID", "repository_name": "string", "expires_at": "string" } ] }`  
RESPONSE (errors):  
  401: Unauthorized  
RATE LIMIT: 30 requests per minute per user  
TRIGGERS: None  

### GET /reviews/{review_id}
ENDPOINT: GET /api/v1/reviews/{review_id}  
DESCRIPTION: Returns the full review resource containing the array of extracted facts to display in the interactive checklist interface.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "id": "UUID", "analysis_job_id": "UUID", "status": "pending", "original_facts": [ { "temp_id": "integer", "fact_type": "string", "fact_text": "string", "evidence_file_path": "string", "evidence_line_start": "integer", "evidence_line_end": "integer", "evidence_snippet": "string", "confidence_score": "float" } ], "expires_at": "string" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Review resource not found or expired  
RATE LIMIT: 30 requests per minute per user  
TRIGGERS: None  

### POST /reviews/{review_id}/approve
ENDPOINT: POST /api/v1/reviews/{review_id}/approve  
DESCRIPTION: Approves all facts generated in this review cycle without modifications, updating states and triggering the resume of the generation pipeline.  
AUTH: required  
ASYNC: yes (returns { "status": "resumed" })  
REQUEST:  
  Body: `{}`  
RESPONSE (200):  
  `{ "review_id": "UUID", "status": "approved", "analysis_job_id": "UUID" }`  
RESPONSE (errors):  
  400: Review is already processed (not in pending status)  
  401: Unauthorized  
  404: Review resource not found  
RATE LIMIT: 10 requests per minute per user  
TRIGGERS: Celery task: `resume_analysis_workflow` with approved facts.  

### POST /reviews/{review_id}/reject
ENDPOINT: POST /api/v1/reviews/{review_id}/reject  
DESCRIPTION: Cancels the analysis run, rejecting all facts and updating the job to a failed state.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Body: `{ "rejection_reason": "string — Description explaining why the run is rejected" }`  
RESPONSE (200):  
  `{ "review_id": "UUID", "status": "rejected" }`  
RESPONSE (errors):  
  400: Review is already processed  
  401: Unauthorized  
RATE LIMIT: 10 requests per minute per user  
TRIGGERS: None (updates database job status to `failed` and terminates the run).  

### PATCH /reviews/{review_id}/facts
ENDPOINT: PATCH /api/v1/reviews/{review_id}/facts  
DESCRIPTION: Submits a custom payload containing edited, approved, or rejected facts. Once processing completes, it transitions the review to `approved` (or `edited`) and resumes the pipeline.  
AUTH: required  
ASYNC: yes (returns { "status": "resumed" })  
REQUEST:  
  Body:  
    `{ "approved_fact_ids": [ "UUID" ], "edited_facts": [ { "id": "UUID", "fact_text": "string — edited claim statement", "fact_type": "string" } ], "rejected_fact_ids": [ "UUID" ] }`  
RESPONSE (200):  
  `{ "review_id": "UUID", "status": "edited", "analysis_job_id": "UUID" }`  
RESPONSE (errors):  
  400: Invalid schema or review is not pending  
  401: Unauthorized  
RATE LIMIT: 10 requests per minute per user  
TRIGGERS: Celery task: `resume_analysis_workflow` with the modified state payload.  

---

## 5. Outputs Endpoints

### GET /repositories/{id}/outputs
ENDPOINT: GET /api/v1/repositories/{id}/outputs  
DESCRIPTION: Lists metadata of all generated resume, LinkedIn, README, and portfolio files for the repository.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "outputs": [ { "id": "UUID", "output_type": "string — resume_bullets/linkedin_desc/readme/portfolio_doc", "version": "integer", "is_current_version": "boolean", "llm_model_used": "string", "created_at": "string" } ] }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Repository not found  
RATE LIMIT: 30 requests per minute per user  
TRIGGERS: None  

### GET /outputs/{id}
ENDPOINT: GET /api/v1/outputs/{id}  
DESCRIPTION: Retrieves the text contents and metadata of a specific generated output resource.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: None  
RESPONSE (200):  
  `{ "id": "UUID", "output_type": "string", "content": "string — raw markdown/text content", "version": "integer", "llm_model_used": "string", "minio_object_key": "string" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Output resource not found  
RATE LIMIT: 30 requests per minute per user  
TRIGGERS: None  

### POST /outputs/{id}/regenerate
ENDPOINT: POST /api/v1/outputs/{id}/regenerate  
DESCRIPTION: Reruns the generation node in the background using the user's previously approved facts, incrementing the version index.  
AUTH: required  
ASYNC: yes (returns job_id)  
REQUEST:  
  Body: `{ "target_job_description": "string — optional text to tailor outputs" }`  
RESPONSE (200):  
  `{ "job_id": "UUID — fresh generation run job ID", "status": "queued" }`  
RESPONSE (errors):  
  401: Unauthorized  
  404: Output resource not found  
RATE LIMIT: 5 requests per hour per user  
TRIGGERS: Celery task: `run_analysis_workflow` (skips ingestion and goes straight to generation).  

### GET /outputs/{id}/download
ENDPOINT: GET /api/v1/outputs/{id}/download  
DESCRIPTION: Logs a download transaction audit event and returns a Cloudflare R2 presigned download URL for the target output file.  
AUTH: required  
ASYNC: no  
REQUEST:  
  Query: `?format=md` (options: txt, md, pdf, json)  
RESPONSE (200):  
  `{ "download_url": "string — signed Cloudflare R2 object URL", "expires_at": "string — ISO timestamp indicating link expiration" }`  
RESPONSE (errors):  
  400: Format not supported  
  401: Unauthorized  
  404: Output record not found  
RATE LIMIT: 20 requests per minute per user  
TRIGGERS: None (generates signed URL key in-process).  

---

## 6. WebSocket Protocol & Contract

### WebSocket Handshake Connection
*   **Connection URI**: `ws://<domain>/api/ws/{user_id}?token=<JWT>`  
*   **Protocol Handling**: The Next.js BFF opens a WebSocket client connection on render. The FastAPI gateway intercepts the request, validates the JWT query token, retrieves the `user_id`, registers the socket session descriptor in an in-memory route map, and subscribes to a Redis pub/sub channel keyed as `user:events:{user_id}`.

### Events contract (JSON format)

#### 1. Job Queued
Sent when a background job request is accepted by the server.
```json
{
  "event": "job_queued",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "repository_id": "2e65005b-80df-4589-a2ba-c711a77cd5d3"
  }
}
```

#### 2. Job Started
Sent when a Celery worker pulls the task and starts the LangGraph run.
```json
{
  "event": "job_started",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "started_at": "2026-06-18T19:00:00Z"
  }
}
```

#### 3. Graph Node Changed
Broadcasted whenever LangGraph finishes a node execution and proceeds to the next, helping the UI show active step-by-step progress.
```json
{
  "event": "node_changed",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "node_name": "extract_code_facts"
  }
}
```

#### 4. Review Required (Interrupt Event)
Dispatched when LangGraph hits the human-in-the-loop checkpoint, indicating the worker thread has suspended and user approval is required.
```json
{
  "event": "review_required",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "review_id": "7dcbe0bf-ea4b-4809-b684-2ee19d28cf4a",
    "expires_at": "2026-06-20T19:00:00Z"
  }
}
```

#### 5. Generation Started
Dispatched when the review is confirmed and the compilation phase resumes.
```json
{
  "event": "generation_started",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "approved_facts_count": 14
  }
}
```

#### 6. Job Completed Successfully
Sent when all outputs have been generated, saved to DB, and written to object storage.
```json
{
  "event": "job_complete",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "completed_at": "2026-06-18T19:01:45Z",
    "outputs": [
      { "id": "3587b1c1-4df2-47ef-a0d0-7ad1f50a8d67", "type": "resume_bullets" }
    ]
  }
}
```

#### 7. Job Failed
Dispatched on critical pipeline crashes or processing timeouts.
```json
{
  "event": "job_failed",
  "job_id": "4b6c3104-bdad-4a7b-a37a-7bf3b0cc08ff",
  "data": {
    "error": "Failed to fetch repository tree: repository size exceeds 100MB limit."
  }
}
```
