"""
src/scheduler/tasks.py
───────────────────────
Celery tasks that implement TIME-BASED WAITS in a non-blocking way.

Each task is dispatched with a countdown (seconds). When it fires,
it resumes the LangGraph pipeline for the relevant job.

Design:
  - wait_for_applications : fires after 7 days, checks if any applications arrived
  - wait_for_hr_selection  : fires after 2 days, checks if HR selected candidates
"""
from __future__ import annotations

import asyncio
from celery import shared_task
from loguru import logger
from langgraph.types import Command

from src.scheduler.celery_app import celery_app

SEVEN_DAYS_SEC = 7 * 24 * 60 * 60   # 604800
TWO_DAYS_SEC   = 2 * 24 * 60 * 60   # 172800

from src.state.schema import HiringState # Import for typing
from src.db.models import Job, Outbox, DeadLetterQueue
from src.db.database import AsyncSessionLocal
from sqlalchemy import select, update, delete, insert, text
from datetime import datetime, timezone, timedelta
from src.utils.production_safety import StructuredLogger, is_retryable_error, set_trace_id, db_timeout




from src.tools.platforms.linkedin import LinkedInClient


_worker_loop = None

def _run_async(coro, timeout=600):
    """
    Run an async coroutine from a sync Celery task with resilience guards.
    - Uses a persistent loop for stateful checkpointers.
    - Enforces a total time budget (default 10 minutes).
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    
    # Wrap coroutine with timeout
    async def _wrapped_run():
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("🚨 [Celery] Task reached absolute timeout of {}s", timeout)
            raise
        except Exception as e:
            logger.error("❌ [Celery] Task failed: {}", e)
            raise

    return _worker_loop.run_until_complete(_wrapped_run())


# ─────────────────────────────────────────────────────────────
# Task 1: Wait 7 days, then check for applications
# ─────────────────────────────────────────────────────────────
@celery_app.task(
    name="tasks.wait_for_applications",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5-min retry on failure
)
def wait_for_applications(self, job_id: str, thread_id: str, trace_id: str = None) -> dict:
    """
    Fires 7 days after a job is posted.
    Resumes the LangGraph graph to evaluate whether applications arrived.
    """
    set_trace_id(trace_id)
    logger.info("⏰ [wait_for_applications] Firing for job_id={}", job_id)

    try:
        return _run_async(_resume_graph_after_wait(job_id, thread_id, event="applications_deadline_reached"))
    except Exception as exc:
        logger.error("❌ [wait_for_applications] Error: {}", exc)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
# Task 2: Wait 2 days, then check HR selection
# ─────────────────────────────────────────────────────────────
@celery_app.task(
    name="tasks.wait_for_hr_selection",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def wait_for_hr_selection(self, job_id: str, thread_id: str, trace_id: str = None) -> dict:
    """
    Fires 2 days after shortlist is sent to HR.
    Resumes graph to check if HR responded with candidate selections.
    """
    set_trace_id(trace_id)
    logger.info("⏰ [wait_for_hr_selection] Firing for job_id={}", job_id)

    try:
        return _run_async(_resume_graph_after_wait(job_id, thread_id, event="hr_selection_deadline_reached"))
    except Exception as exc:
        logger.error("❌ [wait_for_hr_selection] Error: {}", exc)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
# Task 3: Real multi-platform publishing
# ─────────────────────────────────────────────────────────────
@celery_app.task(
    name="tasks.publish_to_platforms",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3}
)
def publish_to_platforms(self, job_id: str, job_title: str, jd_content: str, trace_id: str = None) -> dict:
    """
    Asynchronously posts to LinkedIn with automatic exponential backoff retries.
    """
    set_trace_id(trace_id)
    logger.info("📢 [publish_to_platforms] Starting async post for job_id={}", job_id)

    
    results = {}
    
    # 1. LinkedIn
    try:
        async def _run_linkedin():
            from src.db.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                li = LinkedInClient()
                return await db_timeout(li.publish_job(job_id, job_title, jd_content, session))
                
        results["linkedin"] = _run_async(_run_linkedin(), timeout=70) # 60s for job + overhead
    except Exception as e:
        err_msg = str(e)
        if "Rate limit hit" in err_msg:
            logger.warning("⏳ [Celery] Rate limit hit. Initiating 60-second countdown backoff.")
            raise self.retry(exc=e, countdown=60)
            
        # Do not retry on 4xx Client Errors (except 429 which is handled above)
        if "API failed (4" in err_msg:
            logger.error("❌ [Celery] LinkedIn encountered permanent 4xx failure. Aborting retry loop: {}", e)
            results["linkedin"] = f"PERMANENT_ERROR: {e}"
            return results

        logger.error("❌ [Celery] LinkedIn failed, triggering native retry: {}", e)
        raise e

    logger.success("🏁 [publish_to_platforms] Finished job_id={}. Results: {}", job_id, results)
    print(f"\n✅ [WORKER] LinkedIn Publishing completed for Job {job_id}. Check results above!\n")
    return results


# ─────────────────────────────────────────────────────────────
# Task 4: Background Token Refresh System
# ─────────────────────────────────────────────────────────────
@celery_app.task(name="tasks.refresh_expiring_linkedin_tokens")
def refresh_expiring_linkedin_tokens() -> dict:
    """
    Finds integrations nearing expiry (e.g., within 24 hours) and refreshes them automatically.
    """
    logger.info("⏳ [Celery Beat] Scanning for expiring LinkedIn tokens...")
    
    async def _refresh():
        from src.db.database import AsyncSessionLocal
        from src.db.models import Integration
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import select
        from src.tools.platforms.linkedin import refresh_linkedin_token
        
        results = {"refreshed": 0, "failed": 0}
        
        async with AsyncSessionLocal() as session:
            # Threshold: expiring within the next 24 hours
            threshold = datetime.now(timezone.utc) + timedelta(hours=24)
            
            stmt = select(Integration).where(
                Integration.provider == "linkedin",
                Integration.status.in_(["active", "expired"]),
                Integration.expires_at <= threshold,
                Integration.refresh_token.isnot(None)
            )
            res = await db_timeout(session.execute(stmt))
            integrations = res.scalars().all()
            
            for integration in integrations:
                try:
                    success = await refresh_linkedin_token(integration, session)
                    if success:
                        integration.status = "active"
                        results["refreshed"] += 1
                        logger.success("✅ [Beat] Refreshed token for Org {}", integration.organization_id)
                    else:
                        integration.status = "expired"
                        results["failed"] += 1
                        logger.error("❌ [Beat] Failed to refresh token for Org {}", integration.organization_id)
                except Exception as e:
                    logger.error("❌ [Beat] Exception refreshing token for Org {}: {}", integration.organization_id, e)
                    integration.status = "error"
                    results["failed"] += 1
                
                await session.commit()
                
        return results

    res = _run_async(_refresh())
    logger.info("🏁 [Celery Beat] Finished token refresh scan. Results: {}", res)
    return res


# ─────────────────────────────────────────────────────────────
# Shared: resume the LangGraph graph with a scheduler event
# ─────────────────────────────────────────────────────────────
async def _resume_graph_after_wait(job_id: str, thread_id: str, event: str) -> dict:
    """
    Resumes the autonomous pipeline using the universal DB-driven entrypoint.
    """
    from src.graph.pipeline import run_reconstructed_pipeline
    
    logger.info("⚡ [_resume_graph_after_wait] Resuming autonomy for job_id={}", job_id)
    await run_reconstructed_pipeline(job_id)

    logger.success("✅ [_resume_graph_after_wait] Graph resumed autonomously for job_id={}", job_id)
    return {"status": "resumed", "job_id": job_id, "event": event}


@celery_app.task(name="tasks.force_resume_job")
def force_resume_job(job_id: str, thread_id: str, trace_id: str = None):
    """
    Manually forces the pipeline to start for a specific job.
    Logs will appear in the Celery worker's terminal.
    """
    set_trace_id(trace_id)
    logger.info("🚀 [Celery] Force-resuming graph for job_id={}", job_id)

    async def _run():
        from src.graph.pipeline import get_pipeline
        pipeline = await get_pipeline()
        # [NEW] Explicit config to harden against context errors
        config = {"configurable": {"thread_id": thread_id}, "callbacks": []}
        
        # We use ainvoke(None) to kick the graph forward from its current state
        await pipeline.ainvoke(None, config)
        logger.success("✅ [Celery] Pipeline execution successful for job_id={}", job_id)

    try:
        _run_async(_run())
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        logger.error("❌ [Celery] Force resume failed for job_id={}: {}", job_id, e)
        raise e


@celery_app.task(
    name="tasks.send_hr_notification",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
def send_hr_notification_task(self, admin_email: str, job_title: str, shortlisted_candidates: list, job_id: str, trace_id: str = None):
    """
    Decoupled HR notification with resilience and circuit breaking.
    - Uses DistributedCircuitBreaker for email service.
    - Retries automatically on failure.
    """
    set_trace_id(trace_id)
    logger.info("📧 [Celery] Preparing HR notification for job: {}", job_title)

    
    async def _dispatch():
        from src.utils.email_utils import send_any_email
        from src.utils.config_builder import build_email_config
        from src.utils.resilience import with_resilience
        from src.config.settings import settings

        # Prepare HTML body
        candidates_summary = ""
        for c in shortlisted_candidates:
            candidates_summary += f"<li>{c['name']} (Score: {c.get('score', 0):.1f}) - {c.get('email', 'N/A')}</li>"
        
        subject = f"[Hiring AI] {len(shortlisted_candidates)} Candidates Shortlisted for {job_title}"
        body = f"<h2>Shortlist Ready</h2><p>Top candidates:</p><ul>{candidates_summary}</ul>"
        
        email_config = build_email_config(settings)
        
        # [NEW] Use Distributed Resilience for email provider
        return await with_resilience(
            "email", # Shared circuit breaker name for email providers
            send_any_email,
            to=[admin_email],
            subject=subject,
            html=body,
            provider="resend",
            config=email_config,
            fallback=True
        )

    try:
        success = _run_async(_dispatch())
        if not success:
            raise Exception("Email dispatch returned False")
        logger.success("✅ [Celery] HR notification sent to {}", admin_email)
    except Exception as exc:
        logger.error("❌ [Celery] Notification failed for {}: {}", admin_email, exc)
        raise self.retry(exc=exc)



# ─────────────────────────────────────────────────────────────
# Phase 2 & 15: Outbox Processor (Guaranteed Delivery)
# ─────────────────────────────────────────────────────────────
@celery_app.task(name="tasks.process_outbox_queue")
def process_outbox_queue():
    """
    High-frequency worker to process pending notifications.
    Phase 2: Row-level locking with SKIP LOCKED for multi-worker safety.
    """
    logger.info("📦 [Outbox] Scanning for pending notifications...")

    async def _process():
        from src.utils.email_utils import send_any_email
        from src.utils.config_builder import build_email_config
        from src.utils.resilience import with_resilience
        from src.config.settings import settings
        
        async with AsyncSessionLocal() as session:
            # Phase 2.2: SKIP LOCKED to allow multiple workers to scale
            stmt = select(Outbox).where(Outbox.status == "PENDING").with_for_update(skip_locked=True).limit(10)
            res = await db_timeout(session.execute(stmt))
            items = res.scalars().all()
            
            if not items:
                return 0

            for item in items:
                try:
                    # Phase 2.3: Dispatch Logic
                    email_config = build_email_config(settings)
                    payload = item.payload
                    
                    # Log with trace_id from payload (Phase 8, 14, 15)
                    tid = payload.get("trace_id")
                    set_trace_id(tid)
                    
                    s_logger = StructuredLogger(trace_id=tid, job_id=item.job_id)
                    s_logger.info("OUTBOX_DISPATCH_ATTEMPT", {"type": item.type, "to": payload.get("admin_email") or payload.get("email")})


                    # Generic email dispatch (handles both HR and Candidate types)
                    target = payload.get("admin_email") or payload.get("email")
                    subject = f"[Hiring AI] {payload.get('job_title')} Update"
                    
                    # Simplified body construction for outbox
                    body = f"Notification for {payload.get('job_title')}"
                    
                    if item.type == "SEND_SHORTLIST":
                        candidates = payload.get('shortlisted_candidates', [])
                        job_title = payload.get('job_title', 'Job')
                        job_id = str(item.job_id)
                        dashboard_url = f"http://localhost:5173/dashboard/jobs/{job_id}"
                        
                        candidate_rows = ""
                        for cand in candidates:
                            score = cand.get('score', 0)
                            color = "#10b981" if score >= 80 else "#3b82f6" if score >= 60 else "#f59e0b"
                            candidate_rows += f"""
                            <tr style="border-bottom: 1px solid #e5e7eb;">
                                <td style="padding: 16px 0; font-weight: bold; color: #111827;">{cand.get('name', 'N/A')}</td>
                                <td style="padding: 16px 0; color: #4b5563;">{cand.get('email', 'N/A')}</td>
                                <td style="padding: 16px 0; text-align: right;">
                                    <span style="background: {color}10; color: {color}; padding: 4px 10px; rounded: 6px; font-weight: 800; font-size: 13px;">
                                        {score:.1f}%
                                    </span>
                                </td>
                            </tr>
                            """

                        subject = f"🎯 {len(candidates)} Top Candidates for {job_title}"
                        body = f"""
                        <!DOCTYPE html>
                        <html>
                        <body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: sans-serif;">
                            <div style="max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);">
                                <div style="background: #2563eb; padding: 32px; color: #ffffff; text-align: center;">
                                    <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em;">Shortlist Ready</h1>
                                    <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 16px;">AI Screening Complete for <strong>{job_title}</strong></p>
                                </div>
                                <div style="padding: 32px;">
                                    <table style="width: 100%; border-collapse: collapse;">
                                        <thead>
                                            <tr style="border-bottom: 2px solid #f3f4f6;">
                                                <th style="text-align: left; padding-bottom: 12px; font-size: 12px; color: #9ca3af; text-transform: uppercase;">Candidate</th>
                                                <th style="text-align: left; padding-bottom: 12px; font-size: 12px; color: #9ca3af; text-transform: uppercase;">Email</th>
                                                <th style="text-align: right; padding-bottom: 12px; font-size: 12px; color: #9ca3af; text-transform: uppercase;">Fit Score</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {candidate_rows}
                                        </tbody>
                                    </table>
                                    
                                    <div style="margin-top: 32px; text-align: center;">
                                        <a href="{dashboard_url}" style="background: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 14px; display: inline-block;">
                                            View Full Candidate Profiles
                                        </a>
                                    </div>
                                </div>
                                <div style="background: #f9fafb; padding: 24px; border-top: 1px solid #f3f4f6; text-align: center; color: #6b7280; font-size: 12px;">
                                    This is an automated report from your <strong>Hiring.AI</strong> autonomous brain.
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    
                    elif item.type == "JD_APPROVAL_REQUEST":
                        subject = f"[Hiring AI] Review Required: {payload.get('job_title')}"
                        job_id = str(item.job_id)
                        approve_url = f"http://localhost:8000/jobs/{job_id}/approve-jd?approved=true"
                        reject_url = f"http://localhost:8000/jobs/{job_id}/approve-jd?approved=false"
                        dashboard_url = f"http://localhost:5173/dashboard/jobs/{job_id}"
                        
                        body = f"""
                        <!DOCTYPE html>
                        <html>
                        <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                            <div style="max-width: 700px; margin: 0 auto; padding: 40px 20px;">
                                <div style="margin-bottom: 32px;">
                                    <h1 style="color: #2563eb; font-size: 20px; display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                        📄 Job Description Draft Ready
                                    </h1>
                                    <p style="margin: 0; color: #4b5563; font-size: 14px;">
                                        The AI has generated a complete JD for the <strong>{payload.get('job_title')}</strong> role ({payload.get('department')}).
                                    </p>
                                    <p style="margin: 8px 0 0 0; color: #9ca3af; font-size: 12px; font-weight: bold;">
                                        Job ID: {job_id}
                                    </p>
                                </div>

                                <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 32px; margin-bottom: 32px; color: #1f2937; font-size: 15px; line-height: 1.6;">
                                    <div style="white-space: pre-wrap;">{payload.get('full_jd', '')}</div>
                                </div>

                                <div style="border-top: 2px solid #e5e7eb; padding-top: 32px;">
                                    <h3 style="display: flex; align-items: center; gap: 8px; margin: 0 0 12px 0; font-size: 16px; color: #000;">
                                        ⚡ Action Required (Human-in-the-Loop)
                                    </h3>
                                    <p style="margin: 0 0 24px 0; color: #4b5563; font-size: 14px;">
                                        The recruitment pipeline is currently <strong>paused</strong> waiting for your decision.
                                    </p>

                                    <div style="display: flex; gap: 12px; margin-bottom: 24px;">
                                        <a href="{approve_url}" style="background: #10b981; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: bold; display: inline-block;">
                                            ✅ Approve & Publish JD
                                        </a>
                                        <a href="{reject_url}" style="background: #f59e0b; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: bold; display: inline-block;">
                                            🔄 Review & Request Revision
                                        </a>
                                    </div>

                                    <p style="margin: 0; color: #6b7280; font-size: 13px;">
                                        Alternatively, to request AI revisions or manually edit the draft, <a href="{dashboard_url}" style="color: #2563eb; text-decoration: none;">visit your HR Dashboard &rarr;</a>
                                    </p>
                                </div>
                            </div>
                        </body>
                        </html>
                        """

                    success = await with_resilience(
                        "email",
                        send_any_email,
                        to=target,
                        subject=subject,
                        html=body,
                        provider="resend",
                        config=email_config,
                        fallback=True
                    )

                    if success:
                        item.status = "SENT"
                        s_logger.success("OUTBOX_DISPATCH_SUCCESS")
                    else:
                        raise Exception("Email provider returned False")

                except Exception as e:
                    # Phase 15: Retry Classification & Fast-Fail
                    is_retryable = is_retryable_error(e)
                    item.retry_count += 1
                    item.last_attempt_at = datetime.now(timezone.utc)
                    
                    if not is_retryable:
                        logger.error(f"💀 [Outbox] Permanent FAILURE for item {item.id}: {e}. Fast-failing to DLQ.")
                    else:
                        logger.warning(f"⚠️ [Outbox] Attempt {item.retry_count} failed for item {item.id}: {e}")
                    
                    # Move to DLQ if non-retryable OR if max retries reached
                    if not is_retryable or item.retry_count > 3:
                        if is_retryable:
                            logger.error(f"💀 [Outbox] Max retries exceeded for item {item.id}. Moving to DLQ.")
                            
                        await session.execute(
                            insert(DeadLetterQueue).values(
                                job_id=item.job_id,
                                type=item.type,
                                payload=item.payload,
                                reason=str(e),
                                retry_count=item.retry_count,
                                failed_at=datetime.now(timezone.utc)
                            )
                        )
                        item.status = "FAILED"


            await session.commit()
            return len(items)

    processed = _run_async(_process())
    if processed > 0:
        logger.success("🏁 [Outbox] Finished processing {} items", processed)
    return processed


# ─────────────────────────────────────────────────────────────
# Phase 11: Lease-Aware Recovery (Self-Healing)
# ─────────────────────────────────────────────────────────────
@celery_app.task(name="tasks.recover_dead_jobs")
def recover_dead_jobs():
    """
    Cron task to identify and reset jobs stuck in RUNNING for too long.
    Phase 11: Identifies stale leases (>5 mins) and resets them.
    """
    logger.info("🏥 [Recovery] Scanning for stalled job leases...")
    
    # Phase 15: Create a fresh root trace for this maintenance cycle
    from src.utils.production_safety import generate_trace_id
    set_trace_id(f"recovery-{generate_trace_id()}")

    async def _recover():

        async with AsyncSessionLocal() as session:
            # Phase 11.1 & 11.2: Atomic lease reset
            five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
            
            stmt = (
                update(Job)
                .where(Job.locked_at < five_mins_ago)
                .where(Job.locked_by.isnot(None))
                .values(locked_by=None, locked_at=None)
            )
            result = await db_timeout(session.execute(stmt))
            await session.commit()
            return result.rowcount

    recovered = _run_async(_recover())
    if recovered > 0:
        logger.success("✅ [Recovery] Successfully reset {} stalled job leases", recovered)
    return recovered


@celery_app.task(name="tasks.retry_dlq_tasks")
def retry_dlq_tasks():
    """
    Cron task to retry items from Dead Letter Queue that were transient failures.
    Phase 15: Automatic recovery of network-related errors.
    """
    logger.info("♻️ [Recovery] Scanning Dead Letter Queue for retryable items...")

    # Phase 15: Create a fresh root trace for this maintenance cycle
    from src.utils.production_safety import generate_trace_id
    set_trace_id(f"dlq-retry-{generate_trace_id()}")

    async def _retry():

        from src.utils.production_safety import is_retryable_error
        
        async with AsyncSessionLocal() as session:
            # 1. Identify items older than 30 mins to avoid immediate thrashing
            cooldown = datetime.now(timezone.utc) - timedelta(minutes=30)
            
            # Fetch candidates from DLQ
            stmt = select(DeadLetterQueue).where(DeadLetterQueue.failed_at < cooldown).limit(50)
            res = await session.execute(stmt)
            items = res.scalars().all()
            
            if not items:
                return 0

            count = 0
            for item in items:
                # 2. Check if the failure reason is retryable
                # We mock an exception with the reason string for the classifier
                mock_e = Exception(item.reason)
                if is_retryable_error(mock_e):
                    logger.info(f"🔄 [Recovery] Found retryable DLQ item {item.id} (Reason: {item.reason})")
                    
                    # Atomic migration from DLQ -> Outbox
                    # Type is re-derived or kept. We'll use a specific 'RECOVERY' type 
                    # OR preserve original if we had it. Since DLQ payload has it:
                    await session.execute(
                        insert(Outbox).values(
                            job_id=item.job_id,
                            type="RECOVERY_RETRY", # Flag for tracking
                            payload=item.payload,
                            status="PENDING",
                            retry_count=0,
                            created_at=datetime.now(timezone.utc)
                        ).on_conflict_do_nothing(index_elements=["job_id", "type"])
                    )
                    
                    # 3. Remove from DLQ
                    await session.delete(item)
                    count += 1
            
            await session.commit()
            return count

    retried = _run_async(_retry())
    if retried > 0:
        logger.success("🏁 [Recovery] Successfully migrated {} items back to Outbox", retried)
    return retried
