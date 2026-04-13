"""
src/nodes/notifier.py
──────────────────────
LangGraph Node: notify_candidates
──────────────────────────────────
Production Hardened:
1. Outbox pattern (Phase 2).
2. Atomic Lease Guard (Phase 1).
3. Email Validation (Phase 12).
4. Idempotent Write (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone

from src.state.schema import HiringState
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, Job
from src.state.validator import validate_node
from src.utils.production_safety import lease_guard, StructuredLogger, log_event
from sqlalchemy import select, update as sqlalchemy_update

async def _get_target_version(session, job_id, force_resend):
    """Helper to fetch and determine the next version for an email event."""
    stmt = select(Job).where(Job.id == job_id)
    res = await session.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        return 1, 1
    current_ver = job.last_email_version or 1
    target_ver = current_ver + 1 if force_resend else current_ver
    return current_ver, target_ver

def is_valid_email(email: str) -> bool:
    """Phase 12: Pre-dispatch email validation."""
    return isinstance(email, str) and "@" in email and "." in email

@validate_node
@lease_guard
async def notify_candidates(state: HiringState) -> dict:
    """
    Decouples candidate notifications via the Outbox pattern.
    Idempotent: Uses ON CONFLICT DO NOTHING to prevent duplicate acks.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    candidates = state.get("applications", [])
    if not candidates:
        return state

    s_logger.info("NOTIFYING_CANDIDATES", {"count": len(candidates)})

        force_resend = state.get("force_resend", False)
        async with AsyncSessionLocal() as session:
            current_ver, target_ver = await _get_target_version(session, job_id, force_resend)
            
            for cand in candidates:
                email = cand.get("email")
                if not email or not is_valid_email(str(email)):
                    s_logger.warning("INVALID_CANDIDATE_EMAIL", {"candidate": cand.get("name")})
                    continue

                # Phase 2 & 15: Atomic Idempotent Versioned Outbox Deposit
                cand_id = cand.get("candidate_id") or cand.get("id")
                msg_type = f"CANDIDATE_ACK_{cand_id}"
                
                stmt = (
                    insert(Outbox)
                    .values(
                        job_id=job_id,
                        type=msg_type,
                        version=target_ver,
                        payload={
                            "email": str(email),
                            "name": cand.get("name"),
                            "job_title": state.get("job_title", "Job"),
                            "trace_id": trace_id,
                            "version": target_ver
                        },
                        status="PENDING",
                        created_at=datetime.now(timezone.utc)
                    )
                    .on_conflict_do_nothing(index_elements=["job_id", "type", "version"])
                )
                await session.execute(stmt)
            
            # Atomic Version Update on Job record
            if target_ver > current_ver:
                await session.execute(
                    sqlalchemy_update(Job)
                    .where(Job.id == job_id)
                    .values(last_email_version=target_ver)
                )
            await session.commit()
            
        s_logger.success("CANDIDATE_NOTIFICATIONS_QUEUED", {"version": target_ver})
        await log_event(job_id, "CANDIDATE_NOTIFICATIONS_STARTED", {"count": len(candidates), "version": target_ver})

    except Exception as e:
        s_logger.error("NOTIFIER_OUTBOX_WRITE_FAILED", str(e))
        await log_event(job_id, "NOTIFIER_FAILED", {"error": str(e)})

    return state


@validate_node
@lease_guard
async def send_final_decision(state: HiringState) -> dict:
    """
    Phase 15: Final Decision Notifier.
    Queues offer/rejection emails in the Outbox based on the HR selection.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    selected_ids = state.get("hr_selected_candidates", [])
    all_candidates = state.get("applications", [])

    s_logger.info("PROCESSING_FINAL_DECISIONS", {"selected_count": len(selected_ids)})

        force_resend = state.get("force_resend", False)
        async with AsyncSessionLocal() as session:
            current_ver, target_ver = await _get_target_version(session, job_id, force_resend)

            for cand in all_candidates:
                cand_id = str(cand.get("id"))
                email = cand.get("email")
                
                if not email or not is_valid_email(str(email)):
                    continue

                # Decision 4: Route based on HR selection
                base_type = "OFFER_LETTER" if cand_id in selected_ids else "REJECTION_EMAIL"
                msg_type = f"{base_type}_{cand_id}"
                
                stmt = (
                    insert(Outbox)
                    .values(
                        job_id=job_id,
                        type=msg_type,
                        version=target_ver,
                        payload={
                            "email": str(email),
                            "name": cand.get("name"),
                            "job_title": state.get("job_title", "Job"),
                            "trace_id": trace_id,
                            "version": target_ver
                        },
                        status="PENDING",
                        created_at=datetime.now(timezone.utc)
                    )
                    .on_conflict_do_nothing(index_elements=["job_id", "type", "version"])
                )
                await session.execute(stmt)
            
            # Atomic Version Update on Job record
            if target_ver > current_ver:
                await session.execute(
                    sqlalchemy_update(Job)
                    .where(Job.id == job_id)
                    .values(last_email_version=target_ver)
                )

            await session.commit()
            s_logger.success("FINAL_DECISIONS_QUEUED", {"version": target_ver})
            await log_event(job_id, "FINAL_DECISION_STEP_COMPLETE", {"offer_count": len(selected_ids), "version": target_ver})

    except Exception as e:
        s_logger.error("FINAL_DECISION_OUTBOX_FAILED", str(e))
        
    return state


@validate_node
@lease_guard
async def notify_jd_draft(state: HiringState) -> dict:
    """
    Phase 15: JD Approval Request Notifier.
    Queues an approval email in the Outbox for the Hiring Manager.
    Uses ON CONFLICT DO NOTHING for idempotency (one email per job).
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    s_logger.info("NOTIFYING_JD_DRAFT")

    try:
        force_resend = state.get("force_resend", False)
        async with AsyncSessionLocal() as session:
            current_ver, target_ver = await _get_target_version(session, job_id, force_resend)

            # 1. Fetch Hiring Manager Details (already included in job fetch in _get_target_version potentially, 
            # but let's re-query for safety or use the one from helper if we modify it)
            # Re-fetching to ensure all HM fields are present
            stmt = select(Job).where(Job.id == job_id)
            res = await session.execute(stmt)
            job = res.scalar_one_or_none()
            
            if not job or not job.hiring_manager_email:
                s_logger.warning("MISSING_HR_CONTACT", {"job_id": job_id})
                return state

            # 2. Queue Email in Outbox
            outbox_stmt = (
                insert(Outbox)
                .values(
                    job_id=job_id,
                    type="JD_APPROVAL_REQUEST",
                    version=target_ver,
                    payload={
                        "email": job.hiring_manager_email,
                        "name": job.hiring_manager_name or "Hiring Manager",
                        "job_title": job.title,
                        "department": job.department or "General",
                        "full_jd": job.full_jd or job.jd_draft or "No JD content available.",
                        "trace_id": trace_id,
                        "version": target_ver
                    },
                    status="PENDING",
                    created_at=datetime.now(timezone.utc)
                )
                .on_conflict_do_nothing(index_elements=["job_id", "type", "version"])
            )
            await session.execute(outbox_stmt)

            # Atomic Version Update
            if target_ver > current_ver:
                await session.execute(
                    sqlalchemy_update(Job)
                    .where(Job.id == job_id)
                    .values(last_email_version=target_ver)
                )

            await session.commit()
            
            s_logger.success("JD_APPROVAL_NOTIFICATION_QUEUED", {"version": target_ver})
            await log_event(job_id, "JD_NOTIFICATION_QUEUED", {"to": job.hiring_manager_email, "version": target_ver})

    except Exception as e:
        s_logger.error("NOTIFY_JD_DRAFT_FAILED", str(e))
        
    return state
