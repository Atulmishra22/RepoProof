# RepoProof Backend 🐍

The RepoProof backend is built using **FastAPI** for HTTP/WebSocket requests, **Celery** for background task execution, and **LangGraph** for orchestrating the analysis workflow.

---

## 📂 Codebase Structure

```text
backend/
├── alembic/            # Database migrations
├── app/                # Main application folder
│   ├── main.py         # REST and WebSocket endpoints
│   ├── models.py       # SQLAlchemy database models
│   ├── tasks.py        # Celery background tasks
│   ├── analysis_graph.py # LangGraph workflow configuration
│   ├── metrics.py      # Prometheus metrics definitions
│   ├── logging_config.py # structlog JSON structured logs configuration
│   └── database.py     # Database session setup
├── tests/              # Security and output generation tests
└── Dockerfile          # Docker configuration
```

---

## 🗄️ Database Migrations

Database tables are managed using **Alembic**. To apply pending migrations inside the postgres container, run:

```bash
docker exec -it repoproof-backend alembic upgrade head
```

To autogenerate a new migration script after modifying models:

```bash
docker exec -it repoproof-backend alembic revision --autogenerate -m "description_of_changes"
```

---

## 🧪 Running Tests

The test suite contains security, logic, and graph execution tests. Run them inside the backend container environment:

```bash
docker exec repoproof-backend python -m pytest
```
