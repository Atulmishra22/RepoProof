import os
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Setup a Redis client with response decoding enabled
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def get_redis():
    """Dependency injection helper for Redis in FastAPI routes."""
    return redis_client
