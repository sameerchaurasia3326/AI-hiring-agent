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

import smtplib
import uuid
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

from langchain_core.tools import tool
from loguru import logger

from src.config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def _smtp_send(to: str, subject: str, body: str, html: bool = False) -> str:
    """Internal SMTP dispatch — not exposed as a tool directly."""
    msg = MIMEMultipart("alternative")
    msg["From"]    = settings.from_email
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if html else "plain", "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as srv:
        srv.ehlo()
        srv.starttls()
        srv.login(settings.smtp_user, settings.smtp_password)
        srv.sendmail(settings.from_email, [to], msg.as_string())

    logger.success("📧 Email sent → {}: {}", to, subject)
    return f"Email sent to {to}"


@tool
def send_email_tool(to: str, subject: str, body: str) -> str:
    """Send a plain-text email to any recipient.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text body of the email.
    Returns:
        Confirmation string.
    """
    return _smtp_send(to, subject, body, html=False)


@tool
def send_hr_notification_tool(hr_email: str, subject: str, html_body: str) -> str:
    """Send an HTML-formatted notification email to the HR/hiring manager.

    Args:
        hr_email: Hiring manager's email address.
        subject: Email subject.
        html_body: HTML content of the notification.
    Returns:
        Confirmation string.
    """
    return _smtp_send(hr_email, subject, html_body, html=True)


@tool
def send_offer_letter_tool(
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
    return _smtp_send(candidate_email, f"Offer Letter — {job_title}", body)


@tool
def send_rejection_email_tool(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
) -> str:
    """Send a professional rejection email to a non-selected candidate.

    Args:
        candidate_email: Candidate's email address.
        candidate_name: Full name of the candidate.
        job_title: Role they applied for.
    Returns:
        Confirmation string.
    """
    body = f"""Dear {candidate_name},

Thank you sincerely for investing your time in our {job_title} interview process.

After thorough deliberation, we have decided to move forward with another candidate whose experience more closely aligns with our immediate needs.

We were genuinely impressed by your background and warmly encourage you to apply for future openings.

Wishing you every success in your career journey.

Kind regards,
The Hiring Team"""
    return _smtp_send(candidate_email, f"Application Update — {job_title}", body)


@tool
def send_shortlist_email_tool(
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
    rows = "\n".join(
        f"  <tr><td>{i+1}</td><td>{c['name']}</td><td>{c['email']}</td>"
        f"<td><b>{c['score']:.1f}/100</b></td></tr>"
        for i, c in enumerate(candidates)
    )
    html = f"""
<h2>🤖 AI Candidate Shortlist — {job_title}</h2>
<p>The AI has ranked the top {len(candidates)} candidate(s). Please review and select who should proceed to interview.</p>
<table border="1" cellpadding="8" cellspacing="0">
  <tr style="background:#f0f0f0"><th>#</th><th>Name</th><th>Email</th><th>AI Score</th></tr>
{rows}
</table>
<br>
<p><strong>⚡ Action Required (within 2 days):</strong><br>
POST <code>/jobs/{job_id}/select-candidates</code> with the <code>candidate_ids</code> list to confirm your selections.</p>
"""
    return _smtp_send(hr_email, f"[Hiring AI] Shortlist Ready — {job_title}", html, html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CALENDAR TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_calendar_service():
    """Internal: build authenticated Google Calendar service."""
    import os
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    token_path = "./config/token.json"
    creds = None

    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.google_credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


@tool
def find_calendar_slots_tool(days_ahead: int = 7, max_slots: int = 5) -> str:
    """Find available interview slots on the HR's Google Calendar.

    Args:
        days_ahead: How many days ahead to search for free slots.
        max_slots: Maximum number of slots to return.
    Returns:
        JSON string of available slots [{start, end}].
    """
    import json
    try:
        service = _get_calendar_service()
        now     = datetime.now(timezone.utc)
        end     = now + timedelta(days=days_ahead)

        busy = service.freebusy().query(body={
            "timeMin": now.isoformat(), "timeMax": end.isoformat(),
            "items": [{"id": settings.google_calendar_id}],
        }).execute()["calendars"].get(settings.google_calendar_id, {}).get("busy", [])

        slots, candidate = [], now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while len(slots) < max_slots and candidate < end:
            if candidate.weekday() < 5 and 9 <= candidate.hour < 17:
                slot_end = candidate + timedelta(hours=1)
                if not any(
                    candidate < datetime.fromisoformat(b["end"]) and
                    slot_end > datetime.fromisoformat(b["start"])
                    for b in busy
                ):
                    slots.append({"start": candidate.isoformat(), "end": slot_end.isoformat()})
            candidate += timedelta(hours=1)

        return json.dumps(slots)
    except Exception as e:
        logger.error("find_calendar_slots_tool failed: {}", e)
        return json.dumps([])


@tool
def book_interview_tool(
    candidate_name: str,
    candidate_email: str,
    slot_start: str,
    slot_end: str,
    job_title: str,
) -> str:
    """Book an interview calendar event and return the event ID.

    Args:
        candidate_name: Full name of the candidate.
        candidate_email: Candidate's email address.
        slot_start: ISO 8601 start datetime string.
        slot_end: ISO 8601 end datetime string.
        job_title: Position being interviewed for.
    Returns:
        Calendar event ID string, or 'ERROR:...' on failure.
    """
    try:
        service = _get_calendar_service()
        event = {
            "summary": f"Interview: {candidate_name} — {job_title}",
            "description": f"AI-scheduled interview for the {job_title} position.",
            "start": {"dateTime": slot_start, "timeZone": "UTC"},
            "end":   {"dateTime": slot_end,   "timeZone": "UTC"},
            "attendees": [{"email": candidate_email}],
            "conferenceData": {
                "createRequest": {"requestId": f"hire-{uuid.uuid4().hex[:8]}"}
            },
            "reminders": {"useDefault": True},
        }
        created = service.events().insert(
            calendarId=settings.google_calendar_id,
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all",
        ).execute()
        logger.success("📅 Booked: {} at {}", candidate_name, slot_start)
        return created["id"]
    except Exception as e:
        logger.error("book_interview_tool failed: {}", e)
        return f"ERROR:{e}"


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
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
            return text[:6000]
        except Exception as e:
            return f"ERROR: PDF parse failed: {e}"
    elif p.suffix.lower() in {".docx", ".doc"}:
        try:
            from docx import Document
            return "\n".join(para.text for para in Document(str(p)).paragraphs)[:6000]
        except Exception as e:
            return f"ERROR: DOCX parse failed: {e}"
    return "ERROR: Unsupported file type"


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
