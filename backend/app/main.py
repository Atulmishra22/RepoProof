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
from app.models import User, Repository, AnalysisJob, JobStatus, AnalysisStatus

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


@router.post("/repositories/{id}/analyze", tags=["analysis"])
async def trigger_repository_analysis(
    id: str,
    db: Session = Depends(get_db)
):
    """
    Triggers the LangGraph analysis pipeline in the background for a repository.
    Creates a new analysis job and updates repository status.
    """
    # 1. Fetch Repository record
    repo = db.query(Repository).filter(Repository.id == id).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )

    # 2. Check if a job is already queued or active for this repo
    active_job = db.query(AnalysisJob).filter(
        AnalysisJob.repository_id == repo.id,
        AnalysisJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
    ).first()
    
    if active_job:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        updated_at = active_job.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        delta = now - updated_at
        if delta.total_seconds() > 300:  # 5 minutes
            active_job.status = JobStatus.FAILED
            active_job.error_message = "Job stalled or interrupted (timeout)."
            active_job.completed_at = datetime.utcnow()
            repo.analysis_status = AnalysisStatus.FAILED
            db.commit()
            active_job = None
            
    if active_job:
        return {
            "status": "already_active",
            "message": f"An analysis job ({active_job.id}) is already active for this repository.",
            "job_id": str(active_job.id)
        }

    # 3. Create AnalysisJob record
    import uuid
    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        repository_id=repo.id,
        user_id=repo.user_id,
        langgraph_thread_id=job_id,
        status=JobStatus.QUEUED
    )
    db.add(job)
    
    # 4. Set Repository status to ANALYZING
    repo.analysis_status = AnalysisStatus.ANALYZING
    db.commit()

    # 5. Trigger background Celery task
    from app.tasks import run_analysis_workflow_task
    try:
        task = run_analysis_workflow_task.delay(str(repo.id), str(job_id))
        
        # 6. Save Celery Task ID in DB
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "celery_task_id": task.id
        })
        db.commit()
    except Exception as e:
        # Fallback cleanup on celery fail
        repo.analysis_status = AnalysisStatus.FAILED
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.FAILED,
            "error_message": f"Failed to dispatch worker task: {str(e)}"
        })
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue background task: {str(e)}"
        )

    return {
        "status": "success",
        "message": "Analysis workflow queued successfully.",
        "job_id": str(job_id)
    }


@router.get("/repositories/{id}/analysis/{job_id}", tags=["analysis"])
async def get_repository_analysis_status(
    id: str,
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Returns the status and execution metrics of the repository analysis job.
    """
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found."
        )

    return {
        "job_id": str(job.id),
        "repository_id": str(job.repository_id),
        "status": job.status.value if hasattr(job.status, 'value') else job.status,
        "current_node": job.current_node,
        "error_message": job.error_message,
        "llm_tokens_used": job.llm_tokens_used,
        "llm_cost_usd": float(job.llm_cost_usd),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat()
    }


@router.get("/repositories/{id}/analysis-result", tags=["analysis"])
async def get_repository_analysis_result(
    id: str,
    db: Session = Depends(get_db)
):
    """
    Fetches the compiled analysis result (extracted facts, suggested questions, and cost metrics)
    from MinIO storage for a given repository.
    """
    repo = db.query(Repository).filter(Repository.id == id).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )

    from app.analysis_graph import get_s3_client
    try:
        s3 = get_s3_client()
        bucket_name = "repoproof-data"
        s3_key = f"repos/{id}/analysis_result.json"
        
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        result_data = json.loads(response["Body"].read().decode("utf-8"))
        return result_data
    except s3.exceptions.NoSuchKey:
        # Fallback if result has not been uploaded yet
        return {
            "facts": [],
            "suggested_questions": [],
            "llm_tokens_used": 0,
            "llm_cost_usd": 0.0
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch analysis result: {str(e)}"
        )


app.include_router(router)


