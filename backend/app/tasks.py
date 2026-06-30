import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import User, Repository
from app.github_client import GitHubSyncClient, GitHubClientError
from app.redis_client import redis_client

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.ingest_user_profile_task")
def ingest_user_profile_task(username: str, user_id: Optional[str] = None):
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

        # 3. Fetch list of public repositories (use database-cached metadata if available to save API limits)
        repos = []
        try:
            existing_repos = db.query(Repository).filter(
                Repository.owner == username,
                Repository.is_private == False
            ).all()
            if existing_repos:
                logger.info(f"Re-using {len(existing_repos)} repository records found in database for owner: {username}")
                seen_ids = set()
                for r in existing_repos:
                    if r.github_repo_id not in seen_ids:
                        seen_ids.add(r.github_repo_id)
                        repos.append({
                            "id": r.github_repo_id,
                            "name": r.name,
                            "html_url": r.github_url,
                            "default_branch": r.default_branch,
                            "language": r.primary_language,
                            "stargazers_count": r.star_count,
                            "owner": {"login": r.owner},
                            "languages_map": r.languages,
                            "private": r.is_private
                        })
            else:
                logger.info(f"No existing repositories in DB for owner {username}. Querying GitHub API.")
                repos_raw = gh.list_repositories(username)
                for repo_data in repos_raw:
                    repos.append({
                        "id": repo_data.get("id"),
                        "name": repo_data.get("name", ""),
                        "html_url": repo_data.get("html_url", ""),
                        "default_branch": repo_data.get("default_branch", "main"),
                        "language": repo_data.get("language"),
                        "stargazers_count": repo_data.get("stargazers_count", 0),
                        "owner": {"login": repo_data.get("owner", {}).get("login", "")},
                        "languages_map": None,
                        "private": repo_data.get("private", False)
                    })
        except GitHubClientError as e:
            logger.error(f"Failed to fetch repositories for user {username}: {e}")
            return {"status": "error", "message": f"Failed to fetch repositories: {str(e)}"}

        # 4. Upsert User in database
        user = None
        if user_id:
            logged_in_user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
            if logged_in_user and logged_in_user.github_username == username:
                user = logged_in_user

        if not user:
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

        # Save profile stats and README in Redis for easy retrieval by API (TTL: 24h)
        profile_data = {
            "username": username,
            "name": name,
            "email": email,
            "bio": bio,
            "avatar_url": avatar_url,
            "github_id": github_id,
            "readme": readme_content
        }
        redis_client.setex(f"github_profile:{username}", 86400, json.dumps(profile_data))

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
            is_private = repo_data.get("private", False)

            # Check if we have languages cached or need to fetch
            languages_map = repo_data.get("languages_map")
            if languages_map is None:
                languages_map = {}
                try:
                    languages_map = gh.get_repository_languages(repo_owner, repo_name)
                except Exception as e:
                    logger.warning(f"Failed to fetch languages for repo {repo_owner}/{repo_name}: {e}")

            # Check if repo exists for this user specifically
            repo = db.query(Repository).filter(
                Repository.user_id == user.id,
                Repository.github_repo_id == repo_id
            ).first()
            
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
                    is_private=is_private,
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
                repo.is_private = is_private
                repo.updated_at = datetime.utcnow()
            
            processed_repos_count += 1
        
        db.commit()

        # LEVEL 1 — META cache (Redis, shared, safe)
        public_db_repos = db.query(Repository).filter(
            Repository.user_id == user.id,
            Repository.is_private == False
        ).all()
        
        has_public = len(public_db_repos) > 0
        has_private = db.query(Repository).filter(
            Repository.user_id == user.id,
            Repository.is_private == True
        ).count() > 0
        
        meta_data = {
            "has_public": has_public,
            "has_private": has_private,
            "profile_cached": True
        }
        redis_client.setex(f"github_meta:{username}", 86400, json.dumps(meta_data))
        
        # LEVEL 2 — PUBLIC repos cache (Redis, shared, safe)
        public_repos_cache_data = [
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
            for r in public_db_repos
        ]
        redis_client.setex(f"github_public_repos:{username}", 86400, json.dumps(public_repos_cache_data))

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
            
        # Check if the graph is interrupted (waiting for human review)
        state_info = analysis_graph.get_state(config)
        if state_info.next:
            logger.info(f"LangGraph execution interrupted for thread {job_id}. Next node: {state_info.next}")
            return {"status": "interrupted", "job_id": job_id, "next": state_info.next}
            
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


@celery_app.task(name="app.tasks.resume_analysis_workflow_task")
def resume_analysis_workflow_task(job_id: str, updated_facts: Optional[list] = None):
    """
    Background task to resume the paused LangGraph workflow for a repository.
    Optionally updates the candidate facts in the checkpoint state before resuming.
    """
    logger.info(f"Resuming analysis workflow task. Job: {job_id}")
    db = SessionLocal()
    try:
        from app.models import AnalysisJob, JobStatus, Repository, AnalysisStatus
        from app.analysis_graph import analysis_graph
        
        # 1. Update Job Status to RUNNING
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.RUNNING,
            "updated_at": datetime.utcnow()
        })
        db.commit()
        
        # 2. Fetch Job Details
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            raise ValueError(f"Analysis job {job_id} not found in database.")
            
        # Update repo status to ANALYZING to indicate active progress
        db.query(Repository).filter(Repository.id == job.repository_id).update({
            "analysis_status": AnalysisStatus.ANALYZING,
            "updated_at": datetime.utcnow()
        })
        db.commit()

        # 3. Setup LangGraph thread configuration
        config = {"configurable": {"thread_id": job_id}}
        
        # 4. If updated facts are provided, update the graph state
        if updated_facts is not None:
            logger.info(f"Updating graph state with revised facts for thread {job_id}...")
            analysis_graph.update_state(config, {"extracted_facts": updated_facts}, as_node="await_human_review")
            
        # 5. Invoke graph with None input to resume from checkpoint
        logger.info(f"Resuming LangGraph orchestrator thread {job_id}...")
        final_state = analysis_graph.invoke(None, config)
        
        # 6. Handle execution results
        error = final_state.get("error")
        if error:
            raise RuntimeError(error)
            
        logger.info(f"LangGraph execution resumed and finished successfully for thread {job_id}.")
        
        # 7. Update Job Status to COMPLETE
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.COMPLETE,
            "completed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        db.commit()
        return {"status": "success", "job_id": job_id}
        
    except Exception as e:
        logger.exception(f"Unexpected error in resume_analysis_workflow_task for job {job_id}: {e}")
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


@celery_app.task(name="app.tasks.cleanup_expired_sessions_task")
def cleanup_expired_sessions_task():
    """
    Periodic task to clean up expired session rows from PostgreSQL
    and delete matching session cache keys from Redis.
    """
    logger.info("Starting expired sessions cleanup task.")
    db = SessionLocal()
    from app.models import Session as SessionModel
    from datetime import datetime, timezone
    
    try:
        now = datetime.now(timezone.utc)
        # 1. Query expired sessions
        expired_sessions = db.query(SessionModel).filter(SessionModel.expires < now).all()
        count = len(expired_sessions)
        
        if count > 0:
            logger.info(f"Found {count} expired sessions to clean up.")
            for session in expired_sessions:
                # Delete from Redis cache
                redis_key = f"session:{session.session_token}"
                try:
                    redis_client.srem(f"user_sessions:{session.user_id}", session.session_token)
                    redis_client.delete(redis_key)
                except Exception as e:
                    logger.error(f"Failed to delete redis key for session {session.session_token}: {e}")
                
                # Delete from DB
                db.delete(session)
            
            db.commit()
            logger.info(f"Successfully cleaned up {count} expired sessions from DB and Redis.")
        else:
            logger.info("No expired sessions found.")
            
        return {"status": "success", "cleaned_count": count}
    except Exception as e:
        db.rollback()
        logger.error(f"Error during expired sessions cleanup: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

