"""
src/nodes/shortlist_sender.py
──────────────────────────────
LangGraph Node: send_shortlist_to_hr
──────────────────────────────────────
Production Hardened (Outbox Pattern):
1. Atomic Lease Guard (Phase 1).
2. Structured Tracking (Phase 8 & 14).
3. Outbox decoupled dispatch (Phase 2).
4. Idempotent Write (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import re
import uuid as _uuid
from loguru import logger
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone

from src.state.schema import HiringState, PipelineStatus
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Outbox
from src.state.validator import validate_node
from src.utils.production_safety import lease_guard, StructuredLogger, log_event


def is_valid_email(email: str) -> bool:
    """Phase 12: Pre-dispatch email validation."""
    return isinstance(email, str) and "@" in email and "." in email


@validate_node
@lease_guard
async def send_shortlist_to_hr(state: HiringState) -> dict:
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    shortlisted = state.get("shortlist", [])
    if len(shortlisted) == 0:
        s_logger.info("SHORTLIST_EMPTY", {"reason": "skipping_notification"})
        return {"shortlist_sent_to_hr": True}

    # [NEW] Senior Engineer Fix: Preemptive DB Audit for idempotency
    # --- Version-Aware Idempotency Audit (Senior Engineer Fix) ---
    force_resend = state.get("force_resend", False)
    
    from sqlalchemy import select, update as sqlalchemy_update
    async with AsyncSessionLocal() as session:
        # 1. Fetch current job versioning state
        job_check = await session.execute(select(Job).where(Job.id == job_id))
        job = job_check.scalar_one_or_none()
        
        if not job:
            s_logger.error("JOB_NOT_FOUND")
            return state

        current_ver = job.last_email_version or 1
        target_version = current_ver + 1 if force_resend else current_ver

        # 2. Check if this specific version already exists in Outbox
        outbox_check = await session.execute(
            select(Outbox).where(
                Outbox.job_id == job_id,
                Outbox.type == "SEND_SHORTLIST",
                Outbox.version == target_version
            )
        )
        existing_outbox = outbox_check.scalar_one_or_none()
        
        if existing_outbox:
            s_logger.info("IDEMPOTENCY_SKIP", {
                "reason": "version_exists", 
                "version": target_version,
                "status": existing_outbox.status
            })
            return {
                "shortlist_sent_to_hr": True,
                "pipeline_status": PipelineStatus.HR_REVIEW_PENDING.value,
                "current_stage": "hr_selection"
            }

        # 3. Check if Job has already advanced past this stage (Safety guard)
        if not force_resend and job.pipeline_state in [PipelineStatus.HR_REVIEW_PENDING.value, "hr_selection"]:
             s_logger.info("IDEMPOTENCY_SKIP", {"reason": "job_status_advanced"})
             return {
                "shortlist_sent_to_hr": True,
                "pipeline_status": PipelineStatus.HR_REVIEW_PENDING.value,
                "current_stage": "hr_selection"
            }


    # Admin email discovery with Database Fallback (Senior Engineer Fix)
    admin_email = state.get("admin_email") or state.get("hiring_manager_email")
    if isinstance(admin_email, dict):
        admin_email = admin_email.get("email")

    if not admin_email:
        # Fallback: Query the Job's hiring manager directly from DB record (Senior Engineer Fix)
        if job and job.hiring_manager_email:
            admin_email = job.hiring_manager_email
        
        if not admin_email:
            # Deep Fallback: Query the organization owner if needed
            async with AsyncSessionLocal() as session:
                from src.db.models import User
                if job and job.hiring_manager_id:
                    hm_check = await session.execute(select(User).where(User.id == job.hiring_manager_id))
                    hm = hm_check.scalar_one_or_none()
                    if hm and hm.email:
                        admin_email = hm.email

    # Phase 12: Validate BEFORE outbox write
    if not admin_email or not is_valid_email(str(admin_email)):
        s_logger.error("INVALID_ADMIN_EMAIL", f"Invalid target: {admin_email}. Defaulting to system admin.")
        # Final safety net: Use the master settings admin if available
        admin_email = getattr(settings, "admin_email", None)
        if not admin_email or not is_valid_email(str(admin_email)):
            await log_event(job_id, "SHORTLIST_NOTIFICATION_SKIPPED", {"reason": "no_valid_recipient"})
            return {"shortlist_sent_to_hr": True}

    # ── Phase 2 & 15: Idempotent Outbox Pattern Dispatch ──
    try:
        async with AsyncSessionLocal() as session:
            # ── Phase 2 & 15: Idempotent Versioned Outbox Deposit ──
            # We use target_version prepared in Step 1
            stmt = (
                insert(Outbox)
                .values(
                    job_id=job_id,
                    type="SEND_SHORTLIST",
                    version=target_version,
                    payload={
                        "admin_email": str(admin_email),
                        "job_title": state.get("job_title", "Job"),
                        "shortlisted_candidates": shortlisted,
                        "trace_id": trace_id,
                        "version": target_version
                    },
                    status="PENDING",
                    created_at=datetime.now(timezone.utc)
                )
                .on_conflict_do_nothing(index_elements=["job_id", "type", "version"])
            )
            await session.execute(stmt)

            # Atomic Version Update on Job record
            if target_version > current_ver:
                await session.execute(
                    sqlalchemy_update(Job)
                    .where(Job.id == job_id)
                    .values(last_email_version=target_version)
                )
            
            # Atomic DB State Update
            await session.execute(
                update(Job)
                .where(Job.id == _uuid.UUID(str(job_id)))
                .values(
                    pipeline_state=PipelineStatus.HR_REVIEW_PENDING.value,
                    status_field="ACTION_REQUIRED",
                    current_stage="hr_selection"
                )
            )
            await session.commit()
            
        s_logger.success("SHORTLIST_QUEUED_IN_OUTBOX", {"target": admin_email})
        await log_event(job_id, "SHORTLIST_SENT")

    except Exception as e:
        s_logger.error("OUTBOX_WRITE_FAILED", str(e))
        await log_event(job_id, "SHORTLIST_NOTIFICATION_FAILED", {"error": str(e)})

    return {
        "shortlist_sent_to_hr": True,
        "pipeline_status": PipelineStatus.HR_REVIEW_PENDING.value,
        "current_stage":   "hr_selection"
    }
