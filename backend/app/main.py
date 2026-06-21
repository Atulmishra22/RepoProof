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
                "latest_job_id": (
                    lambda val: str(val) if val else None
                )(
                    db.execute(
                        text("SELECT id FROM analysis_jobs WHERE repository_id = :repo_id ORDER BY created_at DESC LIMIT 1"),
                        {"repo_id": r.id}
                    ).scalar()
                ),
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
    `GET /api/v1/repositories/{id}/analysis-result`
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


# ==========================================
# Phase 5: Human-In-The-Loop Reviews & WebSockets
# ==========================================
import logging
import base64
import os
import httpx
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as async_redis
import asyncio

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")
        
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {e}")

manager = ConnectionManager()

# Background Redis PubSub listener for WebSocket status updates
async def redis_pubsub_listener():
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    logger.info(f"Starting Redis Pub/Sub listener on {redis_url}...")
    while True:
        try:
            r = async_redis.from_url(redis_url)
            pubsub = r.pubsub()
            await pubsub.subscribe("review_status_channel")
            logger.info("Subscribed to Redis channel review_status_channel successfully.")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    try:
                        data = json.loads(message["data"])
                        logger.info(f"Broadcasting Redis message to WebSockets: {data}")
                        await manager.broadcast(data)
                    except Exception as e:
                        logger.error(f"Error parsing/broadcasting message: {e}")
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis PubSub listener error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_pubsub_listener())

@app.websocket("/api/v1/ws/reviews")
async def websocket_reviews_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


class FactsUpdatePayload(BaseModel):
    facts: List[Dict[str, Any]]

@router.patch("/reviews/{job_id}/facts", tags=["analysis"])
async def update_facts_and_resume(
    job_id: str,
    payload: FactsUpdatePayload,
    db: Session = Depends(get_db)
):
    """
    Updates the LangGraph checkpointer state with the reviewed facts and resumes the workflow.
    """
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found."
        )
        
    from app.tasks import resume_analysis_workflow_task
    try:
        # Trigger Celery task to update state and resume
        resume_analysis_workflow_task.delay(str(job.id), payload.facts)
        return {
            "status": "success",
            "message": "Analysis resume triggered successfully with updated facts."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger resume: {str(e)}"
        )


class ChatRequestPayload(BaseModel):
    message: str
    facts: List[Dict[str, Any]]

async def fetch_github_file(owner: str, repo: str, path: str, token: Optional[str] = None) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                content_b64 = data.get("content", "")
                if content_b64:
                    return base64.b64decode(content_b64).decode("utf-8", errors="ignore")
            return ""
        except Exception as e:
            logger.error(f"Error fetching github file {path}: {e}")
            return ""

@router.post("/reviews/{job_id}/chat", tags=["analysis"])
async def review_chat_interaction(
    job_id: str,
    payload: ChatRequestPayload,
    db: Session = Depends(get_db)
):
    """
    Chat assistant inside the Human-in-the-Loop review editor.
    Uses context from key repository files and current facts to suggest edits.
    """
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found."
        )
        
    repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )
        
    # Get GITHUB_TOKEN
    github_token = os.environ.get("GITHUB_TOKEN")
    
    # Identify key files from the file tree if we have them in MinIO
    from app.analysis_graph import get_s3_client, LITELLM_PROXY_URL, MODEL_NAME
    s3 = get_s3_client()
    bucket_name = "repoproof-data"
    
    file_tree = {}
    try:
        s3_resp = s3.get_object(Bucket=bucket_name, Key=f"repos/{repo.id}/file_tree.json")
        file_tree = json.loads(s3_resp["Body"].read().decode("utf-8"))
    except Exception:
        pass
        
    # Read up to 3 files
    key_files_context = ""
    candidate_paths = ["package.json", "pyproject.toml", "requirements.txt", "main.py", "app.py"]
    # Add files from tree if available and matching candidates
    matched_paths = []
    for path in file_tree.keys():
        filename = os.path.basename(path).lower()
        if filename in candidate_paths:
            matched_paths.append(path)
            if len(matched_paths) >= 3:
                break
                
    if not matched_paths:
        matched_paths = candidate_paths[:2]
        
    for path in matched_paths:
        file_content = await fetch_github_file(repo.owner, repo.name, path, github_token)
        if file_content:
            key_files_context += f"--- FILE: {path} ---\n{file_content[:2000]}\n\n"
            
    system_prompt = (
        "You are an expert Senior Technical Recruiter and AI pairing partner helping the user refine their repository analysis facts.\n"
        "Analyze the user's message alongside the current list of candidate facts and the repository's key files context.\n\n"
        "Provide professional, helpful advice. If the user asks to modify a claim, write a revised version of that claim in active voice starting with a strong verb.\n"
        "If the user asks to create a new claim, design it strictly based on the codebase details and return it in this exact format:\n"
        "Category: [technology_used | architecture_pattern | complexity_metric | contribution | performance_optimization | security_hardening | cost_saving]\n"
        "Claim: [Strong action-oriented resume bullet point]\n"
        "Source File: [relative filepath]\n"
        "Snippet: [code snippet]\n"
        "ATS Impact: [why it demonstrates senior capacity]\n"
    )
    
    user_prompt = (
        f"Key codebase files context:\n{key_files_context}\n\n"
        f"Current candidate facts:\n{json.dumps(payload.facts, indent=2)}\n\n"
        f"User message: {payload.message}"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LITELLM_PROXY_URL}/v1/chat/completions",
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "temperature": 0.3
                },
                timeout=40.0
            )
            response.raise_for_status()
            resp_data = response.json()
            reply = resp_data["choices"][0]["message"]["content"]
            return {"reply": reply}
    except Exception as e:
        logger.exception(f"Error in review chat LLM call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI response: {str(e)}"
        )


app.include_router(router)


