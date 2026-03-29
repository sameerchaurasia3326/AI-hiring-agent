"""
src/nodes/shortlist_sender.py
──────────────────────────────
LangGraph Node: send_shortlist_to_hr
──────────────────────────────────────
Invokes send_shortlist_email_tool (LangChain @tool) + fires 2-day Celery wait.
Returns state delta only. NO routing logic.
State: SCREENING → HR_REVIEW_PENDING
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from loguru import logger
from langgraph.types import interrupt

from src.state.schema import HiringState, PipelineStatus
from src.tools.hiring_tools import send_shortlist_email_tool
from src.scheduler.tasks import wait_for_hr_selection, TWO_DAYS_SEC


async def send_shortlist_to_hr(state: HiringState) -> dict:
    """Send ranked shortlist to HR via tool and start the 2-day timer."""
    shortlist = state.get("shortlist", [])
    job_id    = state.get("job_id", "")
    thread_id = state.get("graph_thread_id", "")
    hr_email  = state.get("hiring_manager_email", "")

    # ── [NEW] Persist candidates to DB before sending ────────────────────────
    if shortlist:
        await _persist_shortlist_to_db(
            job_id, 
            shortlist, 
            state.get("organization_id"),
            state.get("applications", [])
        )

    # ── Invoke LangChain tool ─────────────────────────────────────────────────
    send_shortlist_email_tool.invoke({
        "hr_email":       hr_email,
        "job_title":      state.get("job_title", ""),
        "job_id":         job_id,
        "candidates_json": json.dumps([
            {"name": c["name"], "email": c["email"], "score": c["score"], "candidate_id": c["candidate_id"]}
            for c in shortlist
        ]),
    })

    # ── Fire Celery wait (short for testing, was TWO_DAYS_SEC in production) ────────
    SELECTION_WAIT_SEC = 3600  # Give user 1 hour to click the email link instead of 60 seconds
    wait_for_hr_selection.apply_async(args=[job_id, thread_id], countdown=SELECTION_WAIT_SEC)
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=SELECTION_WAIT_SEC)).isoformat()

    logger.success("📧 [shortlist_sender] Sent {} candidates to HR. 60-second timer started.", len(shortlist))
    
    # ── Wait State Logic ──────────────────────────────────────────────────────
    # Interrupt immediately after sending. The graph pauses here until:
    # 1. HR calls the decision API (Decision 3)
    # 2. Celery 2-day timer resumes with scheduler_event
    interrupt_response = interrupt({
        "type": "hr_review_pending",
        "job_id": state.get("job_id"),
        "organization_id": state.get("organization_id")
    })

    return {
        "shortlist_sent_to_hr":  True,
        "hr_selection_deadline": deadline,
        "hr_selected_candidates": interrupt_response.get("selected_ids") if isinstance(interrupt_response, dict) else [],
        "scheduler_event":       interrupt_response if isinstance(interrupt_response, str) else None,
        "pipeline_status":       PipelineStatus.HR_REVIEW_PENDING.value,
    }


async def _persist_shortlist_to_db(job_id: str, shortlist: list, org_id: str, applications: list):
    """Save shortlisted candidates and their applications to Postgres."""
    from sqlalchemy import select
    from src.db.database import AsyncSessionLocal
    from src.db.models import Candidate, Application
    import uuid

    async with AsyncSessionLocal() as session:
        try:
            # Helper to find resume_path from applications list by candidate_id
            resume_lookup = {a["candidate_id"]: a["resume_path"] for a in applications}
            
            for c in shortlist:
                # 1. Ensure Candidate exists
                stmt = select(Candidate).where(Candidate.email == c["email"])
                res = await session.execute(stmt)
                candidate = res.scalar_one_or_none()

                if not candidate:
                    candidate = Candidate(
                        id=uuid.UUID(c["candidate_id"]),
                        name=c["name"],
                        email=c["email"],
                        organization_id=uuid.UUID(org_id) if org_id else None,
                        status="screening"
                    )
                    session.add(candidate)
                    await session.flush() # Get ID if not provided (though we provide it)
                
                # 2. Ensure Application exists
                stmt = select(Application).where(
                    Application.job_id == uuid.UUID(job_id),
                    Application.candidate_id == candidate.id
                )
                res = await session.execute(stmt)
                app = res.scalar_one_or_none()

                if not app:
                    app = Application(
                        job_id=uuid.UUID(job_id),
                        candidate_id=candidate.id,
                        resume_path=resume_lookup.get(c["candidate_id"], ""),
                        screening_score=c["score"],
                        status="screening"
                    )
                    session.add(app)
            
            await session.commit()
            logger.info("💾 [shortlist_sender] Persisted {} candidates to DB", len(shortlist))
        except Exception as e:
            await session.rollback()
            logger.error("❌ [shortlist_sender] DB Persistence failed: {}", e)
