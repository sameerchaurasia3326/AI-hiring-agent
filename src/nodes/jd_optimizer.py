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
from src.tools.llm_factory import get_llm

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


def optimize_jd(state: HiringState) -> dict:
    """Rewrite the JD to improve application rate."""
    attempt = state.get("repost_attempts", 0) + 1
    logger.info("🔧 [optimize_jd] Attempt {}/{}", attempt, "max")

    chain = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | get_llm(temperature=0.6)

    response = chain.invoke({
        "jd_draft":     state.get("jd_draft", ""),
        "job_title":    state.get("job_title", ""),
        "attempt":      attempt,
        "max_attempts": "3",
    })

    return {
        "jd_draft":          response.content,
        "jd_approved":       False,
        "hr_feedback":       "",
        "jd_revision_count": 0,       # reset revision counter for new draft
        "repost_attempts":   attempt,
        "pipeline_status":   PipelineStatus.JD_DRAFT.value,
    }
