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

from src.state.schema import HiringState, PipelineStatus
from src.tools.hiring_tools import publish_jd_tool
from src.scheduler.tasks import wait_for_applications, SEVEN_DAYS_SEC


def publish_jd(state: HiringState) -> dict:
    """Publish approved JD and start the 7-day application wait."""
    job_id    = state.get("job_id", str(uuid.uuid4()))
    thread_id = state.get("graph_thread_id", "")

    # ── Invoke LangChain tool ─────────────────────────────────────────────────
    published_url = publish_jd_tool.invoke({
        "job_title":   state.get("job_title", ""),
        "jd_content":  state.get("jd_draft", ""),
    })

    # ── Schedule 7-day Celery event ──────────────────────────────────────────
    wait_for_applications.apply_async(
        args=[job_id, thread_id],
        countdown=SEVEN_DAYS_SEC,
    )

    deadline = (datetime.now(timezone.utc) + timedelta(seconds=SEVEN_DAYS_SEC)).isoformat()
    logger.success("📢 [publish_jd] Published: {} | Deadline: {}", published_url, deadline)

    return {
        "published_jd_url":      published_url,
        "applications_deadline": deadline,
        "applications":          [],
        "pipeline_status":       PipelineStatus.WAITING_FOR_APPLICATIONS.value,
    }
