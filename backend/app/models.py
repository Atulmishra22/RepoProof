import enum
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Numeric, ForeignKey, Enum, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.database import Base

# Database Enums
class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"

class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    AWAITING_REVIEW = "awaiting_review"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"

class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETE = "complete"
    FAILED = "failed"
    TIMED_OUT = "timed_out"

class OutputType(str, enum.Enum):
    RESUME_BULLETS = "resume_bullets"
    LINKEDIN_DESC = "linkedin_desc"
    README = "readme"
    PORTFOLIO_DOC = "portfolio_doc"

class DownloadFormat(str, enum.Enum):
    TXT = "txt"
    MD = "md"
    PDF = "pdf"
    JSON = "json"

# Models
class User(Base):
    """
    Primary user account table containing credentials, subscription tiers, and login tracking.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for user uniqueness."
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique email used for sign-in and communication."
    )
    github_username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Nullable GitHub username associated via OAuth connection."
    )
    auth_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Identity provider used (e.g., github, google, credentials)."
    )
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_tier_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SubscriptionTier.FREE,
        server_default="free",
        comment="Determines LLM usage limits and premium feature accesses."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Flag for soft-ban or account suspension."
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp tracking user activity for session invalidation."
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="NextAuth user display name."
    )
    email_verified: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        name="emailVerified",
        nullable=True,
        comment="NextAuth timestamp when email was verified."
    )
    image: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="NextAuth profile image URL."
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Hashed password for developer credentials login."
    )
    # --- Personal Profile Fields (used for LaTeX resume generation) ---
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Full display name for resume header (separate from NextAuth name)."
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Phone number for resume contact line."
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="City/Country for resume header, e.g. 'Delhi, India'."
    )
    college: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="University or college name for education section."
    )
    degree: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Degree and major, e.g. 'BS in Data Science & Applications'."
    )
    cgpa: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="CGPA string, e.g. '7.6 / 10'. Stored as string for flexible formatting."
    )
    graduation_year: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Expected or actual graduation year, e.g. '2027'."
    )
    linkedin_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="Full LinkedIn profile URL for resume links section."
    )
    portfolio_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="Personal portfolio or website URL."
    )
    profile_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True when name+email+target_role are all filled. Used to gate resume generation."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Record creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Record last update timestamp."
    )

    # Relationships
    repositories: Mapped[List["Repository"]] = relationship(
        "Repository",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    analysis_jobs: Mapped[List["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    accounts: Mapped[List["Account"]] = relationship(
        "Account",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    sessions: Mapped[List["Session"]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    usage_metrics: Mapped[List["UsageMetric"]] = relationship(
        "UsageMetric",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    user_preferences: Mapped[List["UserPreference"]] = relationship(
        "UserPreference",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    multi_repo_jobs: Mapped[List["MultiRepoJob"]] = relationship(
        "MultiRepoJob",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Repository(Base):
    """
    Analyzed repository metadata synced from the GitHub API.
    """
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for repository records."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this repository record. Cascade deletes repository when user is removed."
    )
    github_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Full public HTTP repository URL."
    )
    github_repo_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Unique repository ID generated by GitHub’s API to identify renamed repos."
    )
    owner: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Organization or user name owning the repo."
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of the repository."
    )
    default_branch: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="main",
        server_default="main",
        comment="Active default branch (e.g., main or master) used for file pulling."
    )
    primary_language: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Primary language of the repo as detected by GitHub."
    )
    languages: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="JSON map of all languages used and their byte count (from GitHub API)."
    )
    star_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Popularity metric of the repo to weigh project complexity."
    )
    is_private: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if GitHub marked this repo private. Private repos are never shared across users."
    )
    last_commit_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Repository staleness indicator used to check if re-indexing is needed."
    )
    analysis_status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, name="analysis_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AnalysisStatus.PENDING,
        server_default="pending",
        index=True,
        comment="Aggregated user-facing status representing the state of the active analysis."
    )
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the latest completed execution run."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Record creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Record last update timestamp."
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="repositories")
    analysis_jobs: Mapped[List["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="repository",
        cascade="all, delete-orphan"
    )


class AnalysisJob(Base):
    """
    Execution records of LangGraph pipelines dispatched via Celery.
    """
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for the job."
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Repository being processed. Cascade deletes job records on repo removal."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Target user initiating the job. Cascade deletes job records on user deletion."
    )
    celery_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Celery identifier to control, query, or terminate the OS process."
    )
    langgraph_thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="State key mapping the job run to the LangGraph Postgres checkpointer."
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default="queued",
        index=True,
        comment="Job execution state. Helps UI render correct loading overlays."
    )
    current_node: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Last active node in the LangGraph execution flow."
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Total retries attempted across LLM wrapper transient failures."
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Raw stack trace or structured error description on execution failure."
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp marking when the Celery task started execution."
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp marking when job concluded (failed or completed)."
    )
    llm_tokens_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Sum of prompt and completion tokens used throughout this job."
    )
    llm_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=0.0,
        server_default="0.000000",
        comment="Calculated dollar cost of the run based on model token pricing metrics."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Record creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Record last update timestamp."
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="analysis_jobs")
    user: Mapped["User"] = relationship("User", back_populates="analysis_jobs")
    generated_outputs: Mapped[List["GeneratedOutput"]] = relationship(
        "GeneratedOutput",
        back_populates="analysis_job",
        cascade="all, delete-orphan"
    )
    code_facts: Mapped[List["CodeFact"]] = relationship(
        "CodeFact",
        back_populates="analysis_job",
        cascade="all, delete-orphan"
    )


class GeneratedOutput(Base):
    """
    Generated resumes, readmes, and profiles derived from verified repository facts.
    """
    __tablename__ = "generated_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID."
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Job run that generated this text output. Cascade deletes on job removal."
    )
    output_type: Mapped[OutputType] = mapped_column(
        Enum(OutputType, name="output_type_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        comment="Format target (e.g. resume bullet list, markdown readme)."
    )
    content: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="The actual string text output generated."
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Incremental counter tracking revision counts of the outputs."
    )
    is_current_version: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Boolean flag indicating which version is active/visible."
    )
    llm_model_used: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="LLM model descriptor used for tracing and cost tracking."
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Tokens sent in input."
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Tokens generated in output."
    )
    generation_duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Time taken for the generation API call to complete."
    )
    minio_object_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Cloudflare R2 storage path for file retrieval."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Record creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Record last update timestamp."
    )

    # Relationships
    analysis_job: Mapped["AnalysisJob"] = relationship("AnalysisJob", back_populates="generated_outputs")
    downloads: Mapped[List["OutputDownload"]] = relationship(
        "OutputDownload",
        back_populates="output",
        cascade="all, delete-orphan"
    )


class OutputDownload(Base):
    """
    Access audit trail logging user download actions and presigned URL properties.
    """
    __tablename__ = "output_downloads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID."
    )
    output_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_outputs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the downloaded generated file record. Cascade deletes on output removal."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User requesting download. Cascade deletes download logs on user deletion."
    )
    format: Mapped[DownloadFormat] = mapped_column(
        Enum(DownloadFormat, name="download_format_enum", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        comment="Downloaded format (txt, md, pdf, or json)."
    )
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Exact access timestamp."
    )
    presigned_url_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Expiration timestamp for the presigned storage download URL."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Record creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Record last update timestamp."
    )

    # Relationships
    output: Mapped["GeneratedOutput"] = relationship("GeneratedOutput", back_populates="downloads")
    user: Mapped["User"] = relationship("User")


class Account(Base):
    """
    NextAuth adapter table linking users to federated OAuth accounts.
    """
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for account connection."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        name="userId",
        index=True,
        comment="Reference to the users table. Cascade deletes on user removal."
    )
    type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="OAuth provider account type (e.g. oauth, email, credentials)."
    )
    provider: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="OAuth identity provider name (e.g. github, google)."
    )
    provider_account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        name="providerAccountId",
        index=True,
        comment="Unique identifier issued by OAuth provider for the user."
    )
    refresh_token: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="OAuth token refresh credential string."
    )
    access_token: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="OAuth active session token string."
    )
    expires_at: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Active access token expiration epoch timestamp."
    )
    token_type: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Type of token returned (e.g. Bearer)."
    )
    scope: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="OAuth scope permissions list granted by provider."
    )
    id_token: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="OIDC ID token string."
    )
    session_state: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="OAuth session state string."
    )

    __table_args__ = (
        UniqueConstraint("provider", "providerAccountId", name="uq_accounts_provider_provider_account_id"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="accounts")


class Session(Base):
    """
    NextAuth adapter table managing user login sessions.
    """
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for login session."
    )
    session_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        name="sessionToken",
        index=True,
        comment="Secure session authentication token string."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        name="userId",
        index=True,
        comment="Reference to the users table. Cascade deletes on user removal."
    )
    expires: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Session expiration timestamp."
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class VerificationToken(Base):
    """
    NextAuth adapter table for passwordless verification tokens.
    """
    __tablename__ = "verification_tokens"

    identifier: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        comment="Verification subject identifier (e.g. email address)."
    )
    token: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        unique=True,
        comment="Secure validation token string."
    )
    expires: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Verification token expiration timestamp."
    )


class UsageMetric(Base):
    """
    Tracks API and LLM usage metrics per user for audit, rate-limiting fallback, and billing.
    """
    __tablename__ = "usage_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for usage metric record."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User associated with this usage record."
    )
    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The API endpoint accessed (e.g., /analyze, /regenerate)."
    )
    calls_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Number of times endpoint was called."
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Timestamp of the usage occurrence."
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_metrics")


class CodeFact(Base):
    """
    Granular, source-cited facts extracted by LLMs from the analyzed repository.
    """
    __tablename__ = "code_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key UUID for the code fact."
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="Analysis job that generated this fact."
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Category of technical information."
    )
    claim: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Specific technical statement."
    )
    source_file: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Path of the source file serving as evidence."
    )
    snippet: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Extracted source code snippet."
    )
    ats_impact: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Tailored resume/ATS bullet value explanation."
    )
    is_validated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if validation checks succeeded."
    )
    is_human_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if the user approved the fact in HiTL."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow
    )

    # Relationships
    analysis_job: Mapped["AnalysisJob"] = relationship("AnalysisJob", back_populates="code_facts")
    fact_embedding: Mapped[Optional["FactEmbedding"]] = relationship(
        "FactEmbedding",
        back_populates="code_fact",
        cascade="all, delete-orphan"
    )


class FactEmbedding(Base):
    """
    Multidimensional embeddings for approved facts to support semantic context tailoring.
    """
    __tablename__ = "fact_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    code_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("code_facts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    embedding = mapped_column(
        Vector(768),
        nullable=False,
        comment="Gemini text-embedding-004 768-dimensional float array."
    )
    model_used: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model descriptor used to compute the embeddings."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP")
    )

    # Relationships
    code_fact: Mapped["CodeFact"] = relationship("CodeFact", back_populates="fact_embedding")


class UserPreference(Base):
    """
    Style, layout, and keyword rules learned from the user modifications.
    """
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    rule: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Inferred rule representing the user's editing preference."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP")
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_preferences")


class MultiRepoJob(Base):
    """
    Tracks multi-repository resume generation jobs.
    Each job merges approved facts from up to 3 analyzed repos into a unified LaTeX PDF.
    """
    __tablename__ = "multi_repo_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Primary key for the combined resume generation job."
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this job. Cascade deletes with user."
    )
    repo_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of up to 3 repository UUIDs whose approved facts are merged."
    )
    job_status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum", create_constraint=False),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default="queued",
        comment="Current pipeline status of this multi-repo resume job."
    )
    output_pdf_key: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="MinIO object key for the generated combined resume PDF."
    )
    output_tex_key: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="MinIO object key for the generated combined resume .tex source."
    )
    personal_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of user personal profile fields at the time of generation."
    )
    missing_fields: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Fields that were missing and prompted clarification, e.g. ['college', 'phone']."
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="LaTeX compiler error or pipeline failure message."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Job creation timestamp."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        comment="Last status update timestamp."
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="multi_repo_jobs")
