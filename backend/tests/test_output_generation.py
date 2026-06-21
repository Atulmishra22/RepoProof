import uuid
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, Repository, AnalysisJob, GeneratedOutput, OutputType, JobStatus, AnalysisStatus, DownloadFormat, OutputDownload

client = TestClient(app)

@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture(scope="module")
def setup_test_data(db_session):
    # 1. Create a dummy user
    test_user = db_session.query(User).filter(User.email == "test_outputs@repoproof.com").first()
    if not test_user:
        test_user = User(
            id=uuid.uuid4(),
            email="test_outputs@repoproof.com",
            github_username="test_outputs_dev",
            auth_provider="github",
            is_active=True
        )
        db_session.add(test_user)
        db_session.commit()
        db_session.refresh(test_user)

    # 2. Create a dummy repository
    repo = Repository(
        id=uuid.uuid4(),
        user_id=test_user.id,
        github_url="https://github.com/test_outputs_dev/dummy-repo",
        github_repo_id=123456789,
        owner="test_outputs_dev",
        name="dummy-repo",
        default_branch="main",
        star_count=5,
        analysis_status=AnalysisStatus.COMPLETE
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # 3. Create a dummy analysis job
    job = AnalysisJob(
        id=uuid.uuid4(),
        repository_id=repo.id,
        user_id=test_user.id,
        langgraph_thread_id=repo.id,
        status=JobStatus.COMPLETE
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    # 4. Create dummy generated outputs
    outputs = []
    
    # Resume LaTeX/PDF
    resume_out = GeneratedOutput(
        id=uuid.uuid4(),
        analysis_job_id=job.id,
        output_type=OutputType.RESUME_BULLETS,
        content="\\documentclass{article}\\begin{document}Test Resume\\end{document}",
        version=1,
        is_current_version=True,
        llm_model_used="gpt-4o-mini",
        minio_object_key=f"outputs/{test_user.id}/{job.id}/resume.pdf"
    )
    db_session.add(resume_out)
    outputs.append(resume_out)

    # LinkedIn Description
    linkedin_out = GeneratedOutput(
        id=uuid.uuid4(),
        analysis_job_id=job.id,
        output_type=OutputType.LINKEDIN_DESC,
        content="This is a test LinkedIn summary for dummy-repo.",
        version=1,
        is_current_version=True,
        llm_model_used="gpt-4o-mini",
        minio_object_key=f"outputs/{test_user.id}/{job.id}/linkedin.md"
    )
    db_session.add(linkedin_out)
    outputs.append(linkedin_out)

    db_session.commit()
    
    for o in outputs:
        db_session.refresh(o)

    yield {
        "user": test_user,
        "repo": repo,
        "job": job,
        "outputs": outputs
    }

    # Clean up test data
    for o in outputs:
        db_session.delete(o)
    db_session.delete(job)
    db_session.delete(repo)
    db_session.delete(test_user)
    db_session.commit()


def test_get_repository_outputs(setup_test_data):
    repo_id = setup_test_data["repo"].id
    response = client.get(f"/api/v1/repositories/{repo_id}/outputs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    types = [o["output_type"] for o in data]
    assert "resume_bullets" in types
    assert "linkedin_desc" in types


def test_get_output_by_id(setup_test_data):
    output_id = setup_test_data["outputs"][0].id
    response = client.get(f"/api/v1/outputs/{output_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(output_id)
    assert "\\documentclass" in data["content"]


def test_download_output_file(setup_test_data):
    output_id = setup_test_data["outputs"][0].id
    response = client.get(f"/api/v1/outputs/{output_id}/download")
    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert "repoproof-data" in data["download_url"]
    assert "resume.pdf" in data["download_url"]


def test_download_output_file_tex(setup_test_data):
    output_id = setup_test_data["outputs"][0].id
    response = client.get(f"/api/v1/outputs/{output_id}/download?format=tex")
    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert "resume.tex" in data["download_url"]


def test_export_outputs_zip(setup_test_data):
    repo_id = setup_test_data["repo"].id
    response = client.get(f"/api/v1/repositories/{repo_id}/outputs/export")
    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert "export.zip" in data["download_url"]
