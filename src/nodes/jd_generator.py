"""
src/nodes/jd_generator.py
──────────────────────────
LangGraph Node: generate_jd
────────────────────────────
Production Hardened:
1. Atomic Lease Guard (Phase 1).
2. Jittery Retries for LLM (Phase 7).
3. Structured Observability (Phase 8 & 14).
"""
from __future__ import annotations

import json
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime, timezone

from src.state.schema import HiringState, PipelineStatus
from src.config.jd_templates import JD_TEMPLATES
from src.tools.llm_factory import get_llm
from src.utils.activity import log_activity_sync
from src.utils.production_safety import StructuredLogger, db_timeout, safe_tool_call, log_event, lease_guard, llm_semaphore
from src.utils.normalization import normalize_job_role
from src.state.validator import validate_node


@validate_node
@lease_guard
async def generate_jd(state: HiringState) -> dict:
    """
    Pure node — takes state, calls LLM, returns state delta.
    Uses Phase 7 Jittery Retries and Phase 5 Global Semaphores.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    job_title = state.get("job_title", "Software Engineer")
    requirements = state.get("raw_requirements", "Build great products.")
    
    await log_event(job_id, "JD_GENERATION_STARTED")

    from src.tools.llm_factory import get_llm
    llm = get_llm(temperature=0.7)

    system_prompt = JD_TEMPLATES.get("standard_system", "You are an expert HR recruiter.")
    user_prompt = JD_TEMPLATES.get("generation_prompt", "Generate a JD for {title} given {req}")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", user_prompt)
    ])

    # Phase 4, 5, 7 & 10: Resilience Layer
    try:
        from src.utils.resilience import with_resilience
        
        async with llm_semaphore:
            response = await with_resilience(
                "ollama",
                llm.ainvoke,
                max_retries=3,
                input=prompt.format(title=job_title, req=requirements),
                config={"callbacks": []}
            )
        jd_text = response.content


        s_logger.success("JD_GENERATION_COMPLETED")
        await log_event(job_id, "JD_GENERATION_SUCCESS")

        # ── [NEW] Phase 15 & Fix: Sync AI state to Relational DB for UI Visibility ──
        from src.db.database import AsyncSessionLocal
        from src.db.models import Job, PipelineState
        from sqlalchemy import update
        
        logger.info("JD_GENERATED_SUCCESSFULLY", extra={"job_id": job_id})
    
        # ── [NEW] Role-Awareness: Recalibrate Context after generation ──
        from src.db.database import AsyncSessionLocal
        from src.db.models import Job
        from sqlalchemy import update
        
        new_role = await normalize_job_role(job_title)
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(normalized_role=new_role, jd_draft=jd_text, pipeline_state=PipelineState.JD_APPROVAL_PENDING)
            )
            await session.commit()

        return {
            "jd_draft": jd_text,
            "job_title": job_title,
            "normalized_role": new_role,
            "pipeline_status": PipelineStatus.JD_APPROVAL_PENDING.value,
            "current_stage": "review_jd",
            "action_type": "jd_generation_complete"
        }

    except Exception as e:
        s_logger.error("JD_GENERATION_FAILED", str(e))
        await log_event(job_id, "JD_GENERATION_FAILED", {"error": str(e)})
        return {"pipeline_status": PipelineStatus.FAILED.value}
