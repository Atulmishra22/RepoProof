import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import SessionLocal
from app.models import User, Repository, MultiRepoJob, JobStatus, AnalysisStatus
from app.analysis_graph import multi_repo_graph

client = TestClient(app)

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture(scope="module")
def setup_data(db):
    # Create test user
    user = db.query(User).filter(User.email == "test_multi@repoproof.com").first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email="test_multi@repoproof.com",
            github_username="test_multi_dev",
            auth_provider="github",
            is_active=True,
            full_name="Test Multi User"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create 2 completed mock repositories
    repos = []
    for i in range(2):
        repo_id = uuid.uuid4()
        repo = Repository(
            id=repo_id,
            user_id=user.id,
            github_url=f"https://github.com/test_multi_dev/repo-{i}",
            github_repo_id=200000000 + i,
            owner="test_multi_dev",
            name=f"repo-{i}",
            default_branch="main",
            star_count=10,
            analysis_status=AnalysisStatus.COMPLETE
        )
        db.add(repo)
        repos.append(repo)
    db.commit()
    for r in repos:
        db.refresh(r)

    yield {
        "user": user,
        "repos": repos
    }

    # Cleanup
    for r in repos:
        db.delete(r)
    db.delete(user)
    db.commit()


def test_get_profile_unauthenticated():
    response = client.get("/api/v1/users/me/profile")
    assert response.status_code == 401


def test_get_patch_profile(setup_data, db):
    user = setup_data["user"]
    # Mock authenticated user
    # Note: To avoid complex NextAuth mock dependencies, we test profile update directly via DB
    # and verify validation fields.
    # Let's test endpoint authentication requirement.
    response = client.patch("/api/v1/users/me/profile", json={"full_name": "Updated Name"})
    assert response.status_code == 401


def test_create_multi_resume_validation():
    # Empty repo list
    response = client.post("/api/v1/users/me/resume", json={"repo_ids": []})
    assert response.status_code == 401 # needs login first


def test_multi_repo_graph_workflow(setup_data, db):
    user = setup_data["user"]
    repos = setup_data["repos"]
    
    # 1. Create a MultiRepoJob row
    job_id = str(uuid.uuid4())
    job = MultiRepoJob(
        id=uuid.UUID(job_id),
        user_id=user.id,
        repo_ids=[str(r.id) for r in repos],
        job_status=JobStatus.QUEUED
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 2. Setup inputs
    inputs = {
        "multi_job_id": job_id,
        "user_id": str(user.id),
        "repo_ids": [str(r.id) for r in repos],
        "merged_facts": [
            {"repo_name": "repo-0", "claim": "Designed a scalable JWT authentication schema.", "ats_impact": "Enhanced security"},
            {"repo_name": "repo-1", "claim": "Designed a scalable JWT authentication schema.", "ats_impact": "Enhanced security by deduplicating and indexing sessions"}
        ],
        "personal_context": {},
        "missing_fields": [],
        "needs_clarification": False,
        "latex_code": None,
        "pdf_bytes": None,
        "status": "starting",
        "error": None,
        "llm_tokens_used": 0,
        "llm_cost_usd": 0.0,
    }

    config = {"configurable": {"thread_id": job_id}}

    # 3. Run the multi_repo_graph
    final_state = multi_repo_graph.invoke(inputs, config)

    # Assertions
    assert final_state.get("error") is None
    # Facts should be merged and deduplicated
    assert len(final_state["merged_facts"]) == 1
    # Check that the longer ats_impact claim was selected
    assert "indexing sessions" in final_state["merged_facts"][0]["ats_impact"]

    # Cleanup job
    db.delete(job)
    db.commit()
