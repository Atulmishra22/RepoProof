import json
import logging
from datetime import datetime
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import User, Repository
from app.github_client import GitHubSyncClient, GitHubClientError
from app.redis_client import redis_client

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.ingest_user_profile_task")
def ingest_user_profile_task(username: str):
    """
    Background task to fetch user details, profile README, and public repositories from GitHub.
    Saves User/Repositories to PostgreSQL, and caches the parsed profile in Redis.
    """
    logger.info(f"Starting ingestion task for user: {username}")
    db = SessionLocal()
    try:
        # Initialize GitHub client
        import os
        token = os.environ.get("GITHUB_TOKEN")
        gh = GitHubSyncClient(token=token)

        # 1. Fetch User profile details
        try:
            profile = gh.get_user_profile(username)
        except GitHubClientError as e:
            logger.error(f"Failed to fetch profile for user {username}: {e}")
            return {"status": "error", "message": f"Failed to fetch profile: {str(e)}"}

        email = profile.get("email")
        if not email:
            email = f"{username}@users.noreply.github.com"
        
        avatar_url = profile.get("avatar_url", "")
        bio = profile.get("bio", "")
        name = profile.get("name", "")
        github_id = profile.get("id")

        # 2. Fetch special profile README content
        readme_content = None
        try:
            readme_content = gh.get_profile_readme(username)
        except Exception as e:
            logger.warning(f"Error fetching profile README for {username}: {e}")

        # 3. Fetch list of public repositories
        try:
            repos = gh.list_repositories(username)
        except GitHubClientError as e:
            logger.error(f"Failed to fetch repositories for user {username}: {e}")
            return {"status": "error", "message": f"Failed to fetch repositories: {str(e)}"}

        # 4. Upsert User in database
        user = db.query(User).filter(User.github_username == username).first()
        if not user:
            # Try to match by email as fallback
            user = db.query(User).filter(User.email == email).first()
            
        if not user:
            user = User(
                email=email,
                github_username=username,
                auth_provider="github",
                is_active=True,
                last_login_at=datetime.utcnow()
            )
            db.add(user)
            db.flush()  # Ensures user.id is generated for repos
        else:
            user.github_username = username
            user.last_login_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            db.flush()

        # Save profile stats and README in Redis for easy retrieval by API
        profile_data = {
            "username": username,
            "name": name,
            "email": email,
            "bio": bio,
            "avatar_url": avatar_url,
            "github_id": github_id,
            "readme": readme_content
        }
        redis_client.set(f"github_profile:{username}", json.dumps(profile_data))

        # 5. Upsert repositories in database
        processed_repos_count = 0
        for repo_data in repos:
            repo_owner = repo_data.get("owner", {}).get("login", "")
            repo_name = repo_data.get("name", "")
            repo_id = repo_data.get("id")
            html_url = repo_data.get("html_url", "")
            default_branch = repo_data.get("default_branch", "main")
            primary_language = repo_data.get("language")
            star_count = repo_data.get("stargazers_count", 0)

            # Fetch languages byte map
            languages_map = {}
            try:
                languages_map = gh.get_repository_languages(repo_owner, repo_name)
            except Exception as e:
                logger.warning(f"Failed to fetch languages for repo {repo_owner}/{repo_name}: {e}")

            # Check if repo exists
            repo = db.query(Repository).filter(Repository.github_repo_id == repo_id).first()
            if not repo:
                repo = Repository(
                    user_id=user.id,
                    github_url=html_url,
                    github_repo_id=repo_id,
                    owner=repo_owner,
                    name=repo_name,
                    default_branch=default_branch,
                    primary_language=primary_language,
                    languages=languages_map,
                    star_count=star_count,
                    analysis_status="pending"
                )
                db.add(repo)
            else:
                repo.github_url = html_url
                repo.owner = repo_owner
                repo.name = repo_name
                repo.default_branch = default_branch
                repo.primary_language = primary_language
                repo.languages = languages_map
                repo.star_count = star_count
                repo.updated_at = datetime.utcnow()
            
            processed_repos_count += 1
        
        db.commit()
        logger.info(f"Ingested {processed_repos_count} repositories for user: {username}")
        return {
            "status": "success",
            "username": username,
            "repos_count": processed_repos_count
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error in ingest_user_profile_task for {username}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_analysis_workflow_task")
def run_analysis_workflow_task(repository_id: str, job_id: str):
    """
    Background task to run the LangGraph repository analysis workflow.
    Performs checkout, heuristic scanning, and MinIO uploads, while persisting state checkpoints.
    """
    logger.info(f"Starting analysis workflow task. Repository: {repository_id}, Job: {job_id}")
    db = SessionLocal()
    
    # 1. Update Job Status to RUNNING
    try:
        from app.models import AnalysisJob, JobStatus
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.RUNNING,
            "started_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        db.commit()
    except Exception as e:
        logger.exception(f"Failed to initialize analysis job status: {e}")
        db.close()
        return {"status": "error", "message": f"Job initialization error: {str(e)}"}

    try:
        from app.models import Repository
        from app.analysis_graph import analysis_graph
        
        # 2. Fetch Repository details
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repo:
            raise ValueError(f"Repository {repository_id} not found in database.")
            
        # 3. Setup LangGraph thread configuration
        config = {"configurable": {"thread_id": job_id}}
        
        # 4. Invoke graph
        inputs = {
            "repository_id": repository_id,
            "github_url": repo.github_url,
            "default_branch": repo.default_branch,
            "local_path": "",
            "file_tree": {},
            "extracted_facts": [],
            "suggested_questions": [],
            "llm_tokens_used": 0,
            "llm_cost_usd": 0.0,
            "status": "queued",
            "error": None
        }
        
        logger.info(f"Invoking LangGraph orchestrator thread {job_id}...")
        final_state = analysis_graph.invoke(inputs, config)
        
        # 5. Handle execution results
        error = final_state.get("error")
        if error:
            raise RuntimeError(error)
            
        logger.info(f"LangGraph execution finished successfully for thread {job_id}.")
        
        # 6. Update Job Status to COMPLETE
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.COMPLETE,
            "completed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        db.commit()
        return {"status": "success", "job_id": job_id}
        
    except Exception as e:
        logger.exception(f"Unexpected error in run_analysis_workflow_task for job {job_id}: {e}")
        db.rollback()
        
        # Mark job as failed in PostgreSQL
        try:
            from app.models import AnalysisJob, JobStatus
            db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                "status": JobStatus.FAILED,
                "error_message": str(e),
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            db.commit()
        except Exception as db_err:
            logger.error(f"Failed to log job failure to database: {db_err}")
            
        return {"status": "error", "job_id": job_id, "message": str(e)}
    finally:
        db.close()

