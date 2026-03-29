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


def review_jd(state: HiringState) -> dict:
    """Pause graph and wait for HR JD approval. Returns raw HR response in state."""
    revision = state.get("jd_revision_count", 0)
    logger.info("⏸  [review_jd] Interrupting for HR (revision #{})", revision)

    hr_response: dict = interrupt({
        "type":           "jd_review",
        "job_id":         state.get("job_id"),
        "organization_id": state.get("organization_id"),
        "jd_draft":       state.get("jd_draft", ""),
        "revision_count": revision,
        "message":        "Approve JD or provide feedback for revision.",
    })

    approved: bool = hr_response.get("approved", False)
    feedback: str  = hr_response.get("feedback", "")

    if approved:
        logger.success("✅ [review_jd] JD approved by HR")
        return {
            "jd_approved":     True,
            "hr_feedback":     "",
            "pipeline_status": PipelineStatus.JD_APPROVED.value,
        }

    # Rejected — increment revision count; pipeline.py edge decides what happens next
    new_revision = revision + 1
    logger.info("🔄 [review_jd] Revision {} requested", new_revision)
    return {
        "jd_approved":       False,
        "hr_feedback":       feedback,
        "jd_revision_count": new_revision,
        "pipeline_status":   PipelineStatus.JD_APPROVAL_PENDING.value,
    }
