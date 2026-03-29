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
    ForeignKey, Integer, String, Text, JSON, text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
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
# Organization Model (SaaS Multi-Tenancy)
# ─────────────────────────────────────────────────────────────
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"))
    
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    # In Step 2, Jobs will be linked here


# ─────────────────────────────────────────────────────────────
# User Model (SaaS Multi-Tenancy)
# ─────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(Text, unique=True, nullable=False)
    password = Column(Text)
    name = Column(Text)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, default="admin", server_default="admin")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"))

    # Google OAuth (Step 1)
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expiry = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="users")
    assigned_stages = relationship("JobStage", back_populates="assigned_user")
    feedback = relationship("InterviewFeedback", back_populates="interviewer")


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

    # Generated / pipeline fields
    jd_draft             = Column(Text)          # current JD draft
    jd_revision_count    = Column(Integer, default=0)
    jd_approved          = Column(Boolean, default=False)
    hr_feedback          = Column(Text)
    published_jd_url     = Column(String(500))
    repost_attempts      = Column(Integer, default=0)

    # LangGraph thread_id (used to resume graph)
    graph_thread_id      = Column(String(100), unique=True)

    # State machine
    pipeline_state = Column(
        Enum(PipelineState, name="pipeline_state_enum"),
        default=PipelineState.JD_DRAFT,
        nullable=False,
        index=True,
    )
    is_cancelled = Column(Boolean, default=False, server_default="false")  # HR cancelled pipeline mid-flow

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
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    job           = relationship("Job", back_populates="stages")
    assigned_user = relationship("User", back_populates="assigned_stages")
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
    linkedin_url = Column(String(500))

    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    current_stage_id = Column(UUID(as_uuid=True), ForeignKey("job_stages.id", ondelete="SET NULL"), nullable=True)
    status           = Column(String(50), default="processing", server_default="processing")

    rejection_email_sent = Column(Boolean, default=False, server_default="false")
    rejected_at          = Column(DateTime(timezone=True), nullable=True)

    applications = relationship("Application", back_populates="candidate")
    current_stage = relationship("JobStage")
    feedback      = relationship("InterviewFeedback", back_populates="candidate")


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

    # LLM scoring results
    ai_score         = Column(Float)             # 0-100
    ai_reasoning     = Column(Text)
    ai_strengths     = Column(JSON)              # list[str]
    ai_gaps          = Column(JSON)              # list[str]
    is_shortlisted   = Column(Boolean, default=False)
    hr_selected      = Column(Boolean)           # None = pending, True/False = HR decision

    # Interview scheduling
    interview_slot       = Column(DateTime(timezone=True))
    calendar_event_id    = Column(String(255))
    meeting_link         = Column(String(500))   # Google Meet URL
    interviewer_email    = Column(String(255))   # who conducts the interview
    assigned_user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # RBAC: interviewer assigned
    invite_sent          = Column(Boolean, default=False)

    # Final decision
    offer_sent       = Column(Boolean, default=False)
    rejected         = Column(Boolean, default=False)
    rejection_sent   = Column(Boolean, default=False)

    # Relations
    job       = relationship("Job", back_populates="applications")
    candidate = relationship("Candidate", back_populates="applications")

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
