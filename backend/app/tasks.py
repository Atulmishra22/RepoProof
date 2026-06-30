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

import structlog
logger = structlog.get_logger(__name__)

@celery_app.task(name="app.tasks.ingest_user_profile_task")
def ingest_user_profile_task(username: str, user_id: Optional[str] = None, trace_id: Optional[str] = None):
    """
    Background task to fetch user details, profile README, and public repositories from GitHub.
    Saves User/Repositories to PostgreSQL, and caches the parsed profile in Redis.
    """
    from app.logging_config import bind_log_context
    if trace_id:
        bind_log_context(trace_id=trace_id)
    if user_id:
        bind_log_context(user_id=user_id)

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
        from app.logging_config import clear_log_context
        clear_log_context()
        db.close()


@celery_app.task(name="app.tasks.run_analysis_workflow_task")
def run_analysis_workflow_task(repository_id: str, job_id: str, trace_id: Optional[str] = None):
    """
    Background task to run the LangGraph repository analysis workflow.
    Performs checkout, heuristic scanning, and MinIO uploads, while persisting state checkpoints.
    """
    from app.logging_config import bind_log_context
    if trace_id:
        bind_log_context(trace_id=trace_id)
    bind_log_context(job_id=job_id)
    
    start_time = datetime.utcnow()
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
        from app.models import Repository, AnalysisJob, User
        from app.analysis_graph import analysis_graph
        
        # Fetch Job and bind user_id context
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        user_tier = "free"
        if job:
            bind_log_context(user_id=str(job.user_id))
            user = db.query(User).filter(User.id == job.user_id).first()
            if user:
                user_tier = user.subscription_tier.value if hasattr(user.subscription_tier, 'value') else str(user.subscription_tier)
                
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
            try:
                from app.metrics import analysis_job_total, analysis_job_duration_seconds
                analysis_job_total.labels(status="interrupted", subscription_tier=user_tier).inc()
                duration = (datetime.utcnow() - start_time).total_seconds()
                analysis_job_duration_seconds.labels(status="interrupted").observe(duration)
            except Exception as metric_err:
                logger.error(f"Failed to record interrupted metrics: {metric_err}")
            return {"status": "interrupted", "job_id": job_id, "next": state_info.next}
            
        logger.info(f"LangGraph execution finished successfully for thread {job_id}.")
        
        # 6. Update Job Status to COMPLETE
        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
            "status": JobStatus.COMPLETE,
            "completed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        db.commit()
        
        try:
            from app.metrics import analysis_job_total, analysis_job_duration_seconds
            analysis_job_total.labels(status="complete", subscription_tier=user_tier).inc()
            duration = (datetime.utcnow() - start_time).total_seconds()
            analysis_job_duration_seconds.labels(status="complete").observe(duration)
        except Exception as metric_err:
            logger.error(f"Failed to record complete metrics: {metric_err}")
            
        return {"status": "success", "job_id": job_id}
        
    except Exception as e:
        logger.exception(f"Unexpected error in run_analysis_workflow_task for job {job_id}: {e}")
        db.rollback()
        
        try:
            from app.metrics import analysis_job_total, analysis_job_duration_seconds
            analysis_job_total.labels(status="failed", subscription_tier=user_tier).inc()
            duration = (datetime.utcnow() - start_time).total_seconds()
            analysis_job_duration_seconds.labels(status="failed").observe(duration)
        except Exception as metric_err:
            logger.error(f"Failed to record failed metrics: {metric_err}")
            
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
        from app.logging_config import clear_log_context
        clear_log_context()
        db.close()


@celery_app.task(name="app.tasks.resume_analysis_workflow_task")
def resume_analysis_workflow_task(job_id: str, updated_facts: Optional[list] = None, trace_id: Optional[str] = None):
    """
    Background task to resume the paused LangGraph workflow for a repository.
    Optionally updates the candidate facts in the checkpoint state before resuming.
    """
    from app.logging_config import bind_log_context
    if trace_id:
        bind_log_context(trace_id=trace_id)
    bind_log_context(job_id=job_id)
    
    start_time = datetime.utcnow()
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
        from app.models import User
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            raise ValueError(f"Analysis job {job_id} not found in database.")
            
        bind_log_context(user_id=str(job.user_id))
        user_tier = "free"
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user_tier = user.subscription_tier.value if hasattr(user.subscription_tier, 'value') else str(user.subscription_tier)
            
        # Update repo status to ANALYZING to indicate active progress
        db.query(Repository).filter(Repository.id == job.repository_id).update({
            "analysis_status": AnalysisStatus.ANALYZING,
            "updated_at": datetime.utcnow()
        })
        db.commit()

        # 3. Setup LangGraph thread configuration
        config = {"configurable": {"thread_id": job_id}}
        
        # 4. If updated facts are provided, update the graph state and the database
        if updated_facts is not None:
            # Mark all as human approved since they came from review approval
            for f in updated_facts:
                f["is_human_approved"] = True
            
            logger.info(f"Updating graph state with revised facts for thread {job_id}...")
            analysis_graph.update_state(config, {"extracted_facts": updated_facts}, as_node="await_human_review")
            
            from app.analysis_graph import save_facts_to_db
            try:
                save_facts_to_db(job.id, updated_facts)
            except Exception as db_err:
                logger.error(f"Failed to save approved facts to database: {db_err}")
            
        # 5. Invoke graph with None input to resume from checkpoint
        logger.info(f"Resuming LangGraph orchestrator thread {job_id}...")
        final_state = analysis_graph.invoke(None, config)
        
        # Check if the graph is interrupted (waiting for clarification)
        state_info = analysis_graph.get_state(config)
        if state_info.next:
            logger.info(f"LangGraph execution interrupted for thread {job_id}. Next node: {state_info.next}")
            try:
                from app.metrics import analysis_job_total, analysis_job_duration_seconds
                analysis_job_total.labels(status="interrupted", subscription_tier=user_tier).inc()
                duration = (datetime.utcnow() - start_time).total_seconds()
                analysis_job_duration_seconds.labels(status="interrupted").observe(duration)
            except Exception as metric_err:
                logger.error(f"Failed to record interrupted metrics: {metric_err}")
            return {"status": "interrupted", "job_id": job_id, "next": state_info.next}
        
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

        try:
            from app.metrics import analysis_job_total, analysis_job_duration_seconds
            analysis_job_total.labels(status="complete", subscription_tier=user_tier).inc()
            duration = (datetime.utcnow() - start_time).total_seconds()
            analysis_job_duration_seconds.labels(status="complete").observe(duration)
        except Exception as metric_err:
            logger.error(f"Failed to record complete metrics: {metric_err}")

        # Trigger fact embeddings and preference reflection background tasks
        try:
            compute_fact_embeddings_task.delay(str(job.id))
            reflect_user_preferences_task.delay(str(job.user_id), str(job.id))
        except Exception as queue_err:
            logger.error(f"Failed to queue background embeddings/reflection tasks: {queue_err}")

        return {"status": "success", "job_id": job_id}
        
    except Exception as e:
        logger.exception(f"Unexpected error in resume_analysis_workflow_task for job {job_id}: {e}")
        db.rollback()
        
        try:
            from app.metrics import analysis_job_total, analysis_job_duration_seconds
            analysis_job_total.labels(status="failed", subscription_tier=user_tier).inc()
            duration = (datetime.utcnow() - start_time).total_seconds()
            analysis_job_duration_seconds.labels(status="failed").observe(duration)
        except Exception as metric_err:
            logger.error(f"Failed to record failed metrics: {metric_err}")
            
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
        from app.logging_config import clear_log_context
        clear_log_context()
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


@celery_app.task(name="app.tasks.compute_fact_embeddings_task")
def compute_fact_embeddings_task(job_id: str):
    """
    Computes text embeddings for all approved facts using text-embedding-004 via LiteLLM.
    Writes the resulting vectors directly to fact_embeddings database table.
    """
    logger.info(f"Computing fact embeddings for job: {job_id}")
    db = SessionLocal()
    try:
        from app.models import CodeFact, FactEmbedding
        import httpx
        import os
        import random
        
        # Get all approved facts for this job
        facts = db.query(CodeFact).filter(
            CodeFact.analysis_job_id == job_id,
            CodeFact.is_human_approved == True
        ).all()
        
        if not facts:
            logger.info("No approved facts found to embed.")
            return {"status": "skipped", "message": "No approved facts."}
            
        LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://litellm:4000")
        model_used = "text-embedding-004"
        
        for fact in facts:
            # text content representation
            text_to_embed = f"Category: {fact.category}\nClaim: {fact.claim}\nSource File: {fact.source_file}"
            
            embedding_vector = None
            try:
                response = httpx.post(
                    f"{LITELLM_PROXY_URL}/v1/embeddings",
                    json={
                        "model": model_used,
                        "input": [text_to_embed]
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                resp_data = response.json()
                embedding_vector = resp_data["data"][0]["embedding"]
            except Exception as e:
                logger.warning(f"Failed to compute real embedding for fact {fact.id} via LiteLLM: {e}. Using mock embedding.")
                # Fallback mock embedding: 768 float values
                embedding_vector = [random.uniform(-0.1, 0.1) for _ in range(768)]
                
            if embedding_vector:
                # Save to database
                existing = db.query(FactEmbedding).filter(FactEmbedding.code_fact_id == fact.id).first()
                if existing:
                    existing.embedding = embedding_vector
                    existing.model_used = model_used
                else:
                    new_emb = FactEmbedding(
                        code_fact_id=fact.id,
                        embedding=embedding_vector,
                        model_used=model_used
                    )
                    db.add(new_emb)
                    
        db.commit()
        return {"status": "success", "embedded_count": len(facts)}
    except Exception as e:
        logger.error(f"Failed in compute_fact_embeddings_task: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.reflect_user_preferences_task")
def reflect_user_preferences_task(user_id: str, job_id: str):
    """
    Compares the original facts (from MinIO) against approved ones (from DB)
    to extract styling/rule adjustments. Writes to user_preferences table.
    """
    logger.info(f"Reflecting user preferences. User: {user_id}, Job: {job_id}")
    db = SessionLocal()
    try:
        from app.models import CodeFact, UserPreference, AnalysisJob
        from app.analysis_graph import get_s3_client
        import httpx
        import os
        
        # 1. Fetch original facts from MinIO
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return {"status": "error", "message": "Job not found"}
            
        s3 = get_s3_client()
        bucket_name = "repoproof-data"
        s3_key = f"repos/{job.repository_id}/analysis_result.json"
        
        try:
            response = s3.get_object(Bucket=bucket_name, Key=s3_key)
            original_data = json.loads(response["Body"].read().decode("utf-8"))
            original_facts = original_data.get("facts", [])
        except Exception as e:
            logger.warning(f"Could not load original facts from S3: {e}")
            original_facts = []
            
        # 2. Fetch approved/edited facts from DB
        approved_facts = db.query(CodeFact).filter(
            CodeFact.analysis_job_id == job_id,
            CodeFact.is_human_approved == True
        ).all()
        
        # 3. Find edits
        original_by_id = {f.get("id"): f for f in original_facts if f.get("id")}
        diffs = []
        for af in approved_facts:
            fid = str(af.id)
            if fid in original_by_id:
                orig_fact = original_by_id[fid]
                if orig_fact.get("claim") != af.claim or orig_fact.get("ats_impact") != af.ats_impact:
                    diffs.append({
                        "original_claim": orig_fact.get("claim"),
                        "edited_claim": af.claim,
                        "original_ats_impact": orig_fact.get("ats_impact"),
                        "edited_ats_impact": af.ats_impact
                    })
                    
        if not diffs:
            logger.info("No modifications detected. Skipping preference reflection.")
            return {"status": "skipped", "message": "No edits detected."}
            
        # 4. Ask LLM to infer rules
        diffs_str = json.dumps(diffs, indent=2)
        prompt = (
            "You are an AI assistant analyzing edits made by a software developer on their AI-generated resume bullet points.\n"
            "Identify general styling preferences, layout rules, tone adjustments, or keyword/buzzword changes preferred by the developer.\n"
            f"Here are the edits made:\n{diffs_str}\n\n"
            "Return a JSON list of inferred rules. Format your response exactly as a JSON array of strings, e.g. ['Prefer short, direct action verbs.', 'Avoid using the word leverage.', 'Keep bullet points under 20 words.']."
        )
        
        LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://litellm:4000")
        MODEL_NAME = "gpt-4o-mini"
        
        try:
            response = httpx.post(
                f"{LITELLM_PROXY_URL}/v1/chat/completions",
                json={
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0
                },
                timeout=45.0
            )
            response.raise_for_status()
            resp_data = response.json()
            content = resp_data["choices"][0]["message"]["content"]
            
            # Clean possible markdown fence code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            rules = json.loads(content)
            
            # Handle dictionary wrapped lists
            if isinstance(rules, dict):
                for val in rules.values():
                    if isinstance(val, list):
                        rules = val
                        break
            
            if isinstance(rules, list) and rules:
                for rule_str in rules:
                    if isinstance(rule_str, str) and rule_str.strip():
                        new_pref = UserPreference(
                            user_id=uuid.UUID(user_id),
                            rule=rule_str.strip()
                        )
                        db.add(new_pref)
                db.commit()
                logger.info(f"Successfully reflected {len(rules)} style preferences for user {user_id}.")
                return {"status": "success", "rules_added": len(rules)}
        except Exception as llm_err:
            logger.error(f"Failed to analyze preferences with LLM: {llm_err}")
            
        return {"status": "completed_without_llm"}
    except Exception as e:
        logger.error(f"Error in reflect_user_preferences_task: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()

