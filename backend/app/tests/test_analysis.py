import unittest
import os
import json
import uuid
from app.database import SessionLocal
from app.models import User, Repository, AnalysisJob, JobStatus, AnalysisStatus
from app.analysis_graph import analysis_graph, get_s3_client

class TestAnalysisPipeline(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Find a test user and repo
        self.user = self.db.query(User).filter(User.github_username == "Atulmishra22").first()
        if not self.user:
            # Create user if not exists
            self.user = User(
                email="atulmishralearn@gmail.com",
                github_username="Atulmishra22",
                auth_provider="github",
                is_active=True
            )
            self.db.add(self.user)
            self.db.commit()
            self.db.refresh(self.user)

        self.repo = self.db.query(Repository).filter(Repository.user_id == self.user.id).first()
        if not self.repo:
            # Create a mock repository
            self.repo = Repository(
                user_id=self.user.id,
                github_url="https://github.com/Atulmishra22/contentflow",
                github_repo_id=1125494378,
                owner="Atulmishra22",
                name="contentflow",
                default_branch="main",
                primary_language="Python",
                languages={"Python": 1000},
                star_count=0,
                analysis_status=AnalysisStatus.PENDING
            )
            self.db.add(self.repo)
            self.db.commit()
            self.db.refresh(self.repo)

    def tearDown(self):
        self.db.close()

    def test_run_analysis_graph_directly(self):
        job_id = str(uuid.uuid4())
        
        # Initialize an AnalysisJob row
        job = AnalysisJob(
            id=job_id,
            repository_id=self.repo.id,
            user_id=self.user.id,
            langgraph_thread_id=job_id,
            status=JobStatus.QUEUED
        )
        self.db.add(job)
        self.db.commit()
        
        # Input state
        inputs = {
            "repository_id": str(self.repo.id),
            "github_url": self.repo.github_url,
            "default_branch": self.repo.default_branch,
            "local_path": "",
            "file_tree": {},
            "extracted_facts": [],
            "status": "queued",
            "error": None
        }
        
        # Configure thread for checkpointer
        config = {"configurable": {"thread_id": job_id}}
        
        # Run graph
        print(f"Running LangGraph pipeline for repository {self.repo.name}...")
        final_state = analysis_graph.invoke(inputs, config)
        
        # Assertions
        self.assertIsNone(final_state.get("error"))
        self.assertEqual(final_state["status"], "complete")
        self.assertGreater(len(final_state["file_tree"]), 0)
        
        # Check MinIO
        s3 = get_s3_client()
        bucket_name = "repoproof-data"
        s3_key = f"repos/{self.repo.id}/file_tree.json"
        
        response = s3.get_object(Bucket=bucket_name, Key=s3_key)
        file_tree_content = json.loads(response["Body"].read().decode("utf-8"))
        self.assertEqual(len(file_tree_content), len(final_state["file_tree"]))
        print("Integration test passed successfully!")

if __name__ == "__main__":
    unittest.main()
