"""
src/tools/hiring_tools.py
──────────────────────────
ALL LangChain @tool definitions for the hiring pipeline.

Every tool here is:
  1. Decorated with @tool → becomes a LangChain-native callable
  2. Usable inside a LangGraph ToolNode (auto-invoked via LLM tool calls)
  3. Never called directly with Python if/else from other code

Tools defined here:
  - send_email_tool
  - send_offer_letter_tool
  - send_rejection_email_tool
  - send_shortlist_to_hr_tool
  - find_calendar_slots_tool
  - book_interview_tool
  - parse_resume_tool
  - publish_jd_tool
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from langchain_core.tools import tool, Tool
from loguru import logger

from src.config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL TOOLS
# ═══════════════════════════════════════════════════════════════════════════════
async def _dispatch_pure_email(to: str, subject: str, body: str, html: bool = False) -> str:
    """
    Step 9: Internal dispatch for tools using the pure email system.
    """
    from src.utils.email_utils import send_any_email
    from src.utils.config_builder import build_email_config
    
    try:
        email_config = build_email_config(settings)
        # Default tools to 'resend' with SMTP fallback as per general policy
        success = await send_any_email(
            to=to,
            subject=subject,
            html=body,
            provider="resend",
            config=email_config,
            fallback=True
        )
        if success:
            return f"Email sent to {to}"
        return f"ERROR: All email providers failed for {to}"
    except Exception as e:
        logger.error(f"❌ Email dispatch error for {to}: {e}")
        return f"ERROR: {e}"



@tool
async def send_email_tool(to: str, subject: str, body: str) -> str:
    """Send a plain-text email to any recipient.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text body of the email.
    Returns:
        Confirmation string.
    """
    return await _dispatch_pure_email(to, subject, body, html=False)


from src.nodes.shortlist_sender import send_shortlist_to_hr

send_hr_notification_tool = Tool(
    name="send_hr_notification",
    func=send_shortlist_to_hr,
    description="Send shortlisted candidates to HR"
)

print("DEBUG TOOL:", send_hr_notification_tool)
print("DEBUG FUNC:", send_hr_notification_tool.func)
print("IS CALLABLE:", callable(send_hr_notification_tool.func))


@tool
async def send_offer_letter_tool(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    salary_range: str,
) -> str:
    """Send a formal offer letter email to a selected candidate.

    Args:
        candidate_email: Candidate's email address.
        candidate_name: Full name of the candidate.
        job_title: Role they are being offered.
        salary_range: Compensation package string.
    Returns:
        Confirmation string.
    """
    body = f"""Dear {candidate_name},

🎉 Congratulations! We are delighted to offer you the position of {job_title}.

Your skills and experience stood out throughout our process, and we are excited to have you join our team.

📋 Offer Summary:
  • Role: {job_title}
  • Compensation: {salary_range}
  • Start Date: To be mutually confirmed

Please review the formal offer documents and respond within 5 business days to confirm your acceptance.

With warm regards,
The Hiring Team"""
    return await _dispatch_pure_email(candidate_email, f"Offer Letter — {job_title}", body)


@tool
async def send_rejection_email_tool(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    company_name: str = "Hiring Team",
) -> str:
    """Send a professional rejection email to a non-selected candidate.

    Args:
        candidate_email: Candidate's email address.
        candidate_name: Full name of the candidate.
        job_title: Role they applied for.
        company_name: Name of the hiring company.
    Returns:
        Confirmation string.
    """
    body = f"""Hi {candidate_name},

Thank you for your interest in the {job_title} role.

After careful consideration, we will not be moving forward with your application at this stage.

We appreciate your time and effort and wish you success in your job search.

Best regards,
{company_name}"""
    return await _dispatch_pure_email(candidate_email, "Update on your application", body)


@tool
async def send_shortlist_email_tool(
    hr_email: str,
    job_title: str,
    job_id: str,
    candidates_json: str,
) -> str:
    """Email the AI-generated shortlist to the HR/hiring manager.

    Args:
        hr_email: Hiring manager's email address.
        job_title: The open role.
        job_id: UUID of the job (used in the action link).
        candidates_json: JSON string of [{name, email, score}] objects.
    Returns:
        Confirmation string.
    """
    import json
    candidates = json.loads(candidates_json)
    
    # ── [PREMIUM DESIGN] Card-based Email Template ──────────────────────────
    candidate_cards = ""
    for c in candidates:
        select_url = f"http://localhost:8000/jobs/{job_id}/select-candidates?selected_ids={c['candidate_id']}"
        score_color = "#10b981" if c['score'] >= 80 else "#f59e0b" if c['score'] >= 60 else "#ef4444"
        
        candidate_cards += f"""
        <div style="background: #ffffff; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #e5e7eb; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                <div style="flex: 1;">
                    <h3 style="margin: 0 0 4px 0; color: #111827; font-size: 18px; font-weight: 700;">{c['name']}</h3>
                    <p style="margin: 0; color: #6b7280; font-size: 14px;">{c['email']}</p>
                </div>
                <div style="background: {score_color}; color: white; padding: 6px 12px; border-radius: 9999px; font-size: 14px; font-weight: 600; white-space: nowrap;">
                    Score: {c['score']:.1f}/100
                </div>
            </div>
            <div style="border-top: 1px solid #f3f4f6; padding-top: 16px; margin-top: 16px; display: flex; gap: 12px;">
                <a href="{select_url}" style="background: #2563eb; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 600; display: inline-block; transition: background 0.2s;">
                    Select for Interview
                </a>
                <a href="http://localhost:5173/candidates/{c['candidate_id']}" style="background: #f3f4f6; color: #374151; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 600; display: inline-block;">
                    View Profile
                </a>
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f9fafb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 40px 32px; text-align: center;">
                <div style="display: inline-block; background: rgba(255, 255, 255, 0.1); padding: 8px 16px; border-radius: 8px; color: #ffffff; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px;">
                    🤖 AI Hiring Intelligence
                </div>
                <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 800; letter-spacing: -0.025em;">
                    Candidate Shortlist Ready
                </h1>
                <p style="margin: 8px 0 0 0; color: #dbeafe; font-size: 16px;">
                    {job_title}
                </p>
            </div>

            <!-- Content -->
            <div style="padding: 32px; background-color: #f9fafb;">
                <p style="margin: 0 0 24px 0; color: #4b5563; font-size: 16px; line-height: 1.5;">
                    The AI agent has analyzed all applicants and identified the top {len(candidates)} high-potential candidates for your review.
                </p>
                
                {candidate_cards}

                <div style="margin-top: 32px; padding: 20px; background: #eff6ff; border-radius: 12px; border: 1px solid #bfdbfe;">
                    <p style="margin: 0; color: #1e40af; font-size: 14px; line-height: 1.5;">
                        <strong>Next Steps:</strong> Please review the candidates and click the selection buttons to move them to the interview stage. Links remain active for 48 hours.
                    </p>
                </div>
            </div>

            <!-- Footer -->
            <div style="padding: 32px; text-align: center; border-top: 1px solid #e5e7eb;">
                <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                    © 2024 Hiring AI Platform. Powered by Advanced Agentic Intelligence.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    return await _smtp_send(hr_email, f"[Hiring AI] {len(candidates)} Candidates Shortlisted for {job_title}", html, html=True)


async def send_email(to: str, subject: str, body: str, html: bool = False) -> str:
    """Public utility for sending emails across the system.
    
    This function is intended for internal use by nodes and API endpoints. 
    For LLM tool calling, use send_email_tool.
    """
    return await _smtp_send(to, subject, body, html)


# ═══════════════════════════════════════════════════════════════════════════════
# CALENDAR TOOLS
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_calendar_service_async(email: str = None):
    """Internal: build authenticated Google Calendar service.
    
    Priority:
      1. User-specific OAuth service (if email matches a connected user)
      2. Service Account (fallback for HR/System)
      3. Mock (if both fail)
    """
    from src.db.database import AsyncSessionLocal
    from src.db.models import User
    from src.api.google_auth_utils import get_user_calendar_service
    from sqlalchemy import select

    if email:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.email == email)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if user and user.google_refresh_token:
                logger.info("📅 Using personal OAuth service for {}", email)
                return await get_user_calendar_service(str(user.id), session)

    # 2. Fallback to Service Account
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    service_account_file = "service-account.json"
    
    if not Path(service_account_file).exists():
        logger.warning("📅 Service account credentials missing at {}. Using MOCK calendar.", service_account_file)
        return None

    try:
        # Running sync IO in thread
        creds = await asyncio.to_thread(
            service_account.Credentials.from_service_account_file,
            service_account_file, 
            scopes=SCOPES
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error("📅 Failed to initialize Google Calendar service: {}", e)
        return None


@tool
async def find_calendar_slots_tool(
    days_ahead: int = 7,
    max_slots: int = 5,
    interviewer_email: str = "",
    duration_minutes: int = 60,
) -> str:
    """Find available interview slots by checking BOTH the interviewer's and HR's calendar.

    Calls Google Calendar freebusy.query for both calendars, merges all busy
    periods, then walks the next `days_ahead` days in `duration_minutes`
    increments (Mon–Fri, 9am–5pm UTC) to find genuinely free slots.

    Args:
        days_ahead: How many days ahead to search.
        max_slots: Maximum number of free slots to return.
        interviewer_email: Email of the person conducting interviews (calendar to check).
        duration_minutes: Length of each interview slot in minutes (default 60).
    Returns:
        JSON string [{"start": ISO8601, "end": ISO8601}, ...]
    """
    import json
    try:
        service = await _get_calendar_service_async(interviewer_email)
        if not service:
            now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
            mock_slots = [
                {
                    "start": (now + timedelta(days=i, hours=1)).isoformat(),
                    "end":   (now + timedelta(days=i, hours=1, minutes=duration_minutes)).isoformat(),
                }
                for i in range(1, max_slots + 1)
            ]
            logger.info("📅 [MOCK CALENDAR] {} free slots (interviewer: {})", len(mock_slots), interviewer_email or "none")
            return json.dumps(mock_slots)

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)

        # ── Query freebusy for BOTH calendars ──────────────────────────────────
        calendar_ids = [settings.google_calendar_id]
        if interviewer_email and interviewer_email != settings.google_calendar_id:
            calendar_ids.append(interviewer_email)

        freebusy_result = await asyncio.to_thread(
            service.freebusy().query(body={
                "timeMin": now.isoformat(),
                "timeMax": end.isoformat(),
                "items":   [{"id": cal_id} for cal_id in calendar_ids],
            }).execute
        )

        # Merge all busy periods from all queried calendars
        busy_raw: list[dict] = []
        for cal_id in calendar_ids:
            cal_busy = freebusy_result["calendars"].get(cal_id, {}).get("busy", [])
            busy_raw.extend(cal_busy)

        # Parse to datetime for easier comparison
        busy_parsed = [
            (
                datetime.fromisoformat(b["start"]),
                datetime.fromisoformat(b["end"]),
            )
            for b in busy_raw
        ]

        # ── Walk time range to find free slots ─────────────────────────────────
        delta       = timedelta(minutes=duration_minutes)
        slots: list = []
        candidate   = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)

        while len(slots) < max_slots and candidate < end:
            slot_end = candidate + delta

            # Only Mon–Fri, between 09:00 and 17:00 UTC
            if candidate.weekday() < 5 and 9 <= candidate.hour < 17 and slot_end.hour <= 17:
                is_busy = any(
                    candidate < b_end and slot_end > b_start
                    for b_start, b_end in busy_parsed
                )
                if not is_busy:
                    slots.append({
                        "start": candidate.isoformat(),
                        "end":   slot_end.isoformat(),
                    })

            candidate += timedelta(hours=1)

        logger.info("📅 Found {} free slots for interviewer={}", len(slots), interviewer_email or "HR")
        return json.dumps(slots)

    except Exception as e:
        logger.error("find_calendar_slots_tool failed: {}", e)
        return json.dumps([])



@tool
async def book_interview_tool(
    candidate_name: str,
    candidate_email: str,
    slot_start: str,
    slot_end: str,
    job_title: str,
    interviewer_email: str = "",
) -> str:
    """Book an interview calendar event with both the candidate and interviewer as attendees.

    Creates a Google Calendar event with an auto-generated Google Meet link.
    Both the candidate and interviewer receive calendar invites.

    Args:
        candidate_name: Full name of the candidate.
        candidate_email: Candidate's email address.
        slot_start: ISO 8601 start datetime string.
        slot_end: ISO 8601 end datetime string.
        job_title: Position being interviewed for.
        interviewer_email: Email of the person conducting the interview.
    Returns:
        JSON string {"event_id": str, "meet_link": str}, or '{"error": "..."}' on failure.
    """
    import json
    try:
        service = await _get_calendar_service_async(interviewer_email)
        if not service:
            mock_id   = f"mock-event-{uuid.uuid4().hex[:8]}"
            mock_link = f"https://meet.google.com/mock-{uuid.uuid4().hex[:8]}"
            logger.warning(
                "📅 [MOCK CALENDAR] Booked interview for {} at {} | ID: {} | Meet: {}",
                candidate_name, slot_start, mock_id, mock_link,
            )
            
            # [NEW] Send confirmation email even for mock scheduling so user sees it
            await _smtp_send(
                to=candidate_email,
                subject=f"Interview Scheduled: {job_title}",
                body=f"Hi {candidate_name},\n\nYour interview for {job_title} has been scheduled.\n\nDate/Time: {slot_start}\nLink: {mock_link}\n\nBest regards,\nThe Hiring Team"
            )
            
            return json.dumps({"event_id": mock_id, "meet_link": mock_link})

        # Build attendees list — always include candidate; add interviewer if provided
        attendees = [{"email": candidate_email}]
        if interviewer_email:
            attendees.append({"email": interviewer_email})

        event = {
            "summary":     f"Interview: {candidate_name} — {job_title}",
            "description": (
                f"AI-scheduled interview for the {job_title} position.\n\n"
                f"Candidate: {candidate_name} ({candidate_email})\n"
                f"Interviewer: {interviewer_email or 'TBD'}"
            ),
            "start":     {"dateTime": slot_start, "timeZone": "UTC"},
            "end":       {"dateTime": slot_end,   "timeZone": "UTC"},
            "attendees": attendees,
            "conferenceData": {
                "createRequest": {
                    "requestId":             f"hire-{uuid.uuid4().hex[:8]}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
            "reminders": {"useDefault": True},
        }

        created = await asyncio.to_thread(
            service.events().insert(
                calendarId=settings.google_calendar_id,
                body=event,
                conferenceDataVersion=1,   # required for Meet link generation
                sendUpdates="all",         # sends invites to all attendees
            ).execute
        )

        meet_link = created.get("hangoutLink", "")
        event_id  = created["id"]

        logger.success(
            "📅 Booked: {} at {} | Meet: {} | Interviewer: {}",
            candidate_name, slot_start, meet_link, interviewer_email or "N/A",
        )
        return json.dumps({"event_id": event_id, "meet_link": meet_link})

    except Exception as e:
        logger.error("book_interview_tool failed: {}", e)
        return json.dumps({"event_id": f"ERROR:{e}", "meet_link": ""})



# ═══════════════════════════════════════════════════════════════════════════════
# RESUME / JD TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def parse_resume_tool(resume_path: str) -> str:
    """Extract plain text from a PDF or DOCX resume file.

    Args:
        resume_path: Absolute path to the resume file.
    Returns:
        Extracted plain text content (max 6000 chars).
    """
    p = Path(resume_path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
            return text[:6000]
        except Exception as e:
            return f"ERROR: PDF parse failed: {e}"
    elif suffix in {".docx", ".doc"}:
        try:
            from docx import Document
            return "\n".join(para.text for para in Document(str(p)).paragraphs)[:6000]
        except Exception as e:
            return f"ERROR: DOCX parse failed: {e}"
    elif suffix == ".txt":
        try:
            return p.read_text(encoding="utf-8")[:6000]
        except Exception as e:
            return f"ERROR: TXT parse failed: {e}"
            
    logger.warning("❌ [parse_resume_tool] Unsupported file: path={} | suffix={}", resume_path, suffix)
    return f"ERROR: Unsupported file type (suffix: {suffix})"


@tool
def publish_jd_tool(job_title: str, jd_content: str) -> str:
    """Publish a Job Description to the careers portal and return the public URL.

    Args:
        job_title: The role title.
        jd_content: Full JD text to publish.
    Returns:
        Public URL of the published job posting.
    """
    # Stub — replace with real ATS / LinkedIn API call
    post_id = uuid.uuid4().hex[:8]
    url = f"https://careers.company.com/jobs/{post_id}"
    logger.success("📢 JD published: {}", url)
    return url


# ── All tools collected for binding ──────────────────────────────────────────
ALL_TOOLS = [
    send_email_tool,
    send_hr_notification_tool,
    send_offer_letter_tool,
    send_rejection_email_tool,
    send_shortlist_email_tool,
    find_calendar_slots_tool,
    book_interview_tool,
    parse_resume_tool,
    publish_jd_tool,
]
