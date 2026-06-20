from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
import redis

from app.database import get_db
from app.redis_client import get_redis

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

app.include_router(router)
