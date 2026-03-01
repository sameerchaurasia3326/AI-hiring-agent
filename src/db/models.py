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
    ForeignKey, Integer, String, Text, JSON,
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
# Job Model
# ─────────────────────────────────────────────────────────────
class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # HR-submitted fields
    title                = Column(String(255), nullable=False)
    department           = Column(String(255))
    hiring_manager_name  = Column(String(255))
    hiring_manager_email = Column(String(255))
    requirements         = Column(Text)          # raw hiring requirements text
    salary_range         = Column(String(100))

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

    # Timestamps
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    posted_at      = Column(DateTime(timezone=True))
    closed_at      = Column(DateTime(timezone=True))

    # Relations
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────
# Candidate Model
# ─────────────────────────────────────────────────────────────
class Candidate(Base):
    __tablename__ = "candidates"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String(255), nullable=False)
    email       = Column(String(255), nullable=False, unique=True, index=True)
    phone       = Column(String(50))
    linkedin_url = Column(String(500))

    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    applications = relationship("Application", back_populates="candidate")


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
    invite_sent          = Column(Boolean, default=False)

    # Final decision
    offer_sent       = Column(Boolean, default=False)
    rejected         = Column(Boolean, default=False)
    rejection_sent   = Column(Boolean, default=False)

    # Relations
    job       = relationship("Job", back_populates="applications")
    candidate = relationship("Candidate", back_populates="applications")
