"""
src/nodes/interview_scheduler.py
──────────────────────────────────
LangGraph Node: schedule_interviews
─────────────────────────────────────
For each HR-selected candidate:
  1. Calls find_calendar_slots_tool (@tool)
  2. Calls book_interview_tool (@tool)
  3. Calls send_email_tool (@tool) for invite

NO routing logic inside the node — all decisions are conditional edges.
State: HR_REVIEW_PENDING → INTERVIEW_SCHEDULED
"""
from __future__ import annotations

import json
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.tools.hiring_tools import find_calendar_slots_tool, book_interview_tool, send_email_tool


def schedule_interviews(state: HiringState) -> dict:
    """Book calendar events and send interview invitations using LangChain tools."""
    shortlist       = state.get("shortlist", [])
    selected_ids    = set(state.get("hr_selected_candidates", []))
    job_title       = state.get("job_title", "the role")

    selected = [c for c in shortlist if c["candidate_id"] in selected_ids]

    # ── Invoke: find available calendar slots ─────────────────────────────────
    slots_json: str = find_calendar_slots_tool.invoke({
        "days_ahead": 7,
        "max_slots":  len(selected) * 2,
    })
    slots: list = json.loads(slots_json)

    updated_shortlist = [dict(c) for c in shortlist]

    for i, candidate in enumerate(selected):
        if i >= len(slots):
            logger.warning("⚠️  No more slots for {}", candidate["name"])
            break

        slot = slots[i]

        # ── Invoke: book calendar event ───────────────────────────────────────
        event_id: str = book_interview_tool.invoke({
            "candidate_name":  candidate["name"],
            "candidate_email": candidate["email"],
            "slot_start":      slot["start"],
            "slot_end":        slot["end"],
            "job_title":       job_title,
        })

        # ── Invoke: send invitation email ─────────────────────────────────────
        send_email_tool.invoke({
            "to":      candidate["email"],
            "subject": f"Interview Invitation — {job_title}",
            "body":    (
                f"Dear {candidate['name']},\n\n"
                f"Congratulations! You are invited for an interview for the {job_title} position.\n\n"
                f"📅 Date & Time: {slot['start']}\n"
                f"🔗 A Google Meet link has been added to your calendar invite.\n\n"
                f"Please confirm by accepting the calendar invite.\n\n"
                f"Best regards,\nHiring Team"
            ),
        })

        # Update candidate record in shortlist
        for c in updated_shortlist:
            if c["candidate_id"] == candidate["candidate_id"]:
                c["interview_slot"]    = slot["start"]
                c["calendar_event_id"] = event_id

        logger.success("📅 Scheduled: {} at {}", candidate["name"], slot["start"])

    return {
        "shortlist":           updated_shortlist,
        "notifications_sent":  True,
        "pipeline_status":     PipelineStatus.INTERVIEW_SCHEDULED.value,
    }
