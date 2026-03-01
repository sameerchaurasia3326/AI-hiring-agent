"""
src/nodes/shortlist_sender.py
──────────────────────────────
LangGraph Node: send_shortlist_to_hr
──────────────────────────────────────
Invokes send_shortlist_email_tool (LangChain @tool) + fires 2-day Celery wait.
Returns state delta only. NO routing logic.
State: SCREENING → HR_REVIEW_PENDING
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.tools.hiring_tools import send_shortlist_email_tool
from src.scheduler.tasks import wait_for_hr_selection, TWO_DAYS_SEC


def send_shortlist_to_hr(state: HiringState) -> dict:
    """Send ranked shortlist to HR via tool and start the 2-day timer."""
    shortlist = state.get("shortlist", [])
    job_id    = state.get("job_id", "")
    thread_id = state.get("graph_thread_id", "")
    hr_email  = state.get("hiring_manager_email", "")

    # ── Invoke LangChain tool ─────────────────────────────────────────────────
    send_shortlist_email_tool.invoke({
        "hr_email":       hr_email,
        "job_title":      state.get("job_title", ""),
        "job_id":         job_id,
        "candidates_json": json.dumps([
            {"name": c["name"], "email": c["email"], "score": c["score"]}
            for c in shortlist
        ]),
    })

    # ── Fire 2-day Celery wait ────────────────────────────────────────────────
    wait_for_hr_selection.apply_async(args=[job_id, thread_id], countdown=TWO_DAYS_SEC)
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=TWO_DAYS_SEC)).isoformat()

    logger.success("📧 [shortlist_sender] Sent {} candidates to HR. 2-day timer started.", len(shortlist))
    return {
        "shortlist_sent_to_hr":  True,
        "hr_selection_deadline": deadline,
        "pipeline_status":       PipelineStatus.HR_REVIEW_PENDING.value,
    }
