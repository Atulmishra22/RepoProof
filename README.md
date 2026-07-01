# RepoProof 🚀

RepoProof is an advanced **Repository Intelligence Platform** designed to analyze GitHub repositories, extract verifiable technical achievements (facts) with source code citations, and compile professional developer documents (LaTeX resumes, LinkedIn summaries, portfolio landing pages, and polished READMEs) using a Human-in-the-Loop (HiTL) workflow.

---

## 🛠️ Technology Stack

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS, Zustand
- **Backend**: FastAPI, Celery, SQLAlchemy 2.0, Alembic
- **Orchestration**: LangGraph 0.2+ with PostgreSQL checkpointing
- **Database**: Supabase PostgreSQL 16 with `pgvector`
- **Caching & Broker**: Redis 7
- **Object Storage**: MinIO / Cloudflare R2 (S3-compatible)
- **AI Gateway**: LiteLLM Proxy routing to Gemini API (`gemini-3.1-flash-lite`)
- **Observability**: Prometheus metrics, JSON structured logging (`structlog`), and Langfuse v3 tracing

---

## 📂 Project Structure

```text
RepoProof/
├── backend/            # FastAPI backend, Celery workers, and Alembic migrations
├── frontend/           # Next.js 16 React client & BFF
├── litellm/            # LiteLLM Proxy configuration (config.yaml)
├── docs/               # System architecture design blueprints and checklist
├── .env.example        # Environment variables setup template
└── docker-compose.yml  # Docker Compose orchestration
```

---

## ⚙️ Setup & Configuration

### 1. Environment Variables
Create a `.env` file in the root directory by copying `.env.example`:

```bash
cp .env.example .env
```

Populate the following variables inside `.env`:
```env
# Gemini API Credentials (required by LiteLLM)
GEMINI_API_KEY=your_gemini_api_key_here

# Langfuse Configuration
LANGFUSE_INIT_USER_EMAIL=dev@repoproof.com
LANGFUSE_INIT_USER_PASSWORD=strong_dev_password_123
LANGFUSE_PUBLIC_KEY=pk-lf-dev
LANGFUSE_SECRET_KEY=sk-lf-dev
```

---

## 🚀 Running the Platform

All core services run inside Docker containers. Start them by running the following command inside your WSL terminal:

```bash
docker compose up -d
```

This boots:
1. **PostgreSQL** (`localhost:5433` / container: `postgres:5432`)
2. **Redis** (`localhost:6379`)
3. **MinIO Console** (`localhost:9001` / S3 API: `localhost:9000`)
4. **FastAPI Backend** (`localhost:8000`)
5. **Celery Worker** (running background analysis graphs)
6. **LiteLLM Proxy** (`localhost:4000`)
7. **Langfuse Dashboard** (`localhost:3030`)
8. **Flower Celery Monitor** (`localhost:5555`)

---

## 🧪 Testing & Verification

### 1. Backend Unit Tests
Install test dependencies and execute `pytest` inside the backend container:

```bash
# Install pytest inside container (if not already installed)
docker exec repoproof-backend uv pip install --system pytest pytest-asyncio

# Execute pytest
docker exec repoproof-backend python -m pytest
```

### 2. Frontend E2E Tests
Start the Next.js frontend dev server and execute the Playwright integration tests:

```bash
# Inside frontend/ directory
npm run dev

# Run E2E test suite
npm run test:e2e
```

---

## 📈 Monitoring & Metrics

- **Prometheus Metrics**: Scrape metrics on `http://localhost:8000/metrics`.
- **Traces & Logs**: Open Langfuse dashboard at `http://localhost:3030` to inspect spans, LLM tokens, and latency traces.
