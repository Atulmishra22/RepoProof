# DOCUMENT 8: DOCKER ARCHITECTURE

This document details the Docker Compose and container orchestration architecture for the local development environment, as well as its mapping to cloud services in production.

---

## 8.1 Service Definitions

The following services compile our multi-container microservice system under `docker-compose.yml`:

### 1. `postgres`
*   **SERVICE**: `postgres`
*   **IMAGE**: `postgres:16-alpine`
*   **PORTS**: `5432:5432`
*   **VOLUMES**: `postgres_data:/var/lib/postgresql/data`
*   **ENVIRONMENT**:  
    `POSTGRES_DB=repo_intel`  
    `POSTGRES_USER=postgres`  
    `POSTGRES_PASSWORD=postgres_dev_pass`
*   **DEPENDS_ON**: None.
*   **HEALTHCHECK**:  
    `test: ["CMD-SHELL", "pg_isready -U postgres -d repo_intel"]`  
    `interval: 5s`  
    `timeout: 5s`  
    `retries: 5`
*   **RESTART**: `always`

---

### 2. `redis`
*   **SERVICE**: `redis`
*   **IMAGE**: `redis:7-alpine`
*   **PORTS**: `6379:6379`
*   **VOLUMES**: `redis_data:/data`
*   **ENVIRONMENT**: None.
*   **DEPENDS_ON**: None.
*   **HEALTHCHECK**:  
    `test: ["CMD-SHELL", "redis-cli ping | grep PONG"]`  
    `interval: 5s`  
    `timeout: 5s`  
    `retries: 5`
*   **RESTART**: `always`

---

### 3. `minio`
*   **SERVICE**: `minio`
*   **IMAGE**: `minio/minio:RELEASE.2024-01-28T22-41-38Z`
*   **PORTS**: `9000:9000`, `9001:9001`
*   **VOLUMES**: `minio_data:/data`
*   **ENVIRONMENT**:  
    `MINIO_ROOT_USER=minioadmin`  
    `MINIO_ROOT_PASSWORD=minioadminpass`
*   **DEPENDS_ON**: None.
*   **HEALTHCHECK**:  
    `test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]`  
    `interval: 10s`  
    `timeout: 5s`  
    `retries: 3`
*   **RESTART**: `always`

---

### 4. `backend`
*   **SERVICE**: `backend`
*   **IMAGE**: `repo-intel-backend:latest` (built locally from `./backend/Dockerfile`)
*   **PORTS**: `8000:8000`
*   **VOLUMES**: `./backend:/app`
*   **ENVIRONMENT**:  
    `DATABASE_URL=postgresql://postgres:postgres_dev_pass@postgres:5432/repo_intel`  
    `REDIS_URL=redis://redis:6379/0`  
    `S3_ENDPOINT_URL=http://minio:9000`  
    `S3_ACCESS_KEY_ID=minioadmin`  
    `S3_SECRET_ACCESS_KEY=minioadminpass`  
    `GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}`  
    `GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}`  
    `LITELLM_PROXY_URL=http://litellm:4000`  
    `LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY}`  
    `LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}`  
    `LANGFUSE_HOST=http://langfuse:3000`
*   **DEPENDS_ON**:  
    *   `postgres` (condition: `service_healthy`)  
    *   `redis` (condition: `service_healthy`)  
    *   `minio` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]`  
    `interval: 10s`  
    `timeout: 5s`  
    `retries: 3`
*   **RESTART**: `always`
*   **NOTE**: The container image installs standard LaTeX/TeX Live compilation tools to compile `.tex` resumes to PDF in the background.

---

### 5. `worker`
*   **SERVICE**: `worker`
*   **IMAGE**: `repo-intel-backend:latest` (shares base code with backend and LaTeX compiler tools)
*   **PORTS**: None (internal task execution only).
*   **VOLUMES**: `./backend:/app`
*   **ENVIRONMENT**: Same env payload as `backend` service.
*   **DEPENDS_ON**:  
    *   `backend` (condition: `service_healthy`)  
    *   `redis` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD-SHELL", "celery -A app.celery inspect ping"]`  
    `interval: 15s`  
    `timeout: 10s`  
    `retries: 3`
*   **RESTART**: `always`

---

### 6. `flower`
*   **SERVICE**: `flower`
*   **IMAGE**: `mher/flower:latest`
*   **PORTS**: `5555:5555`
*   **VOLUMES**: None.
*   **ENVIRONMENT**:  
    `CELERY_BROKER_URL=redis://redis:6379/0`
*   **DEPENDS_ON**:  
    *   `redis` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD", "curl", "-f", "http://localhost:5555/"]`  
    `interval: 30s`  
    `timeout: 5s`  
    `retries: 3`
*   **RESTART**: `unless-stopped`

---

### 7. `langfuse`
*   **SERVICE**: `langfuse`
*   **IMAGE**: `langfuse/langfuse:latest`
*   **PORTS**: `3000:3000`
*   **VOLUMES**: None.
*   **ENVIRONMENT**:  
    `DATABASE_URL=postgresql://postgres:postgres_dev_pass@postgres:5432/repo_intel`  
    `NEXTAUTH_SECRET=langfuse_dev_secret_key`  
    `NEXTAUTH_URL=http://localhost:3000`  
    `SALT=langfuse_dev_salt_string`
*   **DEPENDS_ON**:  
    *   `postgres` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]`  
    `interval: 15s`  
    `timeout: 10s`  
    `retries: 3`
*   **RESTART**: `always`

---

### 8. `prometheus`
*   **SERVICE**: `prometheus`
*   **IMAGE**: `prom/prometheus:latest`
*   **PORTS**: `9090:9090`
*   **VOLUMES**:  
    *   `./prometheus.yml:/etc/prometheus/prometheus.yml`  
    *   `prometheus_data:/prometheus`
*   **ENVIRONMENT**: None.
*   **DEPENDS_ON**:  
    *   `backend` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD", "nc", "-z", "localhost", "9090"]`  
    `interval: 30s`  
    `timeout: 5s`  
    `retries: 3`
*   **RESTART**: `unless-stopped`

---

### 9. `grafana`
*   **SERVICE**: `grafana`
*   **IMAGE**: `grafana/grafana:latest`
*   **PORTS**: `3001:3000` (mapped to local port 3001 to prevent conflicts with Langfuse)
*   **VOLUMES**: `grafana_data:/var/lib/grafana`
*   **ENVIRONMENT**:  
    `GF_SECURITY_ADMIN_PASSWORD=admin`
*   **DEPENDS_ON**:  
    *   `prometheus` (condition: `service_healthy`)
*   **HEALTHCHECK**:  
    `test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]`  
    `interval: 30s`  
    `timeout: 5s`  
    `retries: 3`
*   **RESTART**: `unless-stopped`

---

## 8.2 Development vs. Production Differences

| Component / Layer | Local Development (`docker-compose.yml`) | Production (`docker-compose.prod.yml` / Render) |
|---|---|---|
| **FastAPI Backend** | Local build in Docker container (hot-reload enabled). | Render Web Service (linked to production branch on GitHub). |
| **Next.js Frontend** | Run locally (`npm run dev`) or dockerized. | Vercel Free Tier (automatic deployments via GitHub integration). |
| **PostgreSQL Database** | PostgreSQL container with local volume mounts. | Supabase Free Tier (Managed PostgreSQL 16 + pgvector). |
| **Redis Cache / Broker** | Redis container with in-memory persistence. | Upstash Redis Free Tier (Serverless Redis over TLS). |
| **Object Storage** | Local MinIO container (mapped S3 API endpoints). | Cloudflare R2 (S3-compatible bucket, zero-egress fees). |
| **LLM Proxy Engine** | Local Docker service executing LiteLLM. | LiteLLM Proxy deployed to Render or direct API routing. |
| **Observability Telemetry** | Local Langfuse, Prometheus, Grafana containers. | Self-hosted Langfuse on Render; Prometheus/Grafana disabled. |

---

## 8.3 Startup Sequence

To prevent initialization failures, services boot in a sequential chain using `depends_on` healthchecks.

### Startup Order Flow Chart
```
[ postgres ]         [ redis ]         [ minio ]
     │                   │                 │
     ├─► must be healthy ┼─────────────────┤
     │                                     │
     ▼                                     ▼
[ langfuse ]                           [ backend ]
                                           │
                                           ├─► must be healthy
                                           │
                                           ▼
                                       [ worker ]
                                           │
                                           ▼
                                     [ prometheus ]
                                           │
                                           ▼
                                      [ grafana ]
```

### Sequence Breakdown:
1.  **Level 1 (Foundations)**: `postgres`, `redis`, and `minio` start first. They run independent healthcheck scripts (`pg_isready`, `redis-cli ping`, and MinIO health APIs) to confirm readiness.
2.  **Level 2 (Telemetry & API)**:
    *   `langfuse` starts once `postgres` is healthy.
    *   `backend` starts once `postgres`, `redis`, and `minio` are all verified healthy.
3.  **Level 3 (Workloads)**:
    *   `worker` starts once `backend` is verified healthy. This ensures database tables are initialized (FastAPI database migrations run at start) before the worker connects.
4.  **Level 4 (Monitoring)**:
    *   `prometheus` and `grafana` start last, attaching scrape hooks to the healthy backend metrics endpoint.
