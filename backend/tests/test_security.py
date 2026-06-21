import uuid
import json
import pytest
import sqlalchemy as sa
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.redis_client import redis_client
from app.models import User, Session as SessionModel, SubscriptionTier, Repository, AnalysisStatus, GeneratedOutput, OutputType, JobStatus

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture(autouse=True)
def clean_redis():
    yield
    # Clean keys that might have been set
    keys = redis_client.keys("session:*") + redis_client.keys("user_sessions:*") + redis_client.keys("rate_limit:*")
    if keys:
        redis_client.delete(*keys)

def test_auth_missing_token():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "Session token is missing" in response.json()["detail"]

def test_auth_expired_session(db):
    # 1. Create a user
    user = User(
        id=uuid.uuid4(),
        email="expired_test@repoproof.com",
        github_username="expired_test_dev",
        auth_provider="credentials",
        is_active=True
    )
    db.add(user)
    db.commit()

    # 2. Create an expired session
    session_token = "expired-token-123"
    db_session = SessionModel(
        id=uuid.uuid4(),
        session_token=session_token,
        user_id=user.id,
        expires=datetime.utcnow() - timedelta(hours=1)
    )
    db.add(db_session)
    db.commit()

    # 3. Call endpoint with expired session in header
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert response.status_code == 401
    assert "Session has expired" in response.json()["detail"]

    # Verify session deleted from DB
    deleted_session = db.query(SessionModel).filter(SessionModel.session_token == session_token).first()
    assert deleted_session is None

    # Cleanup
    db.delete(user)
    db.commit()

def test_session_caching_and_hit(db):
    # 1. Create user and active session
    user = User(
        id=uuid.uuid4(),
        email="caching_test@repoproof.com",
        github_username="caching_test_dev",
        auth_provider="credentials",
        is_active=True
    )
    db.add(user)
    db.commit()

    session_token = "valid-token-456"
    db_session = SessionModel(
        id=uuid.uuid4(),
        session_token=session_token,
        user_id=user.id,
        expires=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(db_session)
    db.commit()

    # 2. First call: Cache miss. Queries DB, caches in Redis.
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "caching_test@repoproof.com"

    # Verify cached in Redis with a TTL
    redis_key = f"session:{session_token}"
    assert redis_client.exists(redis_key)
    ttl = redis_client.ttl(redis_key)
    assert 0 < ttl <= 3600

    cached_data = json.loads(redis_client.get(redis_key))
    assert cached_data["user_id"] == str(user.id)

    # 3. Temporarily delete session from DB to prove second call hits Redis
    db.delete(db_session)
    db.commit()

    response2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert response2.status_code == 200
    assert response2.json()["email"] == "caching_test@repoproof.com"

    # Cleanup
    db.delete(user)
    db.commit()

def test_signout(db):
    user = User(
        id=uuid.uuid4(),
        email="signout_test@repoproof.com",
        github_username="signout_test_dev",
        auth_provider="credentials",
        is_active=True
    )
    db.add(user)
    db.commit()

    session_token = "signout-token"
    db_session = SessionModel(
        id=uuid.uuid4(),
        session_token=session_token,
        user_id=user.id,
        expires=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(db_session)
    db.commit()

    # Perform active request to populate cache
    client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert redis_client.exists(f"session:{session_token}")

    # Sign out
    signout_resp = client.post(
        "/api/v1/auth/signout",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert signout_resp.status_code == 200
    assert signout_resp.json()["status"] == "success"

    # Verify session deleted from both Redis and Postgres
    assert not redis_client.exists(f"session:{session_token}")
    assert db.query(SessionModel).filter(SessionModel.session_token == session_token).first() is None

    # Cleanup
    db.delete(user)
    db.commit()

def test_profile_update_invalidates_cache(db):
    user = User(
        id=uuid.uuid4(),
        email="update_test@repoproof.com",
        github_username="update_test_dev",
        auth_provider="credentials",
        subscription_tier=SubscriptionTier.FREE,
        is_active=True
    )
    db.add(user)
    db.commit()

    session_token = "update-token"
    db_session = SessionModel(
        id=uuid.uuid4(),
        session_token=session_token,
        user_id=user.id,
        expires=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(db_session)
    db.commit()

    # Populate cache
    client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert redis_client.exists(f"session:{session_token}")

    # Update profile tier to PRO
    update_resp = client.patch(
        "/api/v1/users/me",
        json={"subscription_tier": "pro"},
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["user"]["subscription_tier"] == "pro"

    # Verify cache is invalidated (key deleted from Redis)
    assert not redis_client.exists(f"session:{session_token}")

    # Subsequent request should re-fetch from database and succeed
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["subscription_tier"] == "pro"

    # Cleanup
    db.delete(db_session)
    db.delete(user)
    db.commit()

def test_rate_limiting_free_and_pro(db):
    # 1. Create a FREE user
    free_user = User(
        id=uuid.uuid4(),
        email="free_rate@repoproof.com",
        github_username="free_rate_dev",
        auth_provider="credentials",
        subscription_tier=SubscriptionTier.FREE,
        is_active=True
    )
    db.add(free_user)
    
    # Create Repository for the FREE user
    repo = Repository(
        id=uuid.uuid4(),
        user_id=free_user.id,
        github_url="https://github.com/free_rate_dev/test-repo",
        github_repo_id=987654321,
        owner="free_rate_dev",
        name="test-repo",
        default_branch="main",
        star_count=10,
        analysis_status=AnalysisStatus.PENDING
    )
    db.add(repo)
    db.commit()

    session_token = "free-rate-token"
    db_session = SessionModel(
        id=uuid.uuid4(),
        session_token=session_token,
        user_id=free_user.id,
        expires=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(db_session)
    db.commit()

    # Call endpoint `/analyze` 5 times (should succeed)
    headers = {"Authorization": f"Bearer {session_token}"}
    for i in range(5):
        resp = client.post(f"/api/v1/repositories/{repo.id}/analyze", headers=headers)
        assert resp.status_code in [200, 400, 500] # RateLimiter should not block first 5
        
    # The 6th request should fail with 429 Too Many Requests
    resp_limit = client.post(f"/api/v1/repositories/{repo.id}/analyze", headers=headers)
    assert resp_limit.status_code == 429
    assert "Rate limit exceeded" in resp_limit.json()["detail"]

    # 2. Upgrade user to PRO
    free_user.subscription_tier = SubscriptionTier.PRO
    db.commit()

    # Clear rate limit and session caches
    redis_client.delete(f"rate_limit:/analyze:{free_user.id}")
    redis_client.delete(f"session:{session_token}")

    # Call /analyze 6 times (should succeed beyond FREE limit)
    for i in range(6):
        resp = client.post(f"/api/v1/repositories/{repo.id}/analyze", headers=headers)
        assert resp.status_code != 429

    # Cleanup jobs created by tests
    db.execute(sa.text("DELETE FROM analysis_jobs WHERE user_id = :uid"), {"uid": free_user.id})
    db.execute(sa.text("DELETE FROM usage_metrics WHERE user_id = :uid"), {"uid": free_user.id})
    db.delete(db_session)
    db.delete(repo)
    db.delete(free_user)
    db.commit()
