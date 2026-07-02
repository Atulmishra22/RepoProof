import os
import shutil
import structlog
import time
import subprocess
import tempfile
from typing import TypedDict, List, Dict, Any, Optional
import git
import boto3
import json
from datetime import datetime
import httpx
from langfuse import Langfuse, propagate_attributes

import uuid
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from app.database import SessionLocal
from app.models import Repository, AnalysisJob, AnalysisStatus, JobStatus, GeneratedOutput, OutputType, CodeFact
from app.checkpointer import get_checkpointer
from app.llm_schemas import FactExtractionResult, LaTeXResumeResponse, LaTeXSelfHealingResponse, MarkdownOutputsResponse, SingleMarkdownResponse

logger = structlog.get_logger(__name__)


def save_facts_to_db(job_id: uuid.UUID, facts: List[Dict[str, Any]]):
    db = SessionLocal()
    try:
        # Check existing facts for this job_id
        existing_facts = db.query(CodeFact).filter(CodeFact.analysis_job_id == job_id).all()
        existing_by_id = {str(ef.id): ef for ef in existing_facts}
        
        passed_ids = set()
        for f in facts:
            fid = f.get("id")
            if not fid:
                fid = str(uuid.uuid4())
                f["id"] = fid
            passed_ids.add(fid)
            
            if fid in existing_by_id:
                # Update existing fact
                fact_obj = existing_by_id[fid]
                fact_obj.category = f.get("category")
                fact_obj.claim = f.get("claim")
                fact_obj.source_file = f.get("source_file")
                fact_obj.snippet = f.get("snippet")
                fact_obj.ats_impact = f.get("ats_impact")
                if "is_validated" in f:
                    fact_obj.is_validated = bool(f["is_validated"])
                if "is_human_approved" in f:
                    fact_obj.is_human_approved = bool(f["is_human_approved"])
            else:
                # Create new fact
                fact_obj = CodeFact(
                    id=uuid.UUID(fid),
                    analysis_job_id=job_id,
                    category=f.get("category"),
                    claim=f.get("claim"),
                    source_file=f.get("source_file"),
                    snippet=f.get("snippet"),
                    ats_impact=f.get("ats_impact"),
                    is_validated=f.get("is_validated", False),
                    is_human_approved=f.get("is_human_approved", False)
                )
                db.add(fact_obj)
        
        # Delete any existing facts not passed in the list
        for fid, fact_obj in existing_by_id.items():
            if fid not in passed_ids:
                db.delete(fact_obj)
                
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save facts to DB: {e}")
        db.rollback()
    finally:
        db.close()

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
    target_role: Optional[str]
    needs_clarification: Optional[bool]

# MinIO storage helper
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "minioadminpass"),
    )

def build_dependency_graph(local_path: str, file_tree: Dict[str, Any]) -> Dict[str, List[str]]:
    graph = {}
    import re
    
    # regexes to extract import targets
    py_import_re = re.compile(r'^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)')
    js_import_re = re.compile(r'(?:import|require)\s*\(\s*[\'"]([^\'"]+)[\'"]')
    js_from_re = re.compile(r'from\s+[\'"]([^\'"]+)[\'"]')
    
    for rel_path in file_tree.keys():
        abs_path = os.path.join(local_path, rel_path)
        if not os.path.isfile(abs_path):
            continue
            
        graph[rel_path] = []
        filename_lower = os.path.basename(rel_path).lower()
        
        # Only parse source code files
        if not any(filename_lower.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs"]):
            continue
            
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # python
                    if filename_lower.endswith(".py"):
                        match = py_import_re.match(line)
                        if match:
                            module = match.group(1).split('.')[0]
                            for k in file_tree.keys():
                                if k.startswith(module) or f"/{module}" in k:
                                    graph[rel_path].append(k)
                    # js/ts
                    elif any(filename_lower.endswith(ext) for ext in [".js", ".ts", ".jsx", ".tsx"]):
                        match = js_import_re.search(line)
                        if match:
                            dep = match.group(1)
                            for k in file_tree.keys():
                                if dep in k:
                                    graph[rel_path].append(k)
                        match2 = js_from_re.search(line)
                        if match2:
                            dep = match2.group(1)
                            for k in file_tree.keys():
                                if dep in k:
                                    graph[rel_path].append(k)
        except Exception as e:
            logger.warning(f"Error parsing dependencies for {rel_path}: {e}")
            
    # Clean duplicates
    for k in graph:
        graph[k] = list(set(graph[k]))
        
    return graph

def prune_context_files(local_path: str, file_tree: Dict[str, Any], max_chars: int = 12000) -> Dict[str, str]:
    logger.info("Running GraphRAG context pruning...")
    graph = build_dependency_graph(local_path, file_tree)
    
    # Save dependency graph to project_graph.json
    try:
        graph_path = os.path.join(local_path, "project_graph.json")
        with open(graph_path, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save project_graph.json: {e}")
        
    # Identify seed entry points
    target_names = {
        "package.json", "pyproject.toml", "requirements.txt",
        "dockerfile", "docker-compose.yml", "go.mod", "cargo.toml",
        "main.py", "app.py", "index.js", "server.js", "src/main.ts"
    }
    
    seeds = []
    for rel_path in file_tree.keys():
        filename = os.path.basename(rel_path).lower()
        if filename in target_names or rel_path.lower() in target_names:
            seeds.append(rel_path)
            
    # BFS to collect reachable files up to depth 2
    visited = set(seeds)
    queue = [(s, 0) for s in seeds]
    
    while queue:
        curr, depth = queue.pop(0)
        if depth >= 2:
            continue
        neighbors = graph.get(curr, [])
        for n in neighbors:
            if n not in visited:
                visited.add(n)
                queue.append((n, depth + 1))
                
    # Read the contents of visited/pruned files
    pruned_content = {}
    for rel_path in visited:
        abs_path = os.path.join(local_path, rel_path)
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    pruned_content[rel_path] = f.read(max_chars)
            except Exception as e:
                logger.warning(f"Failed to read file {rel_path} in GraphRAG context: {e}")
                
    logger.info(f"GraphRAG pruned context to {len(pruned_content)} files out of {len(file_tree)} total files.")
    return pruned_content

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
        # Check if mock/dev repo
        if "_dev" in github_url or "mock" in github_url:
            logger.info("Mock repository detected. Skipping git clone and creating mock files.")
            os.makedirs(os.path.join(local_path, "src"), exist_ok=True)
            with open(os.path.join(local_path, "package.json"), "w") as f:
                json.dump({
                    "name": "pub-repo",
                    "version": "1.0.0",
                    "dependencies": {
                        "express": "^4.18.2",
                        "redis": "^4.6.7"
                    }
                }, f, indent=2)
            with open(os.path.join(local_path, "src", "index.ts"), "w") as f:
                f.write("""import express from 'express';
import { createClient } from 'redis';

const app = express();
const client = createClient({ url: 'redis://localhost:6379' });

app.get('/users', async (req, res) => {
  const cachedUsers = await client.get('users');
  if (cachedUsers) return res.json(JSON.parse(cachedUsers));
  
  const users = [{ id: 1, name: 'John' }];
  await client.setEx('users', 3600, JSON.stringify(users));
  res.json(users);
});
""")
            with open(os.path.join(local_path, "README.md"), "w") as f:
                f.write("# Pub Repo\nMock project for testing.")
        else:
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
        
    for f in facts:
        f["id"] = str(uuid.uuid4())
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

    # Select key files using GraphRAG pruned retrieval
    key_files = prune_context_files(local_path, file_tree)
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

                try:
                    from app.metrics import llm_api_call_total, llm_token_consumption_total
                    llm_api_call_total.labels(provider="gemini", model=MODEL_NAME, status="success").inc()
                    # We can use the repository_id as user identifier proxy or log it for general tracking
                    llm_token_consumption_total.labels(user_id=state.get("repository_id", "system"), model=MODEL_NAME, type="prompt").inc(prompt_tokens)
                    llm_token_consumption_total.labels(user_id=state.get("repository_id", "system"), model=MODEL_NAME, type="completion").inc(completion_tokens)
                except Exception as metric_err:
                    logger.error(f"Failed to record LLM success metrics: {metric_err}")

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

                for f in extracted_facts:
                    f["id"] = str(uuid.uuid4())

                # Combine heuristic facts and LLM facts
                existing_facts = state.get("extracted_facts", [])
                combined_facts = list(existing_facts) + extracted_facts

                if job_id:
                    try:
                        save_facts_to_db(uuid.UUID(str(job_id)), combined_facts)
                    except Exception as db_err:
                        logger.error(f"Failed to save combined facts to database: {db_err}")

                return {
                    "extracted_facts": combined_facts,
                    "suggested_questions": suggested_questions,
                    "llm_tokens_used": prompt_tokens + completion_tokens,
                    "llm_cost_usd": cost,
                    "status": "llm_facts_extracted"
                }
    except Exception as e:
        try:
            from app.metrics import llm_api_call_total
            llm_api_call_total.labels(provider="gemini", model=MODEL_NAME, status="failure").inc()
        except Exception as metric_err:
            logger.error(f"Failed to record LLM failure metrics: {metric_err}")
            
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
            
    validated_ids = {f.get("id") for f in validated_facts if f.get("id")}
    for f in extracted_facts:
        f["is_validated"] = f.get("id") in validated_ids

    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        if job_id:
            try:
                save_facts_to_db(uuid.UUID(str(job_id)), extracted_facts)
            except Exception as db_err:
                logger.error(f"Failed to update validated facts in database: {db_err}")

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
        
        # Publish COMPLETE status broadcast
        try:
            from app.redis_client import redis_client
            job_id = config.get("configurable", {}).get("thread_id") if config else None
            broadcast_msg = {
                "type": "status_update",
                "repository_id": str(repo_id),
                "status": "complete",
                "job_id": str(job_id) if job_id else None
            }
            redis_client.publish("review_status_channel", json.dumps(broadcast_msg))
            logger.info("Published COMPLETE status update broadcast to Redis.")
        except Exception as pub_err:
            logger.error(f"Failed to publish status update broadcast: {pub_err}")
        
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

def save_intermediate_results_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    repo_id = state["repository_id"]
    file_tree = state.get("file_tree", {})
    error = state.get("error")
    
    if error:
        return {}

    logger.info("Saving intermediate analysis results for human review...")
    
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
            
        # 1. Upload intermediate file tree mapping JSON to MinIO
        s3_key = f"repos/{repo_id}/file_tree.json"
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(file_tree, indent=2),
            ContentType="application/json"
        )

        # 2. Upload intermediate analysis result (facts and questions) to MinIO
        analysis_result = {
            "facts": state.get("extracted_facts", []),
            "suggested_questions": state.get("suggested_questions", []),
            "llm_tokens_used": state.get("llm_tokens_used", 0),
            "llm_cost_usd": float(state.get("llm_cost_usd", 0.0))
        }
        s3_key_result = f"repos/{repo_id}/analysis_result.json"
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key_result,
            Body=json.dumps(analysis_result, indent=2),
            ContentType="application/json"
        )
        
        # 3. Update repository status to AWAITING_REVIEW
        db.query(Repository).filter(Repository.id == repo_id).update({
            "analysis_status": AnalysisStatus.AWAITING_REVIEW,
            "updated_at": datetime.utcnow()
        })

        # 4. Save metrics & update job status to INTERRUPTED in AnalysisJob
        if config:
            job_id = config.get("configurable", {}).get("thread_id")
            if job_id:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "status": JobStatus.INTERRUPTED,
                    "current_node": "await_human_review",
                    "llm_tokens_used": state.get("llm_tokens_used", 0),
                    "llm_cost_usd": state.get("llm_cost_usd", 0.0),
                    "updated_at": datetime.utcnow()
                })

        db.commit()
        logger.info("Intermediate records saved, repository marked as AWAITING_REVIEW.")
        
        # Publish AWAITING_REVIEW status broadcast
        try:
            from app.redis_client import redis_client
            job_id = config.get("configurable", {}).get("thread_id") if config else None
            broadcast_msg = {
                "type": "status_update",
                "repository_id": str(repo_id),
                "status": "awaiting_review",
                "job_id": str(job_id) if job_id else None
            }
            redis_client.publish("review_status_channel", json.dumps(broadcast_msg))
            logger.info("Published AWAITING_REVIEW status update broadcast to Redis.")
        except Exception as pub_err:
            logger.error(f"Failed to publish status update broadcast: {pub_err}")
        
    except Exception as e:
        logger.exception(f"Error in save_intermediate_results_node: {e}")
        db.rollback()
        return {"status": "failed", "error": f"Save intermediate error: {str(e)}"}
    finally:
        db.close()
        
    return {"status": "awaiting_review"}

def await_human_review_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    # Pass-through node. When resumed, it just transitions forward to upload_metadata.
    logger.info("Resuming execution from human review checkpoint...")
    return {"status": "review_completed"}


def check_missing_context_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    if state.get("error"):
        return {}
        
    repo_id = state["repository_id"]
    job_id = None
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        
    db = SessionLocal()
    user_email = ""
    target_role = state.get("target_role")
    
    # Query user details
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if repo:
            from app.models import User
            user = db.query(User).filter(User.id == repo.user_id).first()
            if user:
                user_email = user.email or ""
    except Exception as e:
        logger.error(f"Error checking context details: {e}")
    finally:
        db.close()
        
    # Validation check: must have a valid email and target role
    has_email = bool(user_email and "@" in user_email)
    
    if not target_role or not target_role.strip():
        try:
            repo = db.query(Repository).filter(Repository.id == repo_id).first()
            if repo:
                from app.models import User
                user = db.query(User).filter(User.id == repo.user_id).first()
                if user and user.github_username:
                    import redis
                    from app.redis_client import redis_client
                    cached_profile = redis_client.get(f"github_profile:{user.github_username}")
                    if cached_profile:
                        profile_data = json.loads(cached_profile)
                        bio = profile_data.get("bio", "")
                        if bio and len(bio.strip()) > 3:
                            target_role = bio.strip()
        except Exception as e:
            logger.error(f"Error resolving fallback target_role: {e}")
            
        if not target_role or not target_role.strip():
            target_role = "Full Stack Software Engineer"
            
        # Update state dictionary directly (we will return it to propagate)
        state["target_role"] = target_role

    has_role = bool(target_role and target_role.strip())
    
    if not has_email or not has_role:
        logger.warning(f"Clarification Gate failed. Has email: {has_email}, Has role: {has_role}. Pausing workflow.")
        # Update job status in database to AWAITING_CLARIFICATION
        if job_id:
            db = SessionLocal()
            try:
                db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                    "status": JobStatus.INTERRUPTED,
                    "current_node": "await_clarification",
                    "updated_at": datetime.utcnow()
                })
                db.commit()
            except Exception as db_err:
                logger.error(f"Failed to update job to awaiting clarification: {db_err}")
            finally:
                db.close()
                
        return {
            "needs_clarification": True,
            "status": "awaiting_clarification"
        }
        
    logger.info("Clarification Gate passed. Continuing to document compilation.")
    return {
        "target_role": target_role,
        "needs_clarification": False,
        "status": "clarification_passed"
    }


def await_clarification_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    logger.info("Resuming execution from clarification gate...")
    return {"status": "clarification_provided"}

def compile_documents_node(state: AnalysisState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    if state.get("error"):
        return {}
        
    repo_id = state["repository_id"]
    approved_facts = state.get("extracted_facts", [])
    
    job_id = None
    if config:
        job_id = config.get("configurable", {}).get("thread_id")
        
    if job_id:
        db = SessionLocal()
        try:
            db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                "current_node": "compile_documents",
                "status": JobStatus.RUNNING,
                "updated_at": datetime.utcnow()
            })
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update current_node to compile_documents: {e}")
        finally:
            db.close()
            
    logger.info(f"Compiling documents for repo {repo_id}, job {job_id} using {len(approved_facts)} approved facts...")
    
    # 1. Query User details from Database and Redis
    db = SessionLocal()
    user_name = "Developer"
    user_email = ""
    github_username = ""
    bio = ""
    user_id = None
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if repo:
            user_id = repo.user_id
            from app.models import User
            user = db.query(User).filter(User.id == repo.user_id).first()
            if user:
                github_username = user.github_username or ""
                user_email = user.email or ""
                user_name = github_username
                
                if github_username:
                    try:
                        from app.redis_client import redis_client
                        profile_str = redis_client.get(f"github_profile:{github_username}")
                        if profile_str:
                            profile_data = json.loads(profile_str)
                            user_name = profile_data.get("name") or user_name
                            user_email = profile_data.get("email") or user_email
                            bio = profile_data.get("bio") or ""
                    except Exception as redis_err:
                        logger.warning(f"Failed to fetch profile from Redis: {redis_err}")
    except Exception as e:
        logger.error(f"Error querying user metadata: {e}")
    finally:
        db.close()

    # If no user_id found, use a fallback
    user_id_str = str(user_id) if user_id else "system"

    # Helper for LLM Calls
    def call_llm(messages: List[Dict[str, str]], schema: Any) -> Dict[str, Any]:
        from app.logging_config import bind_log_context
        if job_id:
            bind_log_context(job_id=str(job_id))
        bind_log_context(user_id=user_id_str)
        
        with propagate_attributes(user_id=repo_id, session_id=str(job_id) if job_id else None):
            with langfuse.start_as_current_observation(
                as_type="generation",
                name="document_generation",
                model=MODEL_NAME,
                input=messages,
                model_parameters={"temperature": 0.2}
            ) as generation:
                try:
                    response = httpx.post(
                        f"{LITELLM_PROXY_URL}/v1/chat/completions",
                        json={
                            "model": MODEL_NAME,
                            "messages": messages,
                            "temperature": 0.2,
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": schema.__name__,
                                    "schema": schema.model_json_schema(),
                                    "strict": True
                                }
                            }
                        },
                        timeout=120.0
                    )
                    response.raise_for_status()
                    resp_data = response.json()
                except Exception as call_err:
                    try:
                        from app.metrics import llm_api_call_total
                        llm_api_call_total.labels(provider="gemini", model=MODEL_NAME, status="failure").inc()
                    except Exception:
                        pass
                    raise call_err
                
                usage = resp_data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                
                try:
                    from app.metrics import llm_api_call_total, llm_token_consumption_total
                    llm_api_call_total.labels(provider="gemini", model=MODEL_NAME, status="success").inc()
                    llm_token_consumption_total.labels(user_id=user_id_str, model=MODEL_NAME, type="prompt").inc(prompt_tokens)
                    llm_token_consumption_total.labels(user_id=user_id_str, model=MODEL_NAME, type="completion").inc(completion_tokens)
                except Exception as metric_err:
                    logger.error(f"Failed to record LLM success metrics: {metric_err}")
                
                content = resp_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                
                generation.update(
                    output=content,
                    usage_details={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": prompt_tokens + completion_tokens
                    }
                )
                return {
                    "parsed": parsed,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens
                }

    # Helper for compiler self-healing LLM call
    def call_self_healing_llm(messages: List[Dict[str, str]]) -> Dict[str, Any]:
        from app.llm_schemas import LaTeXSelfHealingResponse
        return call_llm(messages, LaTeXSelfHealingResponse)

    # 2. Compile LaTeX Resume to PDF with AI Self-Healing Loop
    facts_str = json.dumps(approved_facts, indent=2)
    messages_resume = [
        {
            "role": "system",
            "content": (
                "You are an expert Senior Technical Recruiter and professional LaTeX designer.\n"
                "Your task is to compile a LaTeX developer resume using the candidate's verified repository facts.\n\n"
                "Step 1: ATS Optimizer Reasoning Pass\n"
                "Analyze the candidate's tech stack and code facts. Map technical keywords to standard ATS categories, select high-impact action verbs (e.g. 'Architected', 'Optimized', 'Configured') in active voice, and formulate a page-budget plan to fit the content onto exactly one page.\n\n"
                "Step 2: LaTeX Code Generation\n"
                "Generate a complete, compilation-ready LaTeX resume using standard packages (like fullpage, titlesec, enumitem, hyperref, geometry).\n"
                "Guidelines:\n"
                "- Name: [NAME], Email: [EMAIL], GitHub: [GITHUB], LinkedIn: [LINKEDIN]\n"
                "- Strictly limit the length to EXACTLY one page. Reduce spacing, margins (e.g. \\addtolength{\\oddsidemargin}{-0.5in}, \\addtolength{\\topmargin}{-0.5in}), and item spacing to guarantee a single-page budget.\n"
                "- Write out the LaTeX code inside the json field `latex_code`.\n"
                "- Do NOT escape LaTeX characters in the JSON output (e.g. write \\section, not \\\\section, but make sure to escape special characters in LaTeX text properly like \\% for percent, \\& for ampersand, and \\_ for underscores)."
            )
        },
        {
            "role": "user",
            "content": (
                f"Candidate Name: {user_name}\n"
                f"Candidate Email: {user_email}\n"
                f"GitHub Link: github.com/{github_username}\n"
                f"LinkedIn Link: linkedin.com/in/{github_username}\n"
                f"Brief Bio: {bio}\n\n"
                f"Approved Technical Facts:\n{facts_str}"
            )
        }
    ]
    
    logger.info("Calling LLM to generate initial LaTeX resume...")
    from app.llm_schemas import LaTeXResumeResponse
    start_time = time.time()
    try:
        res_resume = call_llm(messages_resume, LaTeXResumeResponse)
        latex_code = res_resume["parsed"]["latex_code"]
        ats_reasoning = res_resume["parsed"]["ats_reasoning"]
        prompt_tokens_res = res_resume["prompt_tokens"]
        completion_tokens_res = res_resume["completion_tokens"]
    except Exception as e:
        logger.exception(f"Failed to generate initial LaTeX resume: {e}")
        return {"status": "failed", "error": f"LaTeX generation error: {str(e)}"}

    # Define LaTeX compile helper
    def compile_latex(latex_content: str, output_dir: str) -> str:
        tex_path = os.path.join(output_dir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_content)
        
        # Run pdflatex twice
        for i in range(2):
            res = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                cwd=output_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res.returncode != 0:
                log_path = os.path.join(output_dir, "resume.log")
                log_tail = ""
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                        lines = lf.readlines()
                        log_tail = "".join(lines[-30:])
                raise RuntimeError(f"pdflatex compilation failed (exit code {res.returncode}):\n{log_tail}")
                
        pdf_path = os.path.join(output_dir, "resume.pdf")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError("Compiled PDF file not found after successful compilation run.")
        return pdf_path

    # Self-healing loop
    compile_success = False
    error_log = ""
    retry_count = 0
    max_retries = 3
    pdf_bytes = b""
    
    while not compile_success and retry_count <= max_retries:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                logger.info(f"LaTeX compile attempt {retry_count}...")
                pdf_path = compile_latex(latex_code, tmpdir)
                with open(pdf_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                compile_success = True
                try:
                    from app.metrics import latex_compilation_retry_total
                    latex_compilation_retry_total.labels(status="success", attempt=str(retry_count)).inc()
                except Exception as metric_err:
                    logger.error(f"Failed to record LaTeX success metric: {metric_err}")
                logger.info("LaTeX resume compiled successfully!")
                
                # Clear error message on success
                if job_id:
                    db = SessionLocal()
                    try:
                        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                            "error_message": f"LaTeX compiled successfully with {retry_count} self-healing iterations." if retry_count > 0 else None,
                            "updated_at": datetime.utcnow()
                        })
                        db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to clear error_message: {db_err}")
                    finally:
                        db.close()
            except Exception as compile_err:
                error_log = str(compile_err)
                try:
                    from app.metrics import latex_compilation_retry_total
                    latex_compilation_retry_total.labels(status="failure", attempt=str(retry_count)).inc()
                except Exception as metric_err:
                    logger.error(f"Failed to record LaTeX failure metric: {metric_err}")
                logger.warning(f"LaTeX compile attempt {retry_count} failed: {error_log}")
                
                # Log diagnostic to database
                if job_id:
                    db = SessionLocal()
                    try:
                        db.query(AnalysisJob).filter(AnalysisJob.id == job_id).update({
                            "error_message": f"LaTeX compilation attempt {retry_count} failed:\n{error_log}",
                            "updated_at": datetime.utcnow()
                        })
                        db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to log self-healing diagnostic: {db_err}")
                    finally:
                        db.close()
                
                if retry_count == max_retries:
                    break
                
                retry_count += 1
                
                # Call LLM to diagnose and heal
                try:
                    logger.info("Invoking AI Self-Healing LLM pass...")
                    messages_healing = [
                        {
                            "role": "system",
                            "content": (
                                "You are an expert LaTeX compiler and troubleshooter.\n"
                                "The user is trying to compile a LaTeX resume, but the compilation failed with a pdflatex error.\n"
                                "Analyze the invalid LaTeX code and the compiler log tail, diagnose the root cause (e.g. unescaped characters like %, &, _, missing packages, mismatched brackets), and output the corrected, complete LaTeX code.\n\n"
                                "Important guidelines:\n"
                                "- Do NOT truncate or write partial code. Output the COMPLETE corrected LaTeX source code.\n"
                                "- Ensure it adheres strictly to a single-page budget."
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"--- INVALID LATEX CODE ---\n{latex_code}\n\n"
                                f"--- COMPILER LOG ERROR ---\n{error_log}\n\n"
                                "Please output the corrected LaTeX code in the structured JSON response format."
                            )
                        }
                    ]
                    res_healing = call_self_healing_llm(messages_healing)
                    latex_code = res_healing["parsed"]["latex_code"]
                    diagnosed_cause = res_healing["parsed"]["diagnosed_cause"]
                    logger.info(f"Self-Healing Diagnosis: {diagnosed_cause}")
                    
                    # Accumulate token counts
                    prompt_tokens_res += res_healing["prompt_tokens"]
                    completion_tokens_res += res_healing["completion_tokens"]
                except Exception as heal_err:
                    logger.error(f"Failed to run AI Self-Healing LLM pass: {heal_err}")
                    break

    if not compile_success:
        logger.error("LaTeX resume compilation failed after maximum self-healing retries.")
        return {
            "status": "failed",
            "error": f"LaTeX compiler failed: {error_log}"
        }

    # 3. Generate Markdown Outputs (LinkedIn, README, Portfolio)
    messages_md = [
        {
            "role": "system",
            "content": (
                "You are a stellar Developer Relations Manager and copywriter.\n"
                "Your task is to synthesize the candidate's approved repository facts into three cohesive marketing documents:\n"
                "1. LinkedIn Project Description: A professional, compelling LinkedIn summary of the project's features and achievements.\n"
                "2. GitHub Profile README: A beautifully structured markdown README.md for this repository detailing features, architecture, setup/install instructions, and a quickstart guide.\n"
                "3. Developer Portfolio Page: A detailed project breakdown page highlighting design trade-offs, tech stack complexity, and security/performance optimizations."
            )
        },
        {
            "role": "user",
            "content": (
                f"Project Owner: {user_name}\n"
                f"Project URL: {state.get('github_url')}\n"
                f"Approved Technical Facts:\n{facts_str}"
            )
        }
    ]
    
    logger.info("Calling LLM to generate Markdown documents (LinkedIn, README, Portfolio)...")
    from app.llm_schemas import MarkdownOutputsResponse
    try:
        res_md = call_llm(messages_md, MarkdownOutputsResponse)
        linkedin_summary = res_md["parsed"]["linkedin_summary"]
        github_readme = res_md["parsed"]["github_readme"]
        developer_portfolio = res_md["parsed"]["developer_portfolio"]
        prompt_tokens_md = res_md["prompt_tokens"]
        completion_tokens_md = res_md["completion_tokens"]
    except Exception as e:
        logger.exception(f"Failed to generate Markdown documents: {e}")
        return {"status": "failed", "error": f"Markdown generation error: {str(e)}"}

    # 4. Upload all files to MinIO and register in database
    s3 = get_s3_client()
    bucket_name = "repoproof-data"
    
    # Ensure MinIO bucket exists
    try:
        s3.create_bucket(Bucket=bucket_name)
    except s3.exceptions.BucketAlreadyExists:
        pass
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    # Helper to upload file to MinIO
    def upload_to_minio(key: str, body: Any, content_type: str):
        logger.info(f"Uploading output to MinIO: {key}...")
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=body,
            ContentType=content_type
        )

    # Helper to register GeneratedOutput
    def register_generated_output(output_type: OutputType, content: str, object_key: str, p_tok: int, c_tok: int, dur_ms: int):
        if not job_id:
            return
        db = SessionLocal()
        try:
            from app.models import GeneratedOutput
            existing = db.query(GeneratedOutput).filter(
                GeneratedOutput.analysis_job_id == job_id,
                GeneratedOutput.output_type == output_type
            ).first()
            
            if existing:
                existing.version += 1
                existing.content = content
                existing.minio_object_key = object_key
                existing.llm_model_used = MODEL_NAME
                existing.prompt_tokens = p_tok
                existing.completion_tokens = c_tok
                existing.generation_duration_ms = dur_ms
                existing.updated_at = datetime.utcnow()
            else:
                new_out = GeneratedOutput(
                    analysis_job_id=job_id,
                    output_type=output_type,
                    content=content,
                    version=1,
                    is_current_version=True,
                    llm_model_used=MODEL_NAME,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    generation_duration_ms=dur_ms,
                    minio_object_key=object_key
                )
                db.add(new_out)
            db.commit()
        except Exception as err:
            logger.error(f"Failed to register GeneratedOutput for {output_type}: {err}")
            db.rollback()
        finally:
            db.close()

    # Upload & register outputs
    key_prefix = f"outputs/{user_id_str}/{job_id if job_id else 'temp'}"
    
    # Resume (.pdf and .tex)
    resume_pdf_key = f"{key_prefix}/resume.pdf"
    resume_tex_key = f"{key_prefix}/resume.tex"
    upload_to_minio(resume_pdf_key, pdf_bytes, "application/pdf")
    upload_to_minio(resume_tex_key, latex_code, "application/x-tex")
    
    dur_ms_res = int((time.time() - start_time) * 1000)
    register_generated_output(
        OutputType.RESUME_BULLETS,
        latex_code,
        resume_pdf_key,
        prompt_tokens_res,
        completion_tokens_res,
        dur_ms_res
    )
    
    # LinkedIn
    linkedin_key = f"{key_prefix}/linkedin.md"
    upload_to_minio(linkedin_key, linkedin_summary, "text/markdown")
    register_generated_output(
        OutputType.LINKEDIN_DESC,
        linkedin_summary,
        linkedin_key,
        prompt_tokens_md,
        completion_tokens_md,
        dur_ms_res
    )
    
    # README
    readme_key = f"{key_prefix}/readme.md"
    upload_to_minio(readme_key, github_readme, "text/markdown")
    register_generated_output(
        OutputType.README,
        github_readme,
        readme_key,
        prompt_tokens_md,
        completion_tokens_md,
        dur_ms_res
    )
    
    # Portfolio
    portfolio_key = f"{key_prefix}/portfolio.md"
    upload_to_minio(portfolio_key, developer_portfolio, "text/markdown")
    register_generated_output(
        OutputType.PORTFOLIO_DOC,
        developer_portfolio,
        portfolio_key,
        prompt_tokens_md,
        completion_tokens_md,
        dur_ms_res
    )

    # Accumulate tokens used
    total_prompt = prompt_tokens_res + prompt_tokens_md
    total_comp = completion_tokens_res + completion_tokens_md
    total_cost = (total_prompt * 0.10 + total_comp * 0.40) / 1000000.0

    return {
        "llm_tokens_used": state.get("llm_tokens_used", 0) + total_prompt + total_comp,
        "llm_cost_usd": float(state.get("llm_cost_usd", 0.0)) + total_cost,
        "status": "documents_compiled"
    }

# Build LangGraph Workflow
workflow = StateGraph(AnalysisState)

workflow.add_node("clone_repo", clone_repo_node)
workflow.add_node("extract_facts", extract_heuristic_facts_node)
workflow.add_node("extract_llm_facts", extract_llm_facts_node)
workflow.add_node("validate_facts", validate_facts_node)
workflow.add_node("save_intermediate", save_intermediate_results_node)
workflow.add_node("await_human_review", await_human_review_node)
workflow.add_node("check_missing_context", check_missing_context_node)
workflow.add_node("await_clarification", await_clarification_node)
workflow.add_node("compile_documents", compile_documents_node)
workflow.add_node("upload_metadata", upload_metadata_node)

def should_clarify(state: AnalysisState) -> str:
    if state.get("needs_clarification"):
        return "await_clarification"
    return "compile_documents"

# Define edges
workflow.add_edge(START, "clone_repo")
workflow.add_edge("clone_repo", "extract_facts")
workflow.add_edge("extract_facts", "extract_llm_facts")
workflow.add_edge("extract_llm_facts", "validate_facts")
workflow.add_edge("validate_facts", "save_intermediate")
workflow.add_edge("save_intermediate", "await_human_review")
workflow.add_edge("await_human_review", "check_missing_context")
workflow.add_conditional_edges(
    "check_missing_context",
    should_clarify,
    {
        "await_clarification": "await_clarification",
        "compile_documents": "compile_documents"
    }
)
workflow.add_edge("await_clarification", "check_missing_context")
workflow.add_edge("compile_documents", "upload_metadata")
workflow.add_edge("upload_metadata", END)

# Compile graph with persistence
try:
    checkpointer = get_checkpointer()
    analysis_graph = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_human_review", "await_clarification"]
    )
except Exception as e:
    logger.exception(f"Failed to compile LangGraph: {e}")
    analysis_graph = workflow.compile(
        interrupt_before=["await_human_review", "await_clarification"]
    )  # Fallback to no checkpointer for compiling safety


def regenerate_single_output(
    output_id: str,
    ats_mode: Optional[str] = None,
    custom_instructions: Optional[str] = None
) -> GeneratedOutput:
    db = SessionLocal()
    try:
        # Fetch output
        output = db.query(GeneratedOutput).filter(GeneratedOutput.id == output_id).first()
        if not output:
            raise ValueError("Output not found")
            
        # Get job & repo
        job = db.query(AnalysisJob).filter(AnalysisJob.id == output.analysis_job_id).first()
        if not job:
            raise ValueError("Analysis job not found")
            
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if not repo:
            raise ValueError("Repository not found")
            
        # Fetch approved facts from MinIO
        s3 = get_s3_client()
        bucket_name = "repoproof-data"
        facts = []
        try:
            s3_resp = s3.get_object(Bucket=bucket_name, Key=f"repos/{repo.id}/analysis_result.json")
            result_data = json.loads(s3_resp["Body"].read().decode("utf-8"))
            facts = result_data.get("facts", [])
        except Exception as s3_err:
            logger.warning(f"Could not read analysis_result.json from MinIO: {s3_err}")
            
        # Fetch user info
        user_name = "Developer"
        user_email = ""
        github_username = ""
        bio = ""
        
        from app.models import User
        user = db.query(User).filter(User.id == repo.user_id).first()
        if user:
            github_username = user.github_username or ""
            user_email = user.email or ""
            user_name = github_username
            if github_username:
                try:
                    from app.redis_client import redis_client
                    profile_str = redis_client.get(f"github_profile:{github_username}")
                    if profile_str:
                        profile_data = json.loads(profile_str)
                        user_name = profile_data.get("name") or user_name
                        user_email = profile_data.get("email") or user_email
                        bio = profile_data.get("bio") or ""
                except Exception as redis_err:
                    logger.warning(f"Failed to fetch profile from Redis: {redis_err}")
                    
        # Helper for LLM Calls
        def call_llm(messages: List[Dict[str, str]], schema: Any) -> Dict[str, Any]:
            with propagate_attributes(user_id=str(repo.id), session_id=str(job.id)):
                with langfuse.start_as_current_observation(
                    as_type="generation",
                    name="document_regeneration",
                    model=MODEL_NAME,
                    input=messages,
                    model_parameters={"temperature": 0.2}
                ) as generation:
                    response = httpx.post(
                        f"{LITELLM_PROXY_URL}/v1/chat/completions",
                        json={
                            "model": MODEL_NAME,
                            "messages": messages,
                            "temperature": 0.2,
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": schema.__name__,
                                    "schema": schema.model_json_schema(),
                                    "strict": True
                                }
                            }
                        },
                        timeout=120.0
                    )
                    response.raise_for_status()
                    resp_data = response.json()
                    
                    usage = resp_data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    
                    content = resp_data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    
                    generation.update(
                        output=content,
                        usage_details={
                            "input": prompt_tokens,
                            "output": completion_tokens,
                            "total": prompt_tokens + completion_tokens
                        }
                    )
                    return {
                        "parsed": parsed,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens
                    }

        facts_str = json.dumps(facts, indent=2)
        start_time = time.time()
        
        if output.output_type == OutputType.RESUME_BULLETS:
            # 1. Regenerate LaTeX Resume
            messages_resume = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Senior Technical Recruiter and professional LaTeX designer.\n"
                        "Your task is to update or regenerate a LaTeX developer resume using the candidate's verified repository facts, "
                        "their current LaTeX template source, and custom edit instructions.\n\n"
                        "Step 1: ATS Optimizer Reasoning Pass\n"
                        "Analyze the candidate's tech stack, code facts, current LaTeX source, and instructions. "
                        "Choose the best action verbs and keep a strict single-page budget.\n\n"
                        "Step 2: LaTeX Code Generation\n"
                        "Generate a complete, compilation-ready LaTeX resume. Adjust spacing and margins to guarantee one page.\n"
                        "Guidelines:\n"
                        "- Adjust according to custom instructions.\n"
                        "- Strictly limit length to one page.\n"
                        "- Do NOT escape LaTeX characters in JSON (write \\section, not \\\\section, but make sure to escape special characters in LaTeX text properly like \\% for percent, \\& for ampersand, and \\_ for underscores)."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Candidate Name: {user_name}\n"
                        f"Candidate Email: {user_email}\n"
                        f"GitHub Link: github.com/{github_username}\n"
                        f"LinkedIn Link: linkedin.com/in/{github_username}\n"
                        f"Brief Bio: {bio}\n\n"
                        f"Approved Technical Facts:\n{facts_str}\n\n"
                        f"Current LaTeX Code:\n{output.content}\n\n"
                        f"Custom Instructions: {custom_instructions or 'None'}\n"
                        f"ATS Optimization Mode: {ats_mode or 'experienced'}\n\n"
                        "Please output the updated LaTeX code in the structured JSON response format."
                    )
                }
            ]
            
            logger.info("Calling LLM to regenerate LaTeX resume...")
            res_resume = call_llm(messages_resume, LaTeXResumeResponse)
            latex_code = res_resume["parsed"]["latex_code"]
            prompt_tokens_res = res_resume["prompt_tokens"]
            completion_tokens_res = res_resume["completion_tokens"]
            
            # Helper for compiler self-healing
            def call_self_healing_llm(messages: List[Dict[str, str]]) -> Dict[str, Any]:
                return call_llm(messages, LaTeXSelfHealingResponse)
                
            def compile_latex(latex_content: str, output_dir: str) -> str:
                tex_path = os.path.join(output_dir, "resume.tex")
                with open(tex_path, "w", encoding="utf-8") as f:
                    f.write(latex_content)
                for i in range(2):
                    res = subprocess.run(
                        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                        cwd=output_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    if res.returncode != 0:
                        log_path = os.path.join(output_dir, "resume.log")
                        log_tail = ""
                        if os.path.exists(log_path):
                            with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                                lines = lf.readlines()
                                log_tail = "".join(lines[-30:])
                        raise RuntimeError(f"pdflatex compilation failed (exit code {res.returncode}):\n{log_tail}")
                pdf_path = os.path.join(output_dir, "resume.pdf")
                return pdf_path

            compile_success = False
            error_log = ""
            retry_count = 0
            max_retries = 3
            pdf_bytes = b""
            
            while not compile_success and retry_count <= max_retries:
                with tempfile.TemporaryDirectory() as tmpdir:
                    try:
                        pdf_path = compile_latex(latex_code, tmpdir)
                        with open(pdf_path, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()
                        compile_success = True
                    except Exception as compile_err:
                        error_log = str(compile_err)
                        if retry_count == max_retries:
                            break
                        retry_count += 1
                        messages_healing = [
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert LaTeX compiler and troubleshooter.\n"
                                    "The user is trying to compile a LaTeX resume, but the compilation failed with a pdflatex error.\n"
                                    "Analyze the invalid LaTeX code and the compiler log tail, diagnose the root cause, and output the corrected, complete LaTeX code.\n\n"
                                    "Important guidelines:\n"
                                    "- Do NOT truncate or write partial code. Output the COMPLETE corrected LaTeX source code.\n"
                                    "- Ensure it adheres strictly to a single-page budget."
                                )
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"--- INVALID LATEX CODE ---\n{latex_code}\n\n"
                                    f"--- COMPILER LOG ERROR ---\n{error_log}\n\n"
                                    "Please output the corrected LaTeX code in the structured JSON response format."
                                )
                            }
                        ]
                        res_healing = call_self_healing_llm(messages_healing)
                        latex_code = res_healing["parsed"]["latex_code"]
                        prompt_tokens_res += res_healing["prompt_tokens"]
                        completion_tokens_res += res_healing["completion_tokens"]
                        
            if not compile_success:
                raise RuntimeError(f"LaTeX compilation failed after {max_retries} retries. Error: {error_log}")
                
            # Upload to MinIO
            s3.put_object(
                Bucket=bucket_name,
                Key=output.minio_object_key,
                Body=pdf_bytes,
                ContentType="application/pdf"
            )
            # Also upload the updated tex file
            tex_key = output.minio_object_key.replace(".pdf", ".tex")
            s3.put_object(
                Bucket=bucket_name,
                Key=tex_key,
                Body=latex_code,
                ContentType="application/x-tex"
            )
            
            output.content = latex_code
            output.prompt_tokens = prompt_tokens_res
            output.completion_tokens = completion_tokens_res
            
        else:
            # Markdown outputs (LinkedIn, README, Portfolio)
            doc_names = {
                OutputType.LINKEDIN_DESC: "LinkedIn Project Description",
                OutputType.README: "GitHub Profile README",
                OutputType.PORTFOLIO_DOC: "Developer Portfolio Page"
            }
            doc_name = doc_names.get(output.output_type, "Document")
            
            messages_md = [
                {
                    "role": "system",
                    "content": (
                        "You are a stellar Developer Relations Manager and copywriter.\n"
                        f"Your task is to update or regenerate a {doc_name} for the candidate, "
                        "using their approved technical facts, the existing document content, and custom edit instructions.\n\n"
                        "Make sure to output the updated complete document under the `content` JSON field."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Project Owner: {user_name}\n"
                        f"Project URL: {repo.github_url}\n"
                        f"Approved Technical Facts:\n{facts_str}\n\n"
                        f"Current Document Content:\n{output.content}\n\n"
                        f"Custom Edit Instructions:\n{custom_instructions or 'None'}\n\n"
                        "Please output the updated content in the structured JSON response format."
                    )
                }
            ]
            
            res_md = call_llm(messages_md, SingleMarkdownResponse)
            new_content = res_md["parsed"]["content"]
            
            # Upload to MinIO
            s3.put_object(
                Bucket=bucket_name,
                Key=output.minio_object_key,
                Body=new_content,
                ContentType="text/markdown"
            )
            
            output.content = new_content
            output.prompt_tokens = res_md["prompt_tokens"]
            output.completion_tokens = res_md["completion_tokens"]
            
        output.version += 1
        output.generation_duration_ms = int((time.time() - start_time) * 1000)
        output.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(output)
        return output
        
    except Exception as e:
        db.rollback()
        logger.exception(f"Error regenerating output {output_id}: {e}")
        raise e
    finally:
        db.close()


