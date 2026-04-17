"""
src/db/models.py
─────────────────
SQLAlchemy ORM models.

Tables:
  - jobs         — One row per open role; owns pipeline_state
  - candidates   — People who apply
  - applications — Junction: which candidate applied to which job + scoring
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text, JSON, text, UniqueConstraint,
    FetchedValue
)

from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.db.database import Base


# ─────────────────────────────────────────────────────────────
# Pipeline State Enum (stored in DB per job)
# ─────────────────────────────────────────────────────────────
class PipelineState(str, enum.Enum):
    JD_DRAFT                   = "JD_DRAFT"
    JD_APPROVAL_PENDING        = "JD_APPROVAL_PENDING"
    JD_APPROVED                = "JD_APPROVED"
    JOB_POSTED                 = "JOB_POSTED"
    WAITING_FOR_APPLICATIONS   = "WAITING_FOR_APPLICATIONS"
    SCREENING                  = "SCREENING"
    HR_REVIEW_PENDING          = "HR_REVIEW_PENDING"
    INTERVIEW_SCHEDULED        = "INTERVIEW_SCHEDULED"
    OFFER_SENT                 = "OFFER_SENT"
    CLOSED                     = "CLOSED"
    ESCALATED                  = "ESCALATED"
    FAILED                     = "FAILED"


# ─────────────────────────────────────────────────────────────
# Circuit Breaker Status Enum (Step 2: Distributed Resilience)
# ─────────────────────────────────────────────────────────────
class CircuitBreakerStatus(str, enum.Enum):
    CLOSED    = "CLOSED"     # Normal operation
    OPEN      = "OPEN"       # Failing, blocking requests
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with single probe


class CircuitBreakerState(Base):
    __tablename__ = "circuit_breaker_states"

    service_name         = Column(String(100), primary_key=True)  # e.g., 'ollama', 'openai', 'resend'
    status               = Column(Enum(CircuitBreakerStatus, native_enum=False, length=50), default=CircuitBreakerStatus.CLOSED, server_default="CLOSED")
    last_failure_at      = Column(DateTime(timezone=True))
    probe_started_at     = Column(DateTime(timezone=True))
    consecutive_failures = Column(Integer, default=0, server_default="0")
    error_message        = Column(Text)

    updated_at           = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=text("now()"))



# ─────────────────────────────────────────────────────────────
# Organization Model (SaaS Multi-Tenancy)
# ─────────────────────────────────────────────────────────────
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"))
    
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    integrations = relationship("Integration", back_populates="organization", cascade="all, delete-orphan")
    # In Step 2, Jobs will be linked here


# ─────────────────────────────────────────────────────────────
# User Model (SaaS Multi-Tenancy)
# ─────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    admin = "admin"
    interviewer = "interviewer"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(Text, unique=True, nullable=False)
    hashed_password = Column(Text)
    name = Column(Text)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(UserRole, native_enum=False, length=50), default=UserRole.admin, server_default="admin")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"))

    # Email Verification
    is_email_verified = Column(Boolean, default=False, server_default='false', index=True)
    email_verification_otp_hash = Column(Text, nullable=True)
    email_verification_expires = Column(DateTime(timezone=True), nullable=True)
    email_verification_attempts = Column(Integer, default=0, server_default='0')

    # Google OAuth (Step 1)
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expiry = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="users")
    interviewer_stages = relationship("JobStage", back_populates="interviewer")
    feedback = relationship("InterviewFeedback", back_populates="interviewer")
    interviews = relationship("Interview", back_populates="interviewer")


# ─────────────────────────────────────────────────────────────
# Invite Model (Team RBAC)
# ─────────────────────────────────────────────────────────────
class Invite(Base):
    __tablename__ = "invites"

    id              = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email           = Column(Text, nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(Text, nullable=False, default="interviewer")  # admin | hiring_manager | interviewer
    token           = Column(Text, unique=True, nullable=False)             # cryptographically secure token
    status          = Column(Text, default="pending", server_default="pending")  # pending | accepted | expired
    expires_at      = Column(DateTime(timezone=True), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"))

    organization = relationship("Organization")


# ─────────────────────────────────────────────────────────────
# Integration Model (External Providers)
# ─────────────────────────────────────────────────────────────
class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(100), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="active", server_default="active")
    provider_metadata = Column("metadata", JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    organization = relationship("Organization", back_populates="integrations")

    __table_args__ = (
        UniqueConstraint('organization_id', 'provider', name='uq_integration_org_provider'),
    )


# ─────────────────────────────────────────────────────────────
# Job Model
# ─────────────────────────────────────────────────────────────
class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)

    # HR-submitted fields
    title                = Column(String(255), nullable=False)
    department           = Column(String(255))
    hiring_manager_name  = Column(String(255))
    hiring_manager_email = Column(String(255))
    requirements         = Column(Text)          # raw hiring requirements text or generated list
    salary_range         = Column(String(100))
    location             = Column(String(255))
    experience_required  = Column(String(100))
    employment_type      = Column(String(100))
    joining_requirement  = Column(String(255))
    required_skills      = Column(JSON)          # list[str]
    preferred_skills     = Column(JSON)          # list[str]

    # Note: 'screening_questions' array removed, now using a separate table

    technical_test_type  = Column(String(50))    # 'external', 'mcq', or None
    technical_test_link  = Column(String(500))
    technical_test_mcq   = Column(JSON)          # list[dict]
    hiring_workflow      = Column(JSON)          # list[str]
    scoring_weights      = Column(JSON)          # dict (semantic, llm, screening, test)
    template_type        = Column(String(50), default="startup", server_default="startup")  # JD style: startup | corporate | fresher

    # Generated / pipeline fields
    jd_draft             = Column(Text)          # legacy / full json draft
    summary              = Column(Text)          # 2-layer: short preview card text
    full_jd              = Column(Text)          # 2-layer: full formatted string
    jd_revision_count    = Column(Integer, default=0)
    jd_approved          = Column(Boolean, default=False)
    hr_feedback          = Column(Text)
    published_jd_url     = Column(String(500))
    repost_attempts      = Column(Integer, default=0)
    external_post_id     = Column(Text, nullable=True)

    # LangGraph thread_id (used to resume graph)
    graph_thread_id      = Column(String(100), unique=True)

    # State machine
    pipeline_state = Column(
        Enum(PipelineState, name="pipeline_state_enum"),
        default=PipelineState.JD_DRAFT,
        nullable=False,
        index=True,
    )
    status_field = Column("status", String(50), default="PROCESSING") # ACTION_REQUIRED | PROCESSING | INTERVIEW_SCHEDULED | PAUSED
    interrupt_payload = Column(JSONB, nullable=True) # Frozen state for Human-in-the-loop recovery
    current_stage = Column(String(100))        # e.g., 'shortlisting', 'interview_scheduling'
    is_cancelled = Column(Boolean, default=False, server_default="false")  # HR cancelled pipeline mid-flow

    # ── [NEW] Production Hardening (Lease + Versioning) ───────
    locked_by        = Column(UUID(as_uuid=True), index=True) # Worker ID (process UUID)
    locked_at        = Column(DateTime(timezone=True))
    pipeline_version = Column(String(50), default="1.0.0", server_default="1.0.0")
    last_email_version = Column(Integer, default=1, server_default="1")
    normalized_role = Column(String(100), index=True)
    scoring_blueprint = Column(JSON, nullable=True) # AI-generated evaluation profile (must-have, good-to-have)


    # Timestamps
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    stages = relationship("JobStage", back_populates="job", cascade="all, delete-orphan", order_by="JobStage.stage_order")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")
    screening_questions_list = relationship("ScreeningQuestion", back_populates="job", cascade="all, delete-orphan")
    tests_list = relationship("Test", back_populates="job", cascade="all, delete-orphan")
    feedback = relationship("InterviewFeedback", back_populates="job", cascade="all, delete-orphan")

    @property
    def status(self) -> str:
        """User-friendly frontend status computed from the complex LangGraph pipeline_state."""
        if self.is_cancelled:
            return "closed"
        val = self.pipeline_state.value if self.pipeline_state else "JD_DRAFT"
        if val == "JD_DRAFT":
            return "processing"
        elif val == "JD_APPROVAL_PENDING":
            return "draft"
        elif val in ("SCREENING", "HR_REVIEW_PENDING"):
            return "processing"
        elif val in ("JD_APPROVED", "JOB_POSTED", "WAITING_FOR_APPLICATIONS", "INTERVIEW_SCHEDULED"):
            return "active"
        else:
            return "closed"

    updated_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    posted_at      = Column(DateTime(timezone=True))
    closed_at      = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<Job {self.id} - {self.title} ({self.status})>"


# ─────────────────────────────────────────────────────────────
# Job Stage Model (Interview Workflow)
# ─────────────────────────────────────────────────────────────
class JobStage(Base):
    __tablename__ = "job_stages"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id           = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_name       = Column(Text, nullable=False)
    stage_order      = Column(Integer, nullable=False, default=0)
    # Role-based access: specific interviewer for this stage
    interviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # ── [NEW] Custom Instructions ──────────────────────────────
    stage_instructions = Column(Text, nullable=True) # AI hints for the interviewer
    
    created_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    # Relationships
    job           = relationship("Job", back_populates="stages")
    interviewer   = relationship("User", back_populates="interviewer_stages")
    feedback      = relationship("InterviewFeedback", back_populates="stage")

class ScreeningQuestion(Base):
    """
    Step 3: Advanced Screening Question configurations per Job.
    """
    __tablename__ = "screening_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(String(500), nullable=False)
    question_type = Column(String(50), nullable=False)  # 'yes_no', 'text', 'number', 'multiple_choice'
    is_required = Column(Boolean, default=True)
    options = Column(JSON)  # For multiple_choice

    job = relationship("Job", back_populates="screening_questions_list")

    def __repr__(self):
        return f"<ScreeningQuestion {self.question_type}: {self.question}>"


class Test(Base):
    """
    Step 4: Technical Tests configurations per Job.
    """
    __tablename__ = "tests"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False) # e.g., 'mcq'
    
    job = relationship("Job", back_populates="tests_list")
    questions = relationship("TestQuestion", back_populates="test", cascade="all, delete-orphan")
    results = relationship("TestResult", back_populates="test", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Test {self.id} type={self.type}>"

class TestQuestion(Base):
    """Questions belonging to an internal Test (e.g. MCQ)."""
    __tablename__ = "test_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(String(500), nullable=False)
    options = Column(JSON, nullable=False)
    correct_index = Column(Integer, nullable=False)

    test = relationship("Test", back_populates="questions")

class TestResult(Base):
    """Results of a candidate taking a Test."""
    __tablename__ = "test_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    completed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    test = relationship("Test", back_populates="results")
    candidate = relationship("Candidate")


# ─────────────────────────────────────────────────────────────
# Candidate Model
# ─────────────────────────────────────────────────────────────
class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)

    name        = Column(String(255), nullable=False)
    email       = Column(String(255), nullable=False, unique=True, index=True)
    phone       = Column(String(50))
    resume_url  = Column(String(500))
    skills      = Column(JSON)          # list[str]
    experience  = Column(Text)
    linkedin_url = Column(String(500))

    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    applications = relationship("Application", back_populates="candidate")
    feedback      = relationship("InterviewFeedback", back_populates="candidate")
    interviews    = relationship("Interview", back_populates="candidate")

# ─────────────────────────────────────────────────────────────
# Interview Model (Scheduled Events)
# ─────────────────────────────────────────────────────────────
class Interview(Base):
    __tablename__ = "interviews"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    candidate_id    = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    application_id  = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    interviewer_id  = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    scheduled_time  = Column(DateTime(timezone=True), nullable=False)
    meeting_link    = Column(String(500))
    status          = Column(String(50), default="scheduled", server_default="scheduled") # scheduled | completed
    
    # post-interview feedback (Step 3 refinement)
    feedback_rating = Column(Integer)
    feedback_notes  = Column(Text)
    decision        = Column(String(50)) # hire | strong_hire | reject
    
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    candidate   = relationship("Candidate", back_populates="interviews")
    application = relationship("Application")
    interviewer = relationship("User", back_populates="interviews")
    organization = relationship("Organization")


# ─────────────────────────────────────────────────────────────
# Application Model (junction: candidate ↔ job + scoring)
# ─────────────────────────────────────────────────────────────
class Application(Base):
    __tablename__ = "applications"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id       = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True)

    resume_path  = Column(String(500))           # local path or S3 URL
    applied_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Scoring & Stage
    score            = Column(Float)             # 0-100
    stage            = Column(String(50))        # screening | shortlisted | interviewed | rejected
    ai_reasoning     = Column(Text)
    ai_strengths     = Column(JSON)              # list[str]
    ai_gaps          = Column(JSON)              # list[str]
    is_shortlisted   = Column(Boolean, default=False)
    source           = Column(String(50), default="ai", server_default="ai") # ai | manual | referral
    hr_selected      = Column(Boolean)           # None = pending, True/False = HR decision
    is_scored        = Column(Boolean, default=False, server_default="false") # Avoid re-processing
    summary          = Column(Text)              # llm generated summary
    evaluated_at     = Column(DateTime(timezone=True)) # When the LLM actually scored it
    updated_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # ── [NEW] RBAC & Scheduling ─────────────────────────────────
    organization_id      = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True) # Direct tenant link (Step 2 optimization)
    interview_slot       = Column(DateTime(timezone=True))
    calendar_event_id    = Column(String(255))
    meeting_link         = Column(String(500))   # Google Meet URL
    interviewer_email    = Column(String(255))   # who conducts the interview
    interviewer_id       = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # RBAC: interviewer assigned
    invite_sent          = Column(Boolean, default=False)
    offer_sent           = Column(Boolean, default=False)
    feedback_submitted   = Column(Boolean, default=False)
    rejected             = Column(Boolean, default=False)
    rejection_sent       = Column(Boolean, default=False)
    rejected_at          = Column(DateTime(timezone=True))
    current_stage_id     = Column(UUID(as_uuid=True), ForeignKey("job_stages.id", ondelete="SET NULL"), nullable=True)

    # ── [NEW] Evaluation Fields ─────────────────────────────────
    interviewer_score    = Column(Float)
    interviewer_notes    = Column(Text)

    # Relations
    job       = relationship("Job", back_populates="applications")
    candidate = relationship("Candidate", back_populates="applications")
    current_stage = relationship("JobStage")

    __table_args__ = (
        UniqueConstraint('job_id', 'candidate_id', name='uq_job_candidate_application'),
    )

# ─────────────────────────────────────────────────────────────
# Activity Log Model
# ─────────────────────────────────────────────────────────────
class Activity(Base):
    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)

    message = Column(Text, nullable=False)
    type    = Column(String(100))  # e.g., 'scoring', 'interview_scheduled', 'shortlisted', 'offer_sent', etc.

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job = relationship("Job")

# ─────────────────────────────────────────────────────────────
# Interview Feedback Model
# ─────────────────────────────────────────────────────────────
class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("job_stages.id", ondelete="CASCADE"), nullable=False, index=True)
    interviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    decision = Column(Text, nullable=False) # strong_yes / yes / no / strong_no
    rating = Column(Integer, nullable=False) # 1–5
    feedback_text = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    candidate = relationship("Candidate", back_populates="feedback")
    job = relationship("Job", back_populates="feedback")
    stage = relationship("JobStage", back_populates="feedback")
    interviewer = relationship("User", back_populates="feedback")

    __table_args__ = (
        UniqueConstraint('candidate_id', 'stage_id', 'interviewer_id', name='uq_candidate_stage_interviewer'),
    )


# ─────────────────────────────────────────────────────────────
# Production Hardening Models (Source of Truth)
# ─────────────────────────────────────────────────────────────

class EventStore(Base):
    """
    Step 1 & 4: Distributed event store for pipeline reconstruction.
    """
    __tablename__ = "event_store"

    id         = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id     = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(Text, nullable=False) # e.g. 'JD_GENERATED', 'SCORING_STARTED'
    payload    = Column(JSONB, default={}, server_default='{}')
    sequence   = Column(BigInteger, server_default=FetchedValue())
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"), index=True)



class Outbox(Base):
    """
    Step 2: Guaranteed email dispatching pattern.
    """
    __tablename__ = "outbox"

    id              = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id          = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    type            = Column(Text, nullable=False) # e.g. 'SEND_SHORTLIST'
    payload         = Column(JSONB, nullable=False)
    status          = Column(Text, default="PENDING", server_default="PENDING", index=True) # PENDING | SENT | FAILED
    retry_count     = Column(Integer, default=0, server_default="0")
    last_attempt_at = Column(DateTime(timezone=True))
    version         = Column(Integer, default=1, server_default="1")
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("job_id", "type", "version", name="unique_job_event_version"),
    )



class DeadLetterQueue(Base):
    """
    Step 3: Permanent failure tracking for debugging.
    """
    __tablename__ = "dead_letter_queue"

    id          = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id      = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    type        = Column(Text) # e.g. 'SEND_SHORTLIST' (Phase 15: Critical for replay)
    payload     = Column(JSONB, nullable=False)
    reason      = Column(Text)
    retry_count = Column(Integer)

    failed_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))
