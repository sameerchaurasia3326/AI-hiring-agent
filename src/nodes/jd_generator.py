"""
src/nodes/jd_generator.py
──────────────────────────
LangGraph Node: generate_jd
────────────────────────────
Pure node — takes state, calls LLM, returns state delta.
NO if/else routing — that lives entirely in conditional edges on the graph.
State transition: → JD_DRAFT
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.tools.llm_factory import get_llm

_SYSTEM = """You are a senior technical recruiter at a world-class technology company.
Write a professional, inclusive, and compelling Job Description that will attract the best talent.

Structure:
1. Company Overview (3-4 sentences)
2. Role Summary (3-4 sentences)
3. Key Responsibilities (6-8 bullet points)
4. Required Qualifications (5-7 bullet points)
5. Nice-to-Have Qualifications (3-5 bullet points)
6. What We Offer / Benefits
7. How to Apply

Rules:
- No gender-biased or exclusionary language
- Be specific about the tech stack and tools
- Include the salary range if provided"""

_HUMAN = """
Job Title: {job_title}
Department: {department}
Salary Range: {salary_range}
Requirements: {job_requirements}
{feedback_block}
Write the complete Job Description.
"""

_FEEDBACK_BLOCK = """
⚠️ REVISION #{count} — HR Feedback to address:
{feedback}
"""


def generate_jd(state: HiringState) -> dict:
    """Generate or revise a Job Description using the LLM."""
    revision = state.get("jd_revision_count", 0)
    feedback = state.get("hr_feedback", "")

    feedback_block = (
        _FEEDBACK_BLOCK.format(count=revision, feedback=feedback)
        if revision > 0 and feedback else ""
    )

    logger.info("🖊  [generate_jd] revision #{}", revision)

    chain = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | get_llm(temperature=0.5)

    response = chain.invoke({
        "job_title":       state.get("job_title", ""),
        "department":      state.get("department", ""),
        "salary_range":    state.get("salary_range", "Competitive"),
        "job_requirements": state.get("job_requirements", ""),
        "feedback_block":  feedback_block,
    })

    return {
        "jd_draft":        response.content,
        "jd_approved":     False,
        "pipeline_status": PipelineStatus.JD_DRAFT.value,
    }
