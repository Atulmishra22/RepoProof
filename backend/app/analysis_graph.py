import os
import shutil
import logging
from typing import TypedDict, List, Dict, Any, Optional
import git
import boto3
import json
from datetime import datetime
import httpx
from langfuse import Langfuse, propagate_attributes

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from app.database import SessionLocal
from app.models import Repository, AnalysisJob, AnalysisStatus, JobStatus
from app.checkpointer import get_checkpointer
from app.llm_schemas import FactExtractionResult

logger = logging.getLogger(__name__)

LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://litellm:4000")
MODEL_NAME = "gpt-4o-mini"

# Initialize Langfuse
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
    host=os.environ.get("LANGFUSE_HOST", "http://langfuse:3000")
)

# State definition
class AnalysisState(TypedDict):
    repository_id: str
    github_url: str
    default_branch: str
    local_path: str
    file_tree: Dict[str, Any]
    extracted_facts: List[Dict[str, Any]]
    suggested_questions: List[str]
    llm_tokens_used: int
    llm_cost_usd: float
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

def read_key_files(local_path: str, file_tree: Dict[str, Any], max_chars: int = 12000) -> Dict[str, str]:
    key_files_content = {}
    target_names = {
        "package.json", "pyproject.toml", "requirements.txt",
        "dockerfile", "docker-compose.yml", "go.mod", "cargo.toml",
        "main.py", "app.py", "index.js", "server.js", "src/main.ts"
    }
    for rel_path in file_tree.keys():
        filename = os.path.basename(rel_path).lower()
        if filename in target_names or rel_path.lower() in target_names:
            abs_path = os.path.join(local_path, rel_path)
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(max_chars)
                        key_files_content[rel_path] = content
                except Exception as e:
                    logger.warning(f"Failed to read file {rel_path}: {e}")
    return key_files_content

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
                "category": "technology_used",
                "claim": "NodeJS project environment detected.",
                "source_file": rel_path,
                "snippet": "",
                "ats_impact": "Identifies development dependency stack and package setup details."
            })
        elif lower_path.endswith("requirements.txt") or lower_path.endswith("pyproject.toml"):
            facts.append({
                "category": "technology_used",
                "claim": "Python project environment detected.",
                "source_file": rel_path,
                "snippet": "",
                "ats_impact": "Identifies active Python ecosystem usage and project build configuration."
            })
        elif lower_path.endswith("dockerfile") or lower_path.endswith("docker-compose.yml"):
            facts.append({
                "category": "technology_used",
                "claim": "Docker container configuration detected.",
                "source_file": rel_path,
                "snippet": "",
                "ats_impact": "Indicates experience setting up multi-container platforms and environment reproduction pipelines."
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
            "category": "complexity_metric",
            "claim": f"Dominant file extension: {dominant_ext} ({ext_counts[dominant_ext]} files).",
            "source_file": "repository_root",
            "snippet": "",
            "ats_impact": "Indicates repository scale and dominant programming language context."
        })
        
    logger.info(f"Extracted {len(facts)} heuristic facts.")
    return {
        "extracted_facts": facts,
        "status": "facts_extracted"
    }

def extract_llm_facts_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    if state.get("error"):
        return {}

    job_id = None
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "current_node": "extract_llm_facts",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                logger.error(f"Failed to update current_node to extract_llm_facts: {e}")
            finally:
                db.close()

    logger.info("Extracting LLM facts...")
    local_path = state.get("local_path")
    file_tree = state.get("file_tree", {})

    # Select key files
    key_files = read_key_files(local_path, file_tree)
    key_files_str = ""
    for path, content in key_files.items():
        key_files_str += f"--- FILE: {path} ---\n{content}\n\n"

    file_tree_str = json.dumps(file_tree, indent=2)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert Senior Technical Recruiter and Code Screener.\n"
                "Analyze the provided repository files and structure, and extract engineering facts that can be used to generate a stellar, impact-driven ATS-optimized developer resume.\n\n"
                "Follow these instructions strictly:\n"
                "1. Extract the most significant technical achievements, technology choices, architectural patterns, complexity metrics, or contributions.\n"
                "2. For each extracted fact:\n"
                "   - Categorize it as one of: technology_used, architecture_pattern, complexity_metric, contribution, performance_optimization, security_hardening, cost_saving.\n"
                "   - Write a strong, action-oriented resume bullet point ('claim') in active voice. Start with a strong action verb (e.g. 'Architected', 'Designed', 'Optimized', 'Engineered', 'Streamlined'). It must describe a concrete action and result based strictly on the codebase content. Avoid generic statements.\n"
                "   - Cite the exact 'source_file' relative path.\n"
                "   - Provide the exact, literal 'snippet' from the codebase that acts as evidence.\n"
                "   - Explain the 'ats_impact': how it demonstrates senior-level capacity (e.g. scalability, high-availability, caching efficiency, type-safety, testability, security best practices).\n"
                "3. Formulate a list of targeted, insightful follow-up questions ('suggested_questions') for the developer to enrich the context further (e.g. asking about scale, performance improvements, or specific design decisions)."
            )
        },
        {
            "role": "user",
            "content": f"Here is the flat file tree structure of the repository:\n{file_tree_str}\n\nHere are the contents of the key files:\n{key_files_str}"
        }
    ]

    try:
        # Wrap execution in Langfuse tracing context manager
        with propagate_attributes(user_id=state.get("repository_id"), session_id=str(job_id) if job_id else None):
            with langfuse.start_as_current_observation(
                as_type="generation",
                name="llm_fact_extraction",
                model=MODEL_NAME,
                input=messages,
                model_parameters={"temperature": 0.0, "response_format": "FactExtractionResult"}
            ) as generation:
                
                response = httpx.post(
                    f"{LITELLM_PROXY_URL}/v1/chat/completions",
                    json={
                        "model": MODEL_NAME,
                        "messages": messages,
                        "temperature": 0.0,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "FactExtractionResult",
                                "schema": FactExtractionResult.model_json_schema(),
                                "strict": True
                            }
                        }
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                resp_data = response.json()

                # Parse token usage
                usage = resp_data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)

                # Cost: Input ($0.10/1M), Output ($0.40/1M) for gemini-3.1-flash-lite
                cost = (prompt_tokens * 0.10 + completion_tokens * 0.40) / 1000000.0

                content = resp_data["choices"][0]["message"]["content"]
                parsed_result = json.loads(content)

                extracted_facts = parsed_result.get("facts", [])
                suggested_questions = parsed_result.get("suggested_questions", [])

                langfuse.update_current_generation(
                    output=content,
                    usage_details={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": total_tokens
                    }
                )

                # Combine heuristic facts and LLM facts
                existing_facts = state.get("extracted_facts", [])
                combined_facts = list(existing_facts) + extracted_facts

                return {
                    "extracted_facts": combined_facts,
                    "suggested_questions": suggested_questions,
                    "llm_tokens_used": prompt_tokens + completion_tokens,
                    "llm_cost_usd": cost,
                    "status": "llm_facts_extracted"
                }
    except Exception as e:
        logger.exception(f"Error in LLM fact extraction: {e}")
        return {
            "status": "failed",
            "error": f"LLM extraction error: {str(e)}"
        }

def validate_facts_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    if state.get("error"):
        return {}
        
    # Update current node in database
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "current_node": "validate_facts",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                logger.error(f"Failed to update current_node to validate_facts: {e}")
            finally:
                db.close()

    local_path = state.get("local_path")
    extracted_facts = state.get("extracted_facts", [])
    
    validated_facts = []
    
    # Helper to check snippet existence
    def is_snippet_in_file(file_content: str, snippet: str) -> bool:
        def normalize(text: str) -> str:
            return "".join(text.split()).lower()
        
        norm_file = normalize(file_content)
        norm_snippet = normalize(snippet)
        
        if not norm_snippet:
            return False
        return norm_snippet in norm_file

    for fact in extracted_facts:
        source_file = fact.get("source_file")
        snippet = fact.get("snippet")
        
        # If there is no source file or snippet specified (e.g. heuristic facts)
        if not source_file or source_file == "repository_root":
            validated_facts.append(fact)
            continue
            
        abs_file_path = os.path.join(local_path, source_file)
        if not os.path.isfile(abs_file_path):
            logger.warning(f"Fact validation failed: cited file {source_file} does not exist.")
            continue
            
        # If there is no snippet or it's empty, but the file exists
        if not snippet:
            validated_facts.append(fact)
            continue
            
        # Check snippet presence
        try:
            with open(abs_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if is_snippet_in_file(content, snippet):
                validated_facts.append(fact)
            else:
                logger.warning(f"Fact validation failed: snippet not found in {source_file}.")
        except Exception as e:
            logger.error(f"Failed to validate snippet for {source_file}: {e}")
            
    logger.info(f"Validated facts: {len(validated_facts)} out of {len(extracted_facts)} remaining.")
    return {
        "extracted_facts": validated_facts,
        "status": "facts_validated"
    }

def upload_metadata_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    repo_id = state["repository_id"]
    file_tree = state.get("file_tree", {})
    error = state.get("error")
    local_path = state.get("local_path")
    
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

        # 2. Upload analysis result (facts and questions) to MinIO
        analysis_result = {
            "facts": state.get("extracted_facts", []),
            "suggested_questions": state.get("suggested_questions", []),
            "llm_tokens_used": state.get("llm_tokens_used", 0),
            "llm_cost_usd": float(state.get("llm_cost_usd", 0.0))
        }
        s3_key_result = f"repos/{repo_id}/analysis_result.json"
        logger.info(f"Uploading analysis result metadata to MinIO: {s3_key_result}...")
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key_result,
            Body=json.dumps(analysis_result, indent=2),
            ContentType="application/json"
        )
        
        # 3. Update repository status to COMPLETE
        db.query(Repository).filter(Repository.id == repo_id).update({
            "analysis_status": AnalysisStatus.COMPLETE,
            "last_analyzed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })

        # 4. Save metrics in the AnalysisJob row
        if config:
            job_id = config.get("configurable", {}).get("thread_id")
            if job_id:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "llm_tokens_used": state.get("llm_tokens_used", 0),
                    "llm_cost_usd": state.get("llm_cost_usd", 0.0),
                    "updated_at": datetime.utcnow()
                })

        db.commit()
        logger.info("PostgreSQL records and MinIO storage updated successfully.")
        
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
workflow.add_node("extract_llm_facts", extract_llm_facts_node)
workflow.add_node("validate_facts", validate_facts_node)
workflow.add_node("upload_metadata", upload_metadata_node)

# Define edges
workflow.add_edge(START, "clone_repo")
workflow.add_edge("clone_repo", "extract_facts")
workflow.add_edge("extract_facts", "extract_llm_facts")
workflow.add_edge("extract_llm_facts", "validate_facts")
workflow.add_edge("validate_facts", "upload_metadata")
workflow.add_edge("upload_metadata", END)

# Compile graph with persistence
try:
    checkpointer = get_checkpointer()
    analysis_graph = workflow.compile(checkpointer=checkpointer)
except Exception as e:
    logger.exception(f"Failed to compile LangGraph: {e}")
    analysis_graph = workflow.compile()  # Fallback to no checkpointer for compiling safety

