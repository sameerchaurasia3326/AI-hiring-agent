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

from src.tools.platforms.linkedin import LinkedInClient


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ─────────────────────────────────────────────────────────────
# Task 1: Wait 7 days, then check for applications
# ─────────────────────────────────────────────────────────────
@celery_app.task(
    name="tasks.wait_for_applications",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5-min retry on failure
)
def wait_for_applications(self, job_id: str, thread_id: str) -> dict:
    """
    Fires 7 days after a job is posted.
    Resumes the LangGraph graph to evaluate whether applications arrived.
    """
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
def wait_for_hr_selection(self, job_id: str, thread_id: str) -> dict:
    """
    Fires 2 days after shortlist is sent to HR.
    Resumes graph to check if HR responded with candidate selections.
    """
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
    max_retries=2,
)
def publish_to_platforms(self, job_id: str, job_title: str, jd_content: str) -> dict:
    """
    Asynchronously posts to LinkedIn.
    """
    logger.info("📢 [publish_to_platforms] Starting async post for job_id={}", job_id)
    
    results = {}
    
    # 1. LinkedIn
    try:
        li = LinkedInClient()
        results["linkedin"] = li.publish_job(job_id, job_title, jd_content)
    except Exception as e:
        logger.error("❌ [Celery] LinkedIn failed: {}", e)
        results["linkedin"] = f"ERROR: {e}"

    logger.success("🏁 [publish_to_platforms] Finished job_id={}. Results: {}", job_id, results)
    print(f"\n✅ [WORKER] LinkedIn Publishing completed for Job {job_id}. Check results above!\n")
    return results


# ─────────────────────────────────────────────────────────────
# Shared: resume the LangGraph graph with a scheduler event
# ─────────────────────────────────────────────────────────────
async def _resume_graph_after_wait(job_id: str, thread_id: str, event: str) -> dict:
    """
    Loads the paused LangGraph graph for this job and resumes it
    by providing the scheduler event as the interrupt value.
    """
    from src.graph.pipeline import get_pipeline

    pipeline = await get_pipeline()
    config = {"configurable": {"thread_id": thread_id}}

    # Resume the graph — the interrupt() in the wait node will receive the dict
    result = await pipeline.ainvoke(
        Command(resume={
            "job_id": job_id,
            "decision": "scheduler_event",
            "event": event
        }),
        config=config,
    )
    logger.success(
        "✅ [_resume_graph_after_wait] Graph resumed for job_id={} with event={}",
        job_id, event,
    )
    return {"status": "resumed", "job_id": job_id, "event": event}
