from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
import redis
import json
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.redis_client import get_redis, redis_client
from app.models import User, Repository

app = FastAPI(
    title="RepoProof API",
    description="GitHub Repository Intelligence Platform",
    version="1.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Restrict this to production domain in v2
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")

@router.get("/health", tags=["health"])
async def health_check(
    db: Session = Depends(get_db),
    redis_conn: redis.Redis = Depends(get_redis)
):
    health_status = {
        "status": "healthy",
        "database": "unhealthy",
        "redis": "unhealthy"
    }
    is_healthy = True
    
    # Check Database
    try:
        db.execute(text("SELECT 1"))
        health_status["database"] = "healthy"
    except Exception as e:
        is_healthy = False
        health_status["database"] = f"error: {str(e)}"

    # Check Redis
    try:
        if redis_conn.ping():
            health_status["redis"] = "healthy"
        else:
            is_healthy = False
            health_status["redis"] = "ping failed"
    except Exception as e:
        is_healthy = False
        health_status["redis"] = f"error: {str(e)}"

    if not is_healthy:
        health_status["status"] = "unhealthy"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=health_status
        )
        
    return health_status


class UserIngestRequest(BaseModel):
    username: str


@router.post("/users/ingest", tags=["users"])
async def ingest_user(
    request: UserIngestRequest
):
    """
    Triggers the background Celery task to ingest a user's GitHub profile and repositories.
    """
    from app.tasks import ingest_user_profile_task
    try:
        # Trigger Celery task asynchronously
        task = ingest_user_profile_task.delay(request.username)
        return {
            "status": "success",
            "message": f"Ingestion task started for user {request.username}",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start task: {str(e)}"
        )


@router.get("/repositories", tags=["repositories"])
async def get_repositories(
    username: str = "Atulmishra22",
    db: Session = Depends(get_db)
):
    """
    Fetches the list of repositories from the database for the given username.
    Defaults to 'Atulmishra22'. Also returns cached user profile details from Redis if available.
    """
    # Fetch user
    user = db.query(User).filter(User.github_username == username).first()
    if not user:
        return {
            "repositories": [],
            "profile": None
        }

    # Fetch repos
    repos = db.query(Repository).filter(Repository.user_id == user.id).all()

    # Fetch profile details cache from Redis
    profile_cache = redis_client.get(f"github_profile:{username}")
    profile_data = None
    if profile_cache:
        try:
            profile_data = json.loads(profile_cache)
        except Exception:
            pass

    if not profile_data:
        # Fallback profile details if cache is empty
        profile_data = {
            "username": user.github_username,
            "name": user.github_username,
            "email": user.email,
            "bio": "",
            "avatar_url": "",
            "github_id": None,
            "readme": None
        }

    return {
        "repositories": [
            {
                "id": str(r.id),
                "github_url": r.github_url,
                "github_repo_id": r.github_repo_id,
                "owner": r.owner,
                "name": r.name,
                "default_branch": r.default_branch,
                "primary_language": r.primary_language,
                "languages": r.languages,
                "star_count": r.star_count,
                "analysis_status": r.analysis_status.value if hasattr(r.analysis_status, 'value') else r.analysis_status,
                "last_analyzed_at": r.last_analyzed_at.isoformat() if r.last_analyzed_at else None,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat()
            }
            for r in repos
        ],
        "profile": profile_data
    }


app.include_router(router)

