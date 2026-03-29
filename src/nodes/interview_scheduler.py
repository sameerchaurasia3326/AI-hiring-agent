"""
src/nodes/interview_scheduler.py
──────────────────────────────────
LangGraph Node: schedule_interviews
─────────────────────────────────────
For each HR-selected candidate:
  1. Calls find_calendar_slots_tool — checks BOTH interviewer's AND HR's calendar
     via Google Calendar freebusy.query to find a genuinely free slot.
  2. Calls book_interview_tool — creates a Google Calendar event with:
     • Candidate as attendee
     • Interviewer as attendee
     • Auto-generated Google Meet link (conferenceData)
  3. Calls send_email_tool for invitation emails to both candidate and HR
  4. Persists meeting_link, calendar_event_id, and interviewer_email to DB

NO routing logic inside the node — all decisions are conditional edges.
State: HR_REVIEW_PENDING → INTERVIEW_SCHEDULED
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.config import settings
from src.tools.hiring_tools import find_calendar_slots_tool, book_interview_tool, send_email_tool
from src.utils.activity import log_activity_sync


# ── Stage info helper ─────────────────────────────────────────────────────────

async def _fetch_stage_info(job_id: str, stage_order: int = 1) -> dict:
    """Fetch the stage info (name, interviewer) for a specific order from the DB."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.db.database import AsyncSessionLocal
    from src.db.models import JobStage

    async with AsyncSessionLocal() as session:
        stmt = (
            select(JobStage)
            .options(selectinload(JobStage.assigned_user))
            .where(JobStage.job_id == job_id, JobStage.stage_order == stage_order)
        )
        stage = (await session.execute(stmt)).scalar_one_or_none()
        if stage:
            return {
                "stage_id": stage.id,
                "stage_name": stage.stage_name,
                "user_id": stage.assigned_user_id,
                "email": stage.assigned_user.email if stage.assigned_user else None
            }
        return None


async def schedule_interviews(state: HiringState) -> dict:
    """Book calendar events and send interview invitations using LangChain tools."""
    shortlist        = state.get("shortlist", [])
    selected_ids     = set(state.get("hr_selected_candidates", []))
    job_title        = state.get("job_title", "the role")
    job_id           = state.get("job_id", "")
    hr_email         = state.get("hiring_manager_email", settings.hr_email)

    # RBAC: Fetch the FIRST stage (stage_order=1)
    stage_info = await _fetch_stage_info(job_id, stage_order=1)
    
    if stage_info and stage_info["email"]:
        interviewer_email = stage_info["email"]
        assigned_user_id = stage_info["user_id"]
        stage_id = stage_info["stage_id"]
        stage_name = stage_info["stage_name"]
        logger.info(f"RBAC: Assigning interview to mapped user {interviewer_email} for stage {stage_name}")
    else:
        interviewer_email = state.get("interviewer_email", "") or hr_email
        assigned_user_id = None
        stage_id = stage_info["stage_id"] if stage_info else None
        stage_name = stage_info["stage_name"] if stage_info else "First Stage"
        logger.warning(f"RBAC: No interviewer mapped for first stage. Defaulting to HR {interviewer_email}")

    selected = [c for c in shortlist if c["candidate_id"] in selected_ids]

    if not selected:
        logger.warning("⚠️  [schedule_interviews] No candidates selected by HR — nothing to schedule.")
        return {"pipeline_status": PipelineStatus.INTERVIEW_SCHEDULED.value}

    # ── Step 1: Find free slots (checks both interviewer + HR calendar) ─────────
    slots_json: str = await find_calendar_slots_tool.ainvoke({
        "days_ahead":        7,
        "max_slots":         len(selected) * 2,   # extra slots as buffer
        "interviewer_email": interviewer_email,
        "duration_minutes":  60,
    })
    slots: list = json.loads(slots_json)

    if not slots:
        logger.warning("⚠️  [schedule_interviews] No free slots found for interviewer: {}", interviewer_email)
        # ── Step 1b: Notify HR of scheduling blockage ──────────────────────────
        await send_email_tool.ainvoke({
            "to":      hr_email,
            "subject": f"[Hiring AI] Action Required: No available slots for {job_title}",
            "body": (
                f"Hi,\n\n"
                f"The AI was unable to find any free slots on the calendar for "
                f"**{interviewer_email}** to schedule interviews for the **{job_title}** role.\n\n"
                f"Count of selected candidates: {len(selected)}\n\n"
                f"Please coordinate manually or ask the interviewer to update their calendar availability "
                f"and connect their Google Calendar if they haven't already.\n\n"
                f"Best regards,\nHiring.AI Bot"
            ),
        })
        return {"pipeline_status": PipelineStatus.INTERVIEW_SCHEDULED.value} # Move to next state but with warning

    updated_shortlist = [dict(c) for c in shortlist]
    meeting_links_log = []

    for i, candidate in enumerate(selected):
        if i >= len(slots):
            logger.warning("⚠️  No available slot for {} — skipping.", candidate["name"])
            break

        slot = slots[i]

        # ── Step 2: Book calendar event with interviewer + Google Meet ───────────
        booking_raw: str = await book_interview_tool.ainvoke({
            "candidate_name":   candidate["name"],
            "candidate_email":  candidate["email"],
            "slot_start":       slot["start"],
            "slot_end":         slot["end"],
            "job_title":        job_title,
            "interviewer_email": interviewer_email,
        })

        # book_interview_tool now returns JSON: {event_id, meet_link}
        try:
            booking = json.loads(booking_raw)
        except (json.JSONDecodeError, TypeError):
            booking = {"event_id": str(booking_raw), "meet_link": ""}

        event_id  = booking.get("event_id", "")
        meet_link = booking.get("meet_link", "")

        if "ERROR" in event_id:
            logger.error("📅 Booking failure for {}: {}", candidate["name"], event_id)
            await send_email_tool.ainvoke({
                "to": hr_email,
                "subject": f"[Hiring AI] Booking Error: {candidate['name']}",
                "body": f"The AI failed to create a calendar event for {candidate['name']} ({candidate['email']}).\nError: {event_id}\n\nPlease schedule manually."
            })
            continue

        # ── Step 3a: Email candidate ─────────────────────────────────────────────
        meet_section = f"\n🔗 Google Meet: {meet_link}" if meet_link else ""
        await send_email_tool.ainvoke({
            "to":      candidate["email"],
            "subject": f"Interview Invitation — {job_title}",
            "body": (
                f"Dear {candidate['name']},\n\n"
                f"Congratulations! You have been selected for an interview for "
                f"the **{job_title}** position.\n\n"
                f"📅 Date & Time: {slot['start']}"
                f"{meet_section}\n\n"
                f"Your interviewer will be: {interviewer_email}\n\n"
                f"Please accept the calendar invite to confirm.\n\n"
                f"Best regards,\nHiring Team"
            ),
        })

        # ── Step 3b: Email HR / interviewer ──────────────────────────────────────
        await send_email_tool.ainvoke({
            "to":      hr_email,
            "subject": f"[Hiring AI] Interview Scheduled: {candidate['name']}",
            "body": (
                f"Hi,\n\n"
                f"An interview has been scheduled for **{candidate['name']}** "
                f"for the **{job_title}** role.\n\n"
                f"📅 Date & Time: {slot['start']}\n"
                f"👤 Candidate:   {candidate['name']} ({candidate['email']})\n"
                f"🎙️  Interviewer: {interviewer_email}\n"
                f"🔗 Google Meet: {meet_link or 'N/A'}\n"
                f"🗓️  Calendar ID: {event_id}\n\n"
                f"The candidate has been notified and the calendar invite was sent."
            ),
        })

        log_activity_sync(job_id, message=f"Candidate {candidate['name']} shortlisted by HR", type="shortlisted")
        log_activity_sync(job_id, message=f"Invitation email sent to {candidate['name']}", type="email_sent")

        # ── Step 4: Persist to DB ────────────────────────────────────────────────
        await _persist_interview_to_db(
            job_id=job_id,
            candidate_email=candidate["email"],
            candidate_name=candidate["name"],
            job_title=job_title,
            slot_start=slot["start"],
            event_id=event_id,
            meet_link=meet_link,
            interviewer_email=interviewer_email,
            assigned_user_id=assigned_user_id,
            stage_id=stage_id,
            stage_name=stage_name,
        )

        # Update candidate record in shortlist state
        for c in updated_shortlist:
            if c["candidate_id"] == candidate["candidate_id"]:
                c["interview_slot"]    = slot["start"]
                c["calendar_event_id"] = event_id
                c["meeting_link"]      = meet_link
                c["interviewer_email"] = interviewer_email

        meeting_links_log.append({
            "candidate_id": candidate["candidate_id"],
            "meet_link":    meet_link,
            "event_id":     event_id,
        })

        logger.success(
            "📅 Scheduled: {} at {} | Meet: {} | Interviewer: {}",
            candidate["name"], slot["start"], meet_link or "N/A", interviewer_email,
        )

        log_activity_sync(
            job_id,
            message=f"Candidate {candidate['name']} scheduled for {stage_name} on {slot['start']}",
            type="interview_scheduled"
        )

    return {
        "shortlist":          updated_shortlist,
        "meeting_links":      meeting_links_log,
        "notifications_sent": True,
        "pipeline_status":    PipelineStatus.INTERVIEW_SCHEDULED.value,
    }


# ── DB persistence helper ─────────────────────────────────────────────────────

async def _persist_interview_to_db(
    job_id: str,
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    slot_start: str,
    event_id: str,
    meet_link: str,
    interviewer_email: str,
    assigned_user_id=None,
    stage_id=None,
    stage_name=None,
) -> None:
    """Write the scheduled interview details to the Application row and update Candidate stage."""
    try:
        from sqlalchemy import select, update
        from src.db.database import AsyncSessionLocal
        from src.db.models import Application, Candidate
        from src.tools.hiring_tools import send_email

        async with AsyncSessionLocal() as session:
            # 1. Update Candidate current status and stage
            candidate_row = (await session.execute(
                select(Candidate).where(Candidate.email == candidate_email)
            )).scalar_one_or_none()

            if not candidate_row:
                logger.warning("⚠️  DB: candidate {} not found — skipping persist.", candidate_email)
                return

            candidate_row.current_stage_id = stage_id
            candidate_row.status = "processing"

            # 2. Update Application (scheduling info)
            await session.execute(
                update(Application)
                .where(
                    Application.job_id       == job_id,
                    Application.candidate_id == candidate_row.id,
                )
                .values(
                    interview_slot    = datetime.fromisoformat(slot_start),
                    calendar_event_id = event_id,
                    meeting_link      = meet_link,
                    interviewer_email = interviewer_email,
                    assigned_user_id  = assigned_user_id,
                    invite_sent       = True,
                )
            )
            await session.commit()
            logger.success("💾 DB: candidate stage and application updated for {}", candidate_email)
            
            # 2.5 Log Event
            from src.utils.activity import log_activity_sync
            log_activity_sync(
                job_id,
                message=f"Candidate {candidate_name} entered stage: {stage_name or 'Interview'}",
                type="stage_entered"
            )

            # 3. Send Notification to Assigned Interviewer
            if assigned_user_id and interviewer_email:
                subject = "You have a candidate for interview"
                body = f"""You have a new candidate for interview.
                
Candidate name: {candidate_name}
Job role: {job_title}

Please log in to your dashboard to review the candidate details and access the interview meeting link.
Action link: http://localhost:8000/dashboard/my-tasks

Thank you,
Hiring.AI Assistant"""
                send_email(
                    to=interviewer_email,
                    subject=subject,
                    body=body
                )
                logger.success("📧 Sent new candidate task notification to {}", interviewer_email)

    except Exception as e:
        logger.error("⚠️  DB persist failed for {}: {}", candidate_email, e)
