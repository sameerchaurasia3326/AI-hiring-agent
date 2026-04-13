"""
src/nodes/jd_optimizer.py
──────────────────────────
LangGraph Node: optimize_jd
────────────────────────────
LLM rewrites the JD with better keywords when no applications arrived.
Increments repost_attempts. NO routing logic here — graph conditional
edge (route_after_application_check) decides next node.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.state.validator import validate_node
from src.tools.llm_factory import get_llm
from src.utils.production_safety import lease_guard, StructuredLogger, log_event

_SYSTEM = """You are a hiring optimization expert. A job posting received ZERO applications.
Rewrite it significantly to attract more candidates.
Focus on: better keywords for search, clearer role description, reduced unnecessary requirements,
more competitive salary/benefit language, stronger culture signals.
Return the FULL improved Job Description."""

_HUMAN = """
Current JD (received 0 applications after 7 days):
{jd_draft}

Job Title: {job_title}
Repost Attempt: {attempt}/{max_attempts}

Write the complete optimized Job Description now.
"""


async def optimize_jd(state: HiringState) -> dict:
    """Rewrite JD to attract more candidates after a failed 7-day wait."""
    if not state.get("job_id"):
        raise Exception("CRITICAL: Missing job_id in optimize_jd")

    logger.info("STAGE: optimize_jd")
    logger.info("ACTION: {}", state.get("action_type"))
    logger.info("JOB_ID: {}", state.get("job_id"))

    attempt = state.get("repost_attempts", 0) + 1
    logger.info("🔧 [optimize_jd] Attempt {}/{}", attempt, "max")

    chain = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | get_llm(temperature=0.6)

    # [NEW] Explicit config to avoid 'get_config' outside runnable context
    response = chain.invoke({
        "jd_draft":     state.get("jd_draft", ""),
        "job_title":    state.get("job_title", ""),
        "attempt":      attempt,
        "max_attempts": "3",
    }, config={"callbacks": []})

    return {
        "jd_draft":          response.content,
        "jd_approved":       False,
        "hr_feedback":       "",
        "jd_revision_count": 0,       # reset revision counter for new draft
        "repost_attempts":   attempt,
        "pipeline_status":   PipelineStatus.JD_DRAFT.value,
        "job_id":            state.get("job_id"),
    }
