"""
src/state/schema.py
────────────────────
LangGraph HiringState TypedDict — the single state object
that flows through every node in the pipeline.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional
from typing_extensions import TypedDict


# ─────────────────────────────────────────────────────────────
# Pipeline States (mirrors DB PipelineState enum)
# ─────────────────────────────────────────────────────────────
class PipelineStatus(str, Enum):
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
# Sub-record types (plain dicts — LangGraph serialise-friendly)
# ─────────────────────────────────────────────────────────────
class ApplicationRecord(TypedDict):
    candidate_id: str
    name: str
    email: str
    resume_path: str
    applied_at: str          # ISO 8601

class ScoredResume(TypedDict):
    candidate_id: str
    name: str
    email: str
    score: float             # 0–100
    reasoning: str
    strengths: List[str]
    gaps: List[str]

class ShortlistedCandidate(TypedDict):
    candidate_id: str
    name: str
    email: str
    score: float
    interview_slot: Optional[str]      # ISO 8601 once booked
    calendar_event_id: Optional[str]
    offer_sent: bool
    rejected: bool


# ─────────────────────────────────────────────────────────────
# Main State
# ─────────────────────────────────────────────────────────────
class HiringState(TypedDict, total=False):
    """
    Central state dict passed between all LangGraph nodes.
    Keys are optional (total=False) — nodes only set what they produce.
    """
    # ── Job identity ──────────────────────────────────────────
    job_id: str              # DB UUID (str form)
    graph_thread_id: str     # LangGraph thread identifier
    job_title: str
    department: str
    hiring_manager_name: str
    hiring_manager_email: str
    job_requirements: str
    salary_range: str

    # ── JD Approval Loop (Loop #1) ────────────────────────────
    jd_draft: str
    jd_revision_count: int
    jd_approved: bool
    hr_feedback: str
    published_jd_url: str

    # ── Application Loop (Loop #2) ────────────────────────────
    repost_attempts: int
    applications: List[ApplicationRecord]
    applications_deadline: str    # ISO 8601 date after which we check

    # ── Screening ─────────────────────────────────────────────
    scored_resumes: List[ScoredResume]
    shortlist: List[ShortlistedCandidate]
    shortlist_sent_to_hr: bool

    # ── HR Selection ──────────────────────────────────────────
    hr_selected_candidates: List[str]   # list of candidate_ids HR approved
    hr_selection_deadline: str          # ISO 8601

    # ── Interview scheduling ──────────────────────────────────
    interview_slots: List[dict]         # {start, end, booked, candidate_id}
    notifications_sent: bool

    # ── Pipeline metadata ─────────────────────────────────────
    pipeline_status: str                # PipelineStatus value
    error_log: List[str]
