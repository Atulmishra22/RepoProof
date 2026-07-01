from prometheus_client import Counter, Histogram, Gauge

# 1. analysis_job_total
analysis_job_total = Counter(
    "analysis_job_total",
    "Tracks total jobs executed over time.",
    ["status", "subscription_tier"]
)

# 2. analysis_job_duration_seconds
analysis_job_duration_seconds = Histogram(
    "analysis_job_duration_seconds",
    "Measures total duration of repository analysis workflows.",
    ["status"],
    buckets=[15.0, 30.0, 60.0, 120.0, 240.0, 300.0]
)

# 3. llm_api_call_total
llm_api_call_total = Counter(
    "llm_api_call_total",
    "Counts LLM calls to track API usage.",
    ["provider", "model", "status"]
)

# 4. llm_token_consumption_total
llm_token_consumption_total = Counter(
    "llm_token_consumption_total",
    "Tracks token usage to enforce free-tier quotas.",
    ["user_id", "model", "type"]
)

# 5. active_websocket_connections
active_websocket_connections = Gauge(
    "active_websocket_connections",
    "Tracks real-time active user sessions."
)

# 6. celery_task_backlog
celery_task_backlog = Gauge(
    "celery_task_backlog",
    "Tracks queued tasks waiting for a worker thread.",
    ["queue"]
)

# 7. human_review_turnaround_seconds
human_review_turnaround_seconds = Histogram(
    "human_review_turnaround_seconds",
    "Tracks how long reviews remain pending before user response.",
    ["status"],
    buckets=[60.0, 300.0, 1800.0, 7200.0, 86400.0]
)

# 8. r2_storage_bytes_total
r2_storage_bytes_total = Gauge(
    "r2_storage_bytes_total",
    "Tracks object storage consumption.",
    ["bucket"]
)

# 9. latex_compilation_retry_total
latex_compilation_retry_total = Counter(
    "latex_compilation_retry_total",
    "Tracks the count of LaTeX compiler execution retries inside the self-healing retry loop.",
    ["status", "attempt"]
)
