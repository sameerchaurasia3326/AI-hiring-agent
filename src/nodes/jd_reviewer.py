"""
src/nodes/jd_reviewer.py
─────────────────────────
LangGraph Node: review_jd
──────────────────────────
PURE interrupt node — pauses graph for HR.
Returns state delta only. ALL routing decisions (approved / rejected /
max-revisions-exceeded) happen as conditional edges in pipeline.py.

Interrupt payload sent OUT to caller:
  { type, jd_draft, revision_count }

Resume payload received IN from HR API:
  { approved: true }
  OR
  { approved: false, feedback: "..." }
"""
from __future__ import annotations

from langgraph.types import interrupt
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.db.database import AsyncSessionLocal
from src.state.validator import validate_node
from src.utils.production_safety import lease_guard, StructuredLogger, log_event

@validate_node
@lease_guard
async def review_jd(state: HiringState) -> dict:
    """
    Simulates a reviewer (AI or Human) checking the JD.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        raise Exception("CRITICAL: Missing job_id in review_jd")

    s_logger.info("JD_REVIEW_STARTED")
    await log_event(job_id, "JD_REVIEW_STARTED")

    # [NEW] Idempotency Guard: Check if already approved in DB
    # Prevents "visual reset" on dashboard during resumption
    async with AsyncSessionLocal() as session:
        from src.db.models import Job
        from sqlalchemy import select
        res = await session.execute(select(Job.jd_approved).where(Job.id == job_id))
        if res.scalar():
            logger.info(f"⏩ [review_jd] Job {job_id} already approved in DB. Skipping interrupt.")
            return {
                "jd_approved":     True,
                "hr_feedback":     "",
                "action_type":     "jd_approve",
                "pipeline_status": PipelineStatus.JOB_POSTED.value,
                "job_id":          job_id,
            }

    # ── [NEW] Node Selection Guard ──────────────────────────────────────────
    if state.get("current_stage") != "jd_review" and state.get("current_stage") is not None:
        logger.warning(f"⏩ [review_jd] Skipping: State stage '{state.get('current_stage')}' mismatch.")
        return state

    revision = state.get("jd_revision_count", 0)
    logger.info("⏸  [review_jd] Interrupting for HR (revision #{})", revision)

    # ── Phase 15: Deep Freeze (Stateless Interrupt Recovery) ──
    # Senior Engineer Fix: Capture payload and persist to DB before pausing
    interrupt_payload = {
        "type":           "jd_review",
        "job_id":         str(job_id),
        "organization_id": state.get("organization_id"),
        "jd_draft":       state.get("jd_draft", ""),
        "revision_count": revision,
        "message":        "Approve JD or provide feedback for revision.",
    }

    # [NEW] Guard for "outside runnable context"
    try:
        from src.db.models import Job
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job)
                .where(Job.id == (uuid.UUID(str(job_id)) if isinstance(job_id, str) else job_id))
                .values(
                    status_field="PAUSED",
                    interrupt_payload=interrupt_payload
                )
            )
            await session.commit()
        
        logger.info(f"❄️  [review_jd] Pipeline FROZEN for job_id={job_id}. Awaiting HR approval.")
        hr_response: dict = interrupt(interrupt_payload)
    except RuntimeError as e:
        if "outside of a runnable context" in str(e):
            logger.warning("⚠️  [review_jd] SKIPPING INTERRUPT: Running outside LangGraph (manual mode). Approving automatically for test.")
            # In manual mode, assume approval to continue pipeline
            return {
                "jd_approved":     True,
                "hr_feedback":     "",
                "action_type":     "jd_approve",
                "pipeline_status": PipelineStatus.JD_APPROVED.value,
                "job_id":          state.get("job_id"),
            }
        raise e

    # ── [NEW] Action Type Guard ──────────────────────────────────────────────
    action_type = hr_response.get("action_type")
    if action_type not in ["jd_approve", "jd_reject"]:
        logger.warning(f"⚠️  [review_jd] Ignored unrelated action: {action_type}")
        return state

    approved: bool = hr_response.get("approved", False)
    feedback: str  = hr_response.get("feedback", "")

    if approved:
        logger.success("✅ [review_jd] JD approved by HR")
        return {
            "jd_approved":     True,
            "hr_feedback":     "",
            "action_type":     "jd_approve",
            "pipeline_status": PipelineStatus.JD_APPROVED.value,
            "job_id":          state.get("job_id"),
        }

    # Rejected — increment revision count; pipeline.py edge decides what happens next
    new_revision = revision + 1
    logger.info("🔄 [review_jd] Revision {} requested", new_revision)
    return {
        "jd_approved":       False,
        "hr_feedback":       feedback,
        "jd_revision_count": new_revision,
        "action_type":       "jd_reject",
        "pipeline_status":   PipelineStatus.JD_APPROVAL_PENDING.value,
        "job_id":            state.get("job_id"),
    }
