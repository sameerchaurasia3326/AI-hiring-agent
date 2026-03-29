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
from sqlalchemy import update

from src.db.database import AsyncSessionLocal
from src.db.models import Job
from src.state.schema import HiringState, PipelineStatus
from src.tools.llm_factory import get_llm
from src.tools.hiring_tools import send_hr_notification_tool

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
- STRICT LIMIT: The entire Job Description MUST NOT exceed 2800 characters, otherwise it will fail to post to LinkedIn. Keep it concise.
- No gender-biased or exclusionary language
- Be specific about the tech stack and tools
- Include the salary range if provided"""

_HUMAN = """
Job Title: {job_title}
Department: {department}
Location: {location}
Employment Type: {employment_type}
Experience Required: {experience_required}
Salary Range: {salary_range}
Required Skills: {required_skills}
Preferred Skills: {preferred_skills}
Joining Requirement: {joining_requirement}
{feedback_block}
Write the complete Job Description.
"""

_FEEDBACK_BLOCK = """
⚠️ REVISION #{count} — HR Feedback to address:
{feedback}
"""


async def generate_jd(state: HiringState) -> dict:
    """Generate JD draft using LLM node."""
    logger.info("⚡ [generate_jd] Node triggered! Initializing AI drafting process...")
    revision = state.get("jd_revision_count", 0)
    feedback = state.get("hr_feedback", "")

    feedback_block = (
        _FEEDBACK_BLOCK.format(count=revision, feedback=feedback)
        if revision > 0 and feedback else ""
    )

    logger.info("🖊  [generate_jd] revision #{}", revision)
    logger.debug("📌 [generate_jd] Received state: {}", {k: v for k, v in state.items() if k != "jd_draft"})

    chain = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | get_llm(temperature=0.5)

    response = chain.invoke({
        "job_title":           state.get("job_title", ""),
        "department":          state.get("department", ""),
        "location":            state.get("location", ""),
        "employment_type":     state.get("employment_type", ""),
        "experience_required": state.get("experience_required", ""),
        "salary_range":        state.get("salary_range", "Competitive"),
        "required_skills":     ", ".join(state.get("required_skills", [])),
        "preferred_skills":    ", ".join(state.get("preferred_skills", [])),
        "joining_requirement": state.get("joining_requirement", ""),
        "feedback_block":      feedback_block,
    })

    # ── Database Sync: Save JD draft to Postgres immediately ────────────────
    job_id = state.get("job_id")
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    jd_draft=response.content,
                    pipeline_state=PipelineStatus.JD_APPROVAL_PENDING.value,
                    jd_revision_count=revision
                )
            )
            await session.commit()
            logger.info("💾 [generate_jd] Persisted JD draft to database for job_id={}", job_id)
        except Exception as e:
            logger.error("❌ [generate_jd] Database sync failed: {}", e)

    # ── Notification: Send JD to HR for review ────────────────────────────────
    logger.info("📧 Sending JD review notification to HR...")
    send_hr_notification_tool.invoke({
        "hr_email": state.get("hiring_manager_email"),
        "subject": f"[Hiring AI] Review Required: {state.get('job_title')}",
        "html_body": f"""
        <h2>📄 Job Description Draft Ready</h2>
        <p>The AI has generated a JD for the <strong>{state.get('job_title')}</strong> role ({state.get('department')}).</p>
        <p><strong>Job ID:</strong> <code>{job_id}</code></p>
        <hr>
        <pre style="white-space: pre-wrap; font-family: sans-serif; background: #f4f4f4; padding: 10px; border-radius: 5px;">{response.content}</pre>
        <hr>
        <h3>⚡ Action Required (Human-in-the-Loop)</h3>
        <p>The recruitment pipeline is currently <strong>paused</strong> waiting for your decision.</p>
        
        <p><strong>Option 1: Quick Actions (Click to approve immediately)</strong></p>
        <div style="margin-top: 10px;">
            <a href="{settings.frontend_url}/jobs/{job_id}/approve?approved=true" 
               style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 10px;">
               ✅ Approve & Publish
            </a>
        </div>

        <p style="margin-top: 20px;"><strong>Review JD on Dashboard</strong></p>
        <p>Alternatively, visit your dashboard to review and edit the draft.</p>
        <a href="{settings.frontend_url}/dashboard" style="color: #3b82f6; font-weight: bold;">Go to Dashboard →</a>
        """
    })

    return {
        "jd_draft":        response.content,
        "jd_approved":     False,
        "pipeline_status": PipelineStatus.JD_DRAFT.value,
    }
