"""
src/api/main.py
────────────────
FastAPI application — the external interface for HR interactions.

Endpoints:
  POST /jobs                        — HR submits new hiring request → starts LangGraph pipeline
  POST /jobs/{job_id}/approve-jd    — HR approves/rejects JD → resumes graph (Decision 1)
  POST /jobs/{job_id}/select-candidates — HR selects candidates → resumes graph (Decision 3)
  POST /jobs/{job_id}/final-decision    — HR sends post-interview decision (Decision 4)
  GET  /jobs/{job_id}/status        — Query current pipeline state
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from loguru import logger

from src.graph.pipeline import get_pipeline
from src.state.schema import HiringState

app = FastAPI(
    title="Hiring AI — Automation System",
    description="AI-driven hiring pipeline powered by LangGraph + LangChain",
    version="1.0.0",
)


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class NewJobRequest(BaseModel):
    job_title:              str
    department:             str
    hiring_manager_name:    str
    hiring_manager_email:   str
    job_requirements:       str
    salary_range:           Optional[str] = "Competitive"

class JDApprovalRequest(BaseModel):
    approved:  bool
    feedback:  Optional[str] = ""

class CandidateSelectionRequest(BaseModel):
    candidate_ids: List[str]

class FinalDecisionRequest(BaseModel):
    selected_ids: List[str]   # empty list = all rejected

class JobStatusResponse(BaseModel):
    job_id:          str
    pipeline_status: str
    jd_revision_count: int
    repost_attempts:   int
    applications_count: int
    shortlist_count:   int


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/jobs", summary="Submit new hiring request")
async def create_job(req: NewJobRequest):
    """
    HR submits a hiring request.
    Creates a new LangGraph thread and starts the pipeline.
    Returns job_id and thread_id for future interactions.
    """
    job_id    = str(uuid.uuid4())
    thread_id = f"job-{job_id}"

    initial_state: HiringState = {
        "job_id":                job_id,
        "graph_thread_id":       thread_id,
        "job_title":             req.job_title,
        "department":            req.department,
        "hiring_manager_name":   req.hiring_manager_name,
        "hiring_manager_email":  req.hiring_manager_email,
        "job_requirements":      req.job_requirements,
        "salary_range":          req.salary_range or "Competitive",
        "jd_revision_count":     0,
        "repost_attempts":       0,
        "applications":          [],
        "scored_resumes":        [],
        "shortlist":             [],
        "error_log":             [],
    }

    pipeline = get_pipeline()
    config   = {"configurable": {"thread_id": thread_id}}

    logger.info("🚀 Starting pipeline for job_id={}", job_id)

    # Invoke pipeline — it will run until the first interrupt (review_jd)
    await pipeline.ainvoke(initial_state, config=config)

    return {
        "job_id":    job_id,
        "thread_id": thread_id,
        "message":   "Pipeline started. JD is being generated and will be sent for HR review.",
    }


@app.post("/jobs/{job_id}/approve-jd", summary="HR approves or rejects the generated JD (Decision 1)")
async def approve_jd(job_id: str, req: JDApprovalRequest):
    """
    Resumes the LangGraph pipeline paused at the review_jd interrupt.
    - approved=True  → pipeline proceeds to publish_jd
    - approved=False → pipeline loops back to generate_jd with feedback
    """
    thread_id = f"job-{job_id}"
    pipeline  = get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    resume_value = {"approved": req.approved, "feedback": req.feedback or ""}

    logger.info("📬 [approve_jd] job_id={} approved={}", job_id, req.approved)

    await pipeline.ainvoke(
        None,                     # None = resume from interrupt
        config=config,
        interrupt_value=resume_value,  # value returned by interrupt() in review_jd
    )

    return {
        "job_id":  job_id,
        "approved": req.approved,
        "message": "JD approved — pipeline proceeding to publish." if req.approved
                   else "JD revision requested — AI will regenerate.",
    }


@app.post("/jobs/{job_id}/select-candidates", summary="HR selects candidates for interview (Decision 3)")
async def select_candidates(job_id: str, req: CandidateSelectionRequest):
    """
    Resumes the LangGraph pipeline after the 2-day shortlist review window.
    Selected candidate_ids proceed to interview scheduling.
    Empty list → pipeline closes.
    """
    thread_id = f"job-{job_id}"
    pipeline  = get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [select_candidates] job_id={} selected={}", job_id, req.candidate_ids)

    # Store selection in graph state so route_after_hr_selection can read it
    await pipeline.ainvoke(
        {"hr_selected_candidates": req.candidate_ids},
        config=config,
    )

    return {
        "job_id":          job_id,
        "selected_count":  len(req.candidate_ids),
        "message":         "Candidates selected. Interview scheduling in progress." if req.candidate_ids
                           else "No candidates selected. Pipeline closing.",
    }


@app.post("/jobs/{job_id}/final-decision", summary="HR submits post-interview final decisions (Decision 4)")
async def final_decision(job_id: str, req: FinalDecisionRequest):
    """
    Resumes the LangGraph pipeline paused at the send_final_decision interrupt.
    - selected_ids non-empty → offer letters sent
    - selected_ids empty     → all rejections sent
    """
    thread_id = f"job-{job_id}"
    pipeline  = get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [final_decision] job_id={} offers={}", job_id, req.selected_ids)

    await pipeline.ainvoke(
        None,
        config=config,
        interrupt_value={"selected_ids": req.selected_ids},
    )

    return {
        "job_id":      job_id,
        "offers_sent": len(req.selected_ids),
        "message":     "Final decisions processed. Pipeline complete.",
    }


@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse, summary="Get pipeline status")
async def get_status(job_id: str):
    """Return the current pipeline state for a job."""
    thread_id = f"job-{job_id}"
    pipeline  = get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    state = await pipeline.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found")

    s = state.values
    return JobStatusResponse(
        job_id=job_id,
        pipeline_status=s.get("pipeline_status", "unknown"),
        jd_revision_count=s.get("jd_revision_count", 0),
        repost_attempts=s.get("repost_attempts", 0),
        applications_count=len(s.get("applications", [])),
        shortlist_count=len(s.get("shortlist", [])),
    )


@app.get("/health")
def health():
    return {"status": "ok"}
