# DOCUMENT 7: OBSERVABILITY DESIGN

This document outlines the observability, tracing, metrics, and structured logging design for the platform.

---

## 7.1 Langfuse LLM Tracing

We use self-hosted **Langfuse** via Docker to trace and monitor our LLM calls, costs, and latencies.

### 1. Trace Structure: `analyze_repository`

Every repository analysis job initializes a single Langfuse trace:
*   **Trace Name**: `analyze_repository`
*   **Tags**: `user_id:<UUID>`, `repo_id:<UUID>`, `job_id:<UUID>`
*   **Trace Metadata**: `{ "github_url": "...", "subscription_tier": "free/pro" }`

#### Trace Spans (One span per LLM-enabled LangGraph node)

1.  **Span: `extract_code_facts`**
    *   *LLM Provider & Model*: Gemini 1.5 Flash (via LiteLLM).
    *   *Usage Tracking*: Captured input prompt tokens, output completion tokens, total token cost, and latency.
    *   *Metadata*: Repo file count, language distribution, file tree complexity.
2.  **Span: `generate_resume_bullets`**
    *   *LLM Provider & Model*: Groq / Llama 3 70B.
    *   *Usage Tracking*: Tokens, latency, cost.
    *   *Metadata*: Target job description length, count of approved facts.
3.  **Span: `generate_linkedin_desc`**
    *   *LLM Provider & Model*: Gemini 1.5 Flash.
    *   *Usage Tracking*: Tokens, latency, cost.
4.  **Span: `generate_readme`**
    *   *LLM Provider & Model*: Gemini 1.5 Flash.
    *   *Usage Tracking*: Tokens, latency, cost.
5.  **Span: `generate_portfolio_doc`**
    *   *LLM Provider & Model*: Gemini 1.5 Flash.
    *   *Usage Tracking*: Tokens, latency, cost.

---

### 2. Langfuse Dashboards to Build

1.  **Cost and Token Usage Dashboard**:
    *   *Metric*: Cumulative cost (USD) and tokens spent per day, grouped by user ID and model name.
    *   *Purpose*: Tracks budget limits and identifies heavy users.
2.  **LLM Call Latency Dashboard**:
    *   *Metric*: P50, P90, and P95 latency (in seconds) for each node.
    *   *Purpose*: Monitors API degradation across providers.
3.  **Error Rate by Model and Provider**:
    *   *Metric*: Count of failed LLM calls divided by total requests, grouped by model name (e.g., Llama 3 on Groq vs. Gemini 1.5 on Google).
    *   *Purpose*: Alerts on provider outages and triggers automated routing changes.
4.  **Quality & Hallucination Trace Dashboard**:
    *   *Metric*: Count of rejected facts during user review step, correlated with the generation model version.
    *   *Purpose*: Measures LLM fact accuracy.
5.  **Caching Efficiency Dashboard**:
    *   *Metric*: Redis cache hit rate for repository structures and LiteLLM configurations.
    *   *Purpose*: Optimizes lookup latencies.

---

## 7.2 Prometheus Metrics

The following custom metrics are exposed by the FastAPI application on the `/metrics` endpoint:

### 1. `analysis_job_total`
*   **TYPE**: Counter
*   **LABELS**: `status` (queued, running, complete, failed, timed_out), `subscription_tier`
*   **PURPOSE**: Tracks total jobs executed over time.
*   **ALERT**: None.

### 2. `analysis_job_duration_seconds`
*   **TYPE**: Histogram (Buckets: 15s, 30s, 60s, 120s, 240s, 300s)
*   **LABELS**: `status` (complete, failed, timed_out)
*   **PURPOSE**: Measures total duration of repository analysis workflows.
*   **ALERT**: `histogram_quantile(0.95, sum(rate(analysis_job_duration_seconds_bucket[5m])) by (le)) > 240` (triggers alert if 95% of jobs take longer than 4 minutes).

### 3. `llm_api_call_total`
*   **TYPE**: Counter
*   **LABELS**: `provider` (groq, gemini), `model`, `status` (success, failure)
*   **PURPOSE**: Counts LLM calls to track API usage.
*   **ALERT**: `sum(rate(llm_api_call_total{status="failure"}[5m])) / sum(rate(llm_api_call_total[5m])) > 0.05` (triggers critical alert if LLM call failure rate exceeds 5% over 5 minutes).

### 4. `llm_token_consumption_total`
*   **TYPE**: Counter
*   **LABELS**: `user_id`, `model`, `type` (prompt, completion)
*   **PURPOSE**: Tracks token usage to enforce free-tier quotas.
*   **ALERT**: None.

### 5. `active_websocket_connections`
*   **TYPE**: Gauge
*   **LABELS**: None.
*   **PURPOSE**: Tracks real-time active user sessions.
*   **ALERT**: None.

### 6. `celery_task_backlog`
*   **TYPE**: Gauge
*   **LABELS**: `queue` (analysis, generation, notifications)
*   **PURPOSE**: Tracks queued tasks waiting for a worker thread.
*   **ALERT**: `celery_task_backlog{queue="analysis"} > 10` (triggers alert if more than 10 repository jobs are stuck in queue, signaling worker starvation).

### 7. `human_review_turnaround_seconds`
*   **TYPE**: Histogram (Buckets: 60s, 300s, 1800s, 7200s, 86400s)
*   **LABELS**: `status` (approved, rejected, timed_out)
*   **PURPOSE**: Tracks how long reviews remain pending before user response.
*   **ALERT**: None.

### 8. `r2_storage_bytes_total`
*   **TYPE**: Gauge
*   **LABELS**: `bucket` (raw-repositories, analysis-artifacts, generated-outputs, user-exports)
*   **PURPOSE**: Tracks object storage consumption.
*   **ALERT**: `r2_storage_bytes_total{bucket="raw-repositories"} > 8000000000` (triggers alert if temporary repositories exceed 8GB, indicating cleanup tasks are failing).

### 9. `latex_compilation_retry_total`
*   **TYPE**: Counter
*   **LABELS**: `status` (success, failure), `attempt` (1, 2, 3)
*   **PURPOSE**: Tracks the count of LaTeX compiler execution retries inside the self-healing retry loop.
*   **ALERT**: None.

---

## 7.3 Structured Log Format

We use `structlog` in Python to output JSON logs to stdout. This enables unified log parsing and analysis.

### 1. Celery Task Starting
```json
{
  "timestamp": "2026-06-18T19:10:00.001Z",
  "level": "info",
  "service": "celery-worker",
  "trace_id": "9a38f32c-3543-4ef3-bde8-d73111f18579",
  "span_id": "402e1c95-30bb-485e-990c-db9eb2c52538",
  "user_id": "usr_9921b72e-d01c-4395-8e10-bf9d02167d3b",
  "job_id": "job_09e45be0-8669-42b7-873b-e01db109ce4a",
  "message": "Celery worker received analysis workflow execution task.",
  "duration_ms": 0,
  "task_name": "app.tasks.pipeline.run_analysis_workflow",
  "queue": "analysis"
}
```

### 2. LLM Call Completing
```json
{
  "timestamp": "2026-06-18T19:10:14.342Z",
  "level": "info",
  "service": "celery-worker",
  "trace_id": "9a38f32c-3543-4ef3-bde8-d73111f18579",
  "span_id": "f5b8a920-80de-4ee2-b364-58a1ee2a0230",
  "user_id": "usr_9921b72e-d01c-4395-8e10-bf9d02167d3b",
  "job_id": "job_09e45be0-8669-42b7-873b-e01db109ce4a",
  "message": "LLM call completed successfully via LiteLLM proxy.",
  "duration_ms": 1420,
  "provider": "google",
  "model": "gemini-1.5-flash",
  "prompt_tokens": 143890,
  "completion_tokens": 842,
  "cost_usd": 0.01082
}
```

### 3. Human Review Being Submitted
```json
{
  "timestamp": "2026-06-18T19:12:45.109Z",
  "level": "info",
  "service": "api-backend",
  "trace_id": "9a38f32c-3543-4ef3-bde8-d73111f18579",
  "span_id": "d04a7bc9-40de-44ae-92bb-ea39db8ce120",
  "user_id": "usr_9921b72e-d01c-4395-8e10-bf9d02167d3b",
  "job_id": "job_09e45be0-8669-42b7-873b-e01db109ce4a",
  "message": "Human review checklist processed and verified.",
  "duration_ms": 285,
  "review_id": "rvw_b049d8e7-ebc2-480c-b45b-7b0a7ed99e3a",
  "approved_count": 12,
  "edited_count": 2,
  "rejected_count": 1,
  "status": "edited"
}
```

### 4. Job Failing
```json
{
  "timestamp": "2026-06-18T19:10:15.551Z",
  "level": "error",
  "service": "celery-worker",
  "trace_id": "9a38f32c-3543-4ef3-bde8-d73111f18579",
  "span_id": "f5b8a920-80de-4ee2-b364-58a1ee2a0230",
  "user_id": "usr_9921b72e-d01c-4395-8e10-bf9d02167d3b",
  "job_id": "job_09e45be0-8669-42b7-873b-e01db109ce4a",
  "message": "Repository analysis job terminated prematurely due to unrecoverable exception.",
  "duration_ms": 15550,
  "error": "LiteLLM RateLimitError: API rate limit exceeded on groq/llama3-70b. Code 429.",
  "failed_node": "extract_code_facts",
  "retry_attempt": 3
}
```

### 5. LaTeX Self-Healing Attempt
```json
{
  "timestamp": "2026-06-18T19:15:20.401Z",
  "level": "warning",
  "service": "celery-worker",
  "trace_id": "9a38f32c-3543-4ef3-bde8-d73111f18579",
  "job_id": "job_09e45be0-8669-42b7-873b-e01db109ce4a",
  "message": "LaTeX compilation failed. Initiating AI self-healing repair loop.",
  "attempt": 1,
  "exit_code": 1,
  "last_log_lines": "! Undefined control sequence.\nl.15 \\invalidmacro\n",
  "diagnosed_cause": "The generated LaTeX code contains an undefined control sequence \\invalidmacro on line 15."
}
```
```
