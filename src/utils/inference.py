"""
src/utils/inference.py
────────────────────────
Stage inference from DB state.
Ensures the pipeline is stateless and recovers even if checkpoints are purged.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from loguru import logger

from src.db.database import AsyncSessionLocal
from src.db.models import Job, Application, PipelineState
from src.utils.production_safety import generate_trace_id

async def infer_stage(job_id: str | uuid.UUID) -> str:
    """
    Determine the correct LangGraph node to start/resume from using DB state.
    
    Mapping logic:
    1. No applications -> collect_applications
    2. Applications exist but not scored -> score_resumes
    3. Scored but no HR decision -> send_shortlist_to_hr
    4. HR decision made -> schedule_interviews
    5. Final decision made -> END
    """
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)

    logger.info(f"🔍 [infer_stage] Auditing DB state for job_id={job_id}")

    async with AsyncSessionLocal() as session:
        # 1. Check Applications
        app_count = await session.scalar(
            select(func.count(Application.id)).where(Application.job_id == job_id)
        )
        if app_count == 0:
            logger.info("Decision: No applications found -> collect_applications")
            return "collect_applications"

        # 2. Check Unscored
        unscored_count = await session.scalar(
            select(func.count(Application.id))
            .where(Application.job_id == job_id, Application.is_scored == False)
        )
        if unscored_count > 0:
            logger.info(f"Decision: {unscored_count} unscored apps found -> score_resumes")
            return "score_resumes"

        # 3. Check HR Selection Status
        # If scored but HR hasn't made a decision (hr_selected is None)
        pending_hr_count = await session.scalar(
            select(func.count(Application.id))
            .where(Application.job_id == job_id, Application.hr_selected == None, Application.rejected == False)
        )
        
        # Also check if shortlist email was sent (shortlist_sent_to_hr flag in job)
        job_res = await session.execute(select(Job.pipeline_state, Job.jd_approved).where(Job.id == job_id))
        job = job_res.scalar_one_or_none()
        
        if pending_hr_count > 0:
            # If we have scored candidates but HR hasn't selected any, we might need to send/resend shortlist
            logger.info(f"Decision: {pending_hr_count} candidates awaiting HR review -> send_shortlist_to_hr")
            return "send_shortlist_to_hr"

        # 4. Check Selected Candidates
        selected_count = await session.scalar(
            select(func.count(Application.id))
            .where(Application.job_id == job_id, Application.hr_selected == True)
        )
        if selected_count > 0:
            logger.info(f"Decision: {selected_count} candidates selected -> schedule_interviews")
            return "schedule_interviews"

    logger.info("Decision: Workflow appears finalized -> END")
    return "END"

async def reconstruct_state(job_id: str | uuid.UUID) -> dict:
    """
    Reconstruct the full HiringState from DB for job resumption.
    """
    if isinstance(job_id, str):
        job_id = uuid.uuid4() if not job_id else uuid.UUID(job_id)
    
    stage = await infer_stage(job_id)
    logger.info(f"♻️ Reconstructed state → {stage}")

    async with AsyncSessionLocal() as session:
        # Fetch Job Config
        job_res = await session.execute(select(Job).where(Job.id == job_id))
        job = job_res.scalar_one_or_none()
        
        # Fetch Applications joined with Candidate info
        from src.db.models import Candidate
        app_res = await session.execute(
            select(Application, Candidate.name, Candidate.email)
            .join(Candidate, Application.candidate_id == Candidate.id)
            .where(Application.job_id == job_id)
        )
        apps_data = app_res.all()
        
        applications_state = []
        scored_resumes_state = []
        
        for app, name, email in apps_data:
            app_record = {
                "candidate_id": str(app.candidate_id),
                "name":         name,
                "email":        email,
                "resume_path":  app.resume_path,
                "applied_at":   app.applied_at.isoformat() if app.applied_at else None
            }
            applications_state.append(app_record)
            
            if app.is_scored:
                scored_resumes_state.append({
                    "candidate_id": str(app.candidate_id),
                    "name":         name,
                    "email":        email,
                    "score":        app.score or 0.0,
                    "reasoning":    app.ai_reasoning or "",
                    "strengths":    app.ai_strengths or [],
                    "gaps":         app.ai_gaps or []
                })

    # ── Phase 15: Senior Engineer Recovery Visibility ──
    logger.info(f"♻️ Pipeline recovered at stage: {stage}")
    logger.info(f"📊 Applications: {len(applications_state)}")

    return {
        "job_id":               str(job_id),
        "pipeline_status":      job.pipeline_state.value if job else "JD_DRAFT",
        "current_stage":        stage,
        "hiring_manager_email": job.hiring_manager_email if job else None,
        "interviewer_email":    job.interviewer_email or job.hiring_manager_email if job else None,
        "normalized_role":      job.normalized_role if job else None,
        "location":             job.location if job else None,
        "status_field":         job.status_field if job else "PROCESSING",
        "interrupt_payload":    job.interrupt_payload if job else None,
        "jd_draft":             job.jd_draft if job else "",
        "jd_approved":          job.jd_approved if job else False,
        "applications":         applications_state,
        "scored_resumes":       scored_resumes_state,
        "trace_id":             generate_trace_id(),
        "action_type":          "state_reconstruction"
    }
