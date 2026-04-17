"""
src/state/schema.py
────────────────────
LangGraph HiringState TypedDict — the single state object
that flows through every node in the pipeline.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Annotated
import operator
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
    meeting_link: Optional[str]        # Google Meet URL
    interviewer_email: Optional[str]   # who conducts the interview
    offer_sent: bool
    rejected: bool

class ScoringBlueprint(TypedDict):
    required_skills: List[str]
    optional_skills: List[str]
    tools: List[str]
    domain_keywords: List[str]
    experience_level: float


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
    organization_id: str     # Multi-tenant isolation rule
    graph_thread_id: str     # LangGraph thread identifier
    job_title: str
    template_type: str       # Configured JD design template variant 
    department: str
    hiring_manager_name: str
    hiring_manager_email: str
    interviewer_email: str   # person conducting the interview (defaults to hiring_manager_email)
    location: str
    experience_required: str
    employment_type: str
    joining_requirement: str
    required_skills: List[str]
    preferred_skills: List[str]
    screening_questions: List[dict]
    technical_test_type: str
    technical_test_link: str
    technical_test_mcq: List[dict]
    hiring_workflow: List[str]
    scoring_weights: dict
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
    interview_slots: Annotated[List[dict], operator.add]         # {start, end, booked, candidate_id}
    meeting_links: Annotated[List[dict], operator.add]           # {candidate_id, meet_link, event_id}
    notifications_sent: bool

    # ── Pipeline metadata ─────────────────────────────────────
    pipeline_status: str                # PipelineStatus value
    current_stage: str                  # Current node ID for validation
    action_type: str                    # Actual action taken (jd_approve, jd_reject, etc.)
    trace_id: str                       # UUID for distributed logging (Phase 8)
    pipeline_version: str               # Version identifier (Phase 13)
    error_log: Annotated[List[str], operator.add]
    force_resend: bool
    normalized_role: str        # Standardised role token (e.g. 'security_engineer')
    scoring_blueprint: ScoringBlueprint # Dynamic evaluation criteria
