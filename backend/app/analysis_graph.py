import os
import shutil
import logging
from typing import TypedDict, List, Dict, Any, Optional
import git
import boto3
import json
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from app.database import SessionLocal
from app.models import Repository, AnalysisJob, AnalysisStatus, JobStatus
from app.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)

# State definition
class AnalysisState(TypedDict):
    repository_id: str
    github_url: str
    default_branch: str
    local_path: str
    file_tree: Dict[str, Any]
    extracted_facts: List[Dict[str, Any]]
    status: str
    error: Optional[str]

# MinIO storage helper
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "minioadminpass"),
    )

def clone_repo_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    repo_id = state["repository_id"]
    github_url = state["github_url"]
    
    # Update current node in database
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "current_node": "clone_repo",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                logger.error(f"Failed to update current_node to clone_repo: {e}")
            finally:
                db.close()
                
    local_path = f"/tmp/repos/{repo_id}"
    logger.info(f"Cloning repository {github_url} to {local_path}...")
    
    # Clean up directory if it exists
    if os.path.exists(local_path):
        logger.info(f"Directory {local_path} already exists. Cleaning up before clone...")
        shutil.rmtree(local_path)
        
    os.makedirs(local_path, exist_ok=True)
    
    try:
        # Clone using GitPython
        git.Repo.clone_from(github_url, local_path, depth=1)
        logger.info(f"Cloned successfully. Mapping file tree...")
        
        # Build file tree JSON structure
        file_tree = {}
        for root, dirs, files in os.walk(local_path):
            # Skip .git directory to keep file tree small and clean
            if '.git' in dirs:
                dirs.remove('.git')
                
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, local_path)
                size = os.path.getsize(abs_path)
                _, ext = os.path.splitext(file)
                file_tree[rel_path] = {
                    "size": size,
                    "extension": ext.lower()
                }
                
        logger.info(f"Mapped {len(file_tree)} files in repository.")
        return {
            "local_path": local_path,
            "file_tree": file_tree,
            "status": "repo_cloned"
        }
    except Exception as e:
        logger.exception(f"Error cloning repository: {e}")
        # Cleanup
        if os.path.exists(local_path):
            shutil.rmtree(local_path)
        return {
            "status": "failed",
            "error": f"Cloning error: {str(e)}"
        }

def extract_heuristic_facts_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    if state.get("error"):
        return {}
        
    # Update current node in database
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "current_node": "extract_facts",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                logger.error(f"Failed to update current_node to extract_facts: {e}")
            finally:
                db.close()
                
    logger.info("Extracting heuristic facts...")
    file_tree = state.get("file_tree", {})
    local_path = state.get("local_path")
    
    facts = []
    
    # 1. Framework/Language detection by file tree presence
    for rel_path in file_tree.keys():
        lower_path = rel_path.lower()
        if lower_path.endswith("package.json"):
            facts.append({
                "type": "technology_used",
                "claim": "NodeJS project environment detected.",
                "source_file": rel_path
            })
        elif lower_path.endswith("requirements.txt") or lower_path.endswith("pyproject.toml"):
            facts.append({
                "type": "technology_used",
                "claim": "Python project environment detected.",
                "source_file": rel_path
            })
        elif lower_path.endswith("dockerfile") or lower_path.endswith("docker-compose.yml"):
            facts.append({
                "type": "technology_used",
                "claim": "Docker container configuration detected.",
                "source_file": rel_path
            })
            
    # 2. Count extensions
    ext_counts = {}
    for details in file_tree.values():
        ext = details["extension"]
        if ext:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            
    if ext_counts:
        dominant_ext = max(ext_counts, key=ext_counts.get)
        facts.append({
            "type": "metric",
            "claim": f"Dominant file extension: {dominant_ext} ({ext_counts[dominant_ext]} files).",
            "source_file": "repository_root"
        })
        
    logger.info(f"Extracted {len(facts)} heuristic facts.")
    return {
        "extracted_facts": facts,
        "status": "facts_extracted"
    }

def upload_metadata_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    repo_id = state["repository_id"]
    file_tree = state.get("file_tree", {})
    extracted_facts = state.get("extracted_facts", [])
    local_path = state.get("local_path")
    error = state.get("error")
    
    # Update current node in database
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "current_node": "upload_metadata",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                logger.error(f"Failed to update current_node to upload_metadata: {e}")
            finally:
                db.close()
                
    db = SessionLocal()
    try:
        s3 = get_s3_client()
        bucket_name = "repoproof-data"
        
        # Ensure MinIO bucket exists
        try:
            s3.create_bucket(Bucket=bucket_name)
        except s3.exceptions.BucketAlreadyExists:
            pass
        except s3.exceptions.BucketAlreadyOwnedByYou:
            pass
            
        if error:
            logger.error(f"Analysis failed. Registering error in DB...")
            # Update repository and active job statuses to failed
            db.query(Repository).filter(Repository.id == repo_id).update({
                "analysis_status": AnalysisStatus.FAILED,
                "updated_at": datetime.utcnow()
            })
            return {"status": "failed"}
            
        # 1. Upload file tree mapping JSON to MinIO
        s3_key = f"repos/{repo_id}/file_tree.json"
        logger.info(f"Uploading file tree metadata to MinIO: {s3_key}...")
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(file_tree, indent=2),
            ContentType="application/json"
        )
        
        # 2. Update repository status to COMPLETE
        db.query(Repository).filter(Repository.id == repo_id).update({
            "analysis_status": AnalysisStatus.COMPLETE,
            "last_analyzed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        db.commit()
        logger.info("PostgreSQL repository record updated successfully.")
        
    except Exception as e:
        logger.exception(f"Error in upload_metadata_node: {e}")
        db.rollback()
        return {"status": "failed", "error": f"Upload metadata error: {str(e)}"}
    finally:
        db.close()
        # Clean up local repository workspace
        if local_path and os.path.exists(local_path):
            logger.info(f"Purging cloned workspace directory: {local_path}...")
            shutil.rmtree(local_path)
            
    return {"status": "complete"}

# Build LangGraph Workflow
workflow = StateGraph(AnalysisState)

workflow.add_node("clone_repo", clone_repo_node)
workflow.add_node("extract_facts", extract_heuristic_facts_node)
workflow.add_node("upload_metadata", upload_metadata_node)

# Define edges
workflow.add_edge(START, "clone_repo")
workflow.add_edge("clone_repo", "extract_facts")
workflow.add_edge("extract_facts", "upload_metadata")
workflow.add_edge("upload_metadata", END)

# Compile graph with persistence
try:
    checkpointer = get_checkpointer()
    analysis_graph = workflow.compile(checkpointer=checkpointer)
except Exception as e:
    logger.exception(f"Failed to compile LangGraph: {e}")
    analysis_graph = workflow.compile()  # Fallback to no checkpointer for compiling safety
