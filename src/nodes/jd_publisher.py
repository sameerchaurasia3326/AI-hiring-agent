"""
src/nodes/jd_publisher.py
──────────────────────────
LangGraph Node: publish_jd (uses LangChain tool)
─────────────────────────────────────────────────
Invokes publish_jd_tool + dispatches Celery 7-day wait.
Returns state delta. NO routing logic here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from loguru import logger

from sqlalchemy import update
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from src.state.schema import HiringState, PipelineStatus
from src.scheduler.tasks import wait_for_applications, publish_to_platforms

async def publish_jd(state: HiringState) -> dict:
    """Publish approved JD and start the 7-day application wait."""
    job_id    = state.get("job_id", str(uuid.uuid4()))
    thread_id = state.get("graph_thread_id", "")
    job_title = state.get("job_title", "")
    jd_content = state.get("jd_draft", "")

    # ── ANTI-SPAM GUARD ──────────────────────────────────────────────────────
    # Only post if we haven't already posted or isn't "Processing"
    existing_url = state.get("published_jd_url", "")
    if existing_url and existing_url != "Processing...":
        logger.warning("🛡️ [publish_jd] Anti-Spam Guard: Job already published at {}. Skipping.", existing_url)
    elif existing_url == "Processing...":
        logger.info("⏳ [publish_jd] Anti-Spam Guard: Job is already being processed. Skipping duplicate trigger.")
    else:
        # ── Dispatch Asynchronous Publishing (LinkedIn + Internshala) ────────────
        publish_to_platforms.apply_async(
            args=[job_id, job_title, jd_content]
        )
        logger.info("📢 [publish_jd] Async publishing triggered for job_id={}", job_id)

    # ── Database Sync: Set pipeline_state and published_url ─────────────────
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    pipeline_state=PipelineStatus.WAITING_FOR_APPLICATIONS.value,
                    published_jd_url="Processing..."
                )
            )
            await session.commit()
            logger.info("💾 [publish_jd] Persisted JD status to database for job_id={}", job_id)
        except Exception as e:
            logger.error("❌ [publish_jd] Database sync failed: {}", e)

    # ── Schedule Celery event for resume collection ──────────────────────────
    # Use a short countdown (30s) so that in testing, applications
    # are collected automatically after JD is published.
    COLLECT_AFTER_SEC = 30  # short window for testing; switch to SEVEN_DAYS_SEC in production
    wait_for_applications.apply_async(
        args=[job_id, thread_id],
        countdown=COLLECT_AFTER_SEC,
    )

    deadline = (datetime.now(timezone.utc) + timedelta(seconds=COLLECT_AFTER_SEC)).isoformat()
    logger.success("📢 [publish_jd] Published! Resume collection starts in {}s", COLLECT_AFTER_SEC)

    return {
        "published_jd_url":      "Processing...",
        "applications_deadline": deadline,
        "applications":          [],
        "pipeline_status":       PipelineStatus.WAITING_FOR_APPLICATIONS.value,
    }
