"""
src/api/main.py
────────────────
FastAPI application — the external interface for HR interactions.

Endpoints:
  POST /jobs                        — HR submits new hiring request → starts LangGraph pipeline
  POST /jobs/{job_id}/approve-jd    — HR approves/rejects JD → resumes graph (Decision 1)
  POST /jobs/{job_id}/select-candidates — HR selects candidates → resumes graph (Decision 3)
  POST /jobs/{job_id}/final-decision    — HR sends post-interview decision (Decision 4)
  GET  /jobs/{job_id}/status        — Query current pipeline state
"""
from __future__ import annotations

# ── Load .env FIRST so LANGCHAIN_TRACING_V2 is set before LangChain imports ──
import os
import uuid
import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any, Annotated, Dict, Literal

from dotenv import load_dotenv
load_dotenv(override=True)
# LangSmith tracing is now active if LANGCHAIN_TRACING_V2=true in .env

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from loguru import logger

from sqlalchemy import select, update, func, text, UniqueConstraint, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from langgraph.types import Command
from src.graph.pipeline import get_pipeline
from src.state.schema import HiringState, PipelineStatus
from src.config.jd_templates import JD_TEMPLATES
from src.db.database import AsyncSessionLocal, get_db
from src.db.models import (
    Job, ScreeningQuestion, Test, TestQuestion, PipelineState,
    Organization, User, Invite, JobStage, Candidate, Application,
    Activity, InterviewFeedback, Interview, UserRole
)
from src.api.auth import (
    get_current_user, get_current_user_optional, require_admin,
    require_interviewer_or_above, authenticate_websocket, create_token
)
from src.api.websocket_manager import manager
from fastapi import WebSocket, WebSocketDisconnect, Query
from src.config.settings import settings
from src.utils.activity import log_activity
from src.tools.hiring_tools import send_email, send_rejection_email_tool
from src.api.google_auth_utils import get_google_auth_url, exchange_code_for_tokens
from src.utils.config_builder import build_email_config
from src.tools.llm_factory import get_llm
from src.utils.production_safety import set_trace_id, generate_trace_id

from langchain_core.prompts import ChatPromptTemplate

app = FastAPI(
    title="Hiring AI — Automation System",
    description="AI-driven hiring pipeline powered by LangGraph + LangChain",
    version="1.0.0",
)

# ── CORS Middleware Configuration ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for local development/testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the HR UI
os.makedirs("src/api/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

@app.on_event("startup")
async def startup_resume_orphaned_jobs():
    """Auto-resume any jobs that were interrupted by a server restart."""
    
    async def resume_jobs():
        pipeline = await get_pipeline()
        async with AsyncSessionLocal() as session:
            # Find jobs that are in active processing states
            # NOTE: All non-terminal states must be listed here to ensure
            # full fault tolerance — any active job resumes after restart.
            active_states = [
                PipelineStatus.JD_DRAFT.value,
                PipelineStatus.JD_APPROVAL_PENDING.value,
                PipelineStatus.JD_APPROVED.value,
                PipelineStatus.JOB_POSTED.value,
                PipelineStatus.WAITING_FOR_APPLICATIONS.value,
                PipelineStatus.SCREENING.value,
                PipelineStatus.HR_REVIEW_PENDING.value,
                PipelineStatus.INTERVIEW_SCHEDULED.value,
            ]
            result = await session.execute(
                select(Job).where(Job.pipeline_state.in_(active_states))
            )
            jobs = result.scalars().all()
            for job in jobs:
                thread_id = f"job-{job.id}"
                config = {"configurable": {"thread_id": thread_id}}
                try:
                    state = await pipeline.aget_state(config)
                    
                    if not state or not state.values:
                        logger.warning(f"⚠️  No checkpoint found for thread {thread_id} — skipping resume")
                        continue

                    # If there is a next task, check if it's waiting on an interrupt
                    if state.next:
                        is_interrupted = any(
                            getattr(task, "interrupts", None)
                            for task in state.tasks
                        )
                        if not is_interrupted:
                            logger.info(f"🔄 Auto-resuming orphaned LangGraph thread: {thread_id} (next={state.next})")
                            async def _safe_resume(p=pipeline, c=config, tid=thread_id):
                                try:
                                    await p.ainvoke(None, c)
                                    logger.success(f"✅ Resumed thread {tid} successfully")
                                except Exception as e:
                                    logger.error(f"❌ Failed to resume thread {tid}: {e}")
                            asyncio.create_task(_safe_resume())
                        else:
                            logger.info(f"⏸  Thread {thread_id} is paused at interrupt — waiting for human input")
                    else:
                        logger.info(f"✅ Thread {thread_id} has no pending work (state={job.pipeline_state})")
                except Exception as e:
                    logger.error(f"❌ Error checking state for thread {thread_id}: {e}")
                        
    # Run in background to avoid blocking Uvicorn startup
    asyncio.create_task(resume_jobs())



# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class JobStageRequest(BaseModel):
    stage_name:         str
    stage_order:        int
    interviewer_id:     Optional[uuid.UUID] = None
    stage_instructions: Optional[str] = None

class NewJobRequest(BaseModel):
    title:                  str = Field(..., alias="job_title")
    stages:                 List[JobStageRequest] = Field(..., alias="hiring_workflow")
    
    # Optional fields with defaults to support simplified title/stages request
    department:             str = "Engineering"
    hiring_manager_name:    str = "Admin"
    hiring_manager_email:   Optional[str] = None
    location:               str = "Remote"
    experience_required:    str = "Not Specified"
    employment_type:        str = "Full-time"
    joining_requirement:    str = "Immediate"
    required_skills:        List[str] = []
    preferred_skills:       List[str] = []
    screening_questions:    List[dict] = []
    technical_test_type:    Optional[str] = None
    technical_test_link:    Optional[str] = None
    technical_test_mcq:     List[dict] = []
    scoring_weights:        dict = {"semantic": 0.4, "llm": 0.3, "screening": 0.2, "test": 0.1}
    salary_range:           Optional[str] = "Competitive"
    interviewer_email:      Optional[str] = None
    template_type:          str = "startup"
    
    @field_validator('template_type')
    @classmethod
    def validate_template_type(cls, v: str) -> str:
        if v not in JD_TEMPLATES:
            return "startup"
        return v

    model_config = ConfigDict(populate_by_name=True)

class JDApprovalRequest(BaseModel):
    approved:  bool
    feedback:  Optional[str] = ""

class CandidateSelectionRequest(BaseModel):
    candidate_ids: List[str]

class DecisionRequest(BaseModel):
    candidate_id: str
    decision: str  # "approve" | "reject"

class FeedbackRequest(BaseModel):
    candidate_id: uuid.UUID
    stage_id: uuid.UUID
    decision: str  # "strong_yes", "yes", "no", "strong_no"
    rating: int    # 1-5
    feedback_text: str


class FinalDecisionRequest(BaseModel):
    selected_ids: List[str]   # empty list = all rejected

class SuggestionRequest(BaseModel):
    job_title: str
    skills: List[str]

class SuggestionResponse(BaseModel):
    suggested_skills: List[str]
    suggested_screening_questions: List[str]
    suggested_interview_questions: List[str]

class InsightRequest(BaseModel):
    job_title: str
    location: str
    experience: str
    salary: str

class InsightResponse(BaseModel):
    estimated_volume: str
    expected_quality: str
    recommendation: str

class JobStatusResponse(BaseModel):
    job_id:             str
    pipeline_status:    str
    status:             str    # [NEW] ACTION_REQUIRED | PROCESSING | INTERVIEW_SCHEDULED
    jd_revision_count:  int
    repost_attempts:    int
    applications_count: int
    shortlist_count:    int
    meeting_links:      List[dict] = []   # [{candidate_id, meet_link, event_id}]

class SignupRequest(BaseModel):
    company_name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class VerifyEmailRequest(BaseModel):
    email: str
    otp: str

class ResendOtpRequest(BaseModel):
    email: str

class RejectionEmailRequest(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID

class BulkRejectionEmailRequest(BaseModel):
    candidate_ids: List[uuid.UUID]
    job_id: uuid.UUID

class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "interviewer"]

class AcceptInviteRequest(BaseModel):
    token: str
    name: str
    password: str

class AIChatRequest(BaseModel):
    job_title: str
    skills: List[str] = []
    message: str

class AIChatResponse(BaseModel):
    reply: str

class CandidateCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[str] = None

class ApplicationCreate(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: str = "shortlisted"
    stage: str = "SHORTLISTING"

class ApplicationSimpleResponse(BaseModel):
    application_id: uuid.UUID
    message: str

class CandidateIdResponse(BaseModel):
    candidate_id: uuid.UUID

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[str] = None

class ApplicationFlatResponse(BaseModel):
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_email: str
    job_id: uuid.UUID
    job_title: str
    status: str
    stage: str
    score: Optional[float] = None
    updated_at: datetime

class CandidateResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str]
    resume_url: Optional[str]
    skills: Optional[List[str]]
    experience: Optional[str]
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ApplicationEvaluationRequest(BaseModel):
    rating: float
    notes: str
    decision: str # select | reject

class InterviewCreate(BaseModel):
    candidate_id: uuid.UUID
    application_id: Optional[uuid.UUID] = None
    interviewer_id: uuid.UUID
    scheduled_time: datetime
    meeting_link: Optional[str] = None

class InterviewResponse(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    application_id: Optional[uuid.UUID]
    interviewer_id: uuid.UUID
    scheduled_time: datetime
    meeting_link: Optional[str]
    status: str
    created_at: datetime
    
    candidate_name: Optional[str] = None
    job_title: Optional[str] = None
    interviewer_name: Optional[str] = None

    class Config:
        from_attributes = True

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/signup", summary="Register a new B2B company and admin user")
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    from src.utils.security import generate_otp, hash_otp, hash_password, OTP_EXPIRY_MINUTES
    from src.utils.email_utils import send_otp_email
    from datetime import datetime, timedelta, timezone
    
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # 1. Create Organization
    new_org = Organization(name=req.company_name)
    db.add(new_org)
    await db.flush()  # To generate new_org.id
    
    # Generate OTP
    plain_otp = generate_otp()
    hashed_otp = hash_otp(plain_otp)
    
    # 2. Create User linked to Organization
    new_user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        name=req.email.split("@")[0],
        organization_id=new_org.id,
        role="admin",
        is_email_verified=False,
        email_verification_otp_hash=hashed_otp,
        email_verification_expires=datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )
    db.add(new_user)
    await db.commit()
    
    # 3. Send the OTP Email (Wrap in try/except for absolute safety in dev)
    try:
        # ── Step 9: Pure Dispatch ──
        email_config = build_email_config(settings)

        await send_otp_email(
            req.email, 
            plain_otp,
            config=email_config
        )
    except Exception as e:
        logger.warning(f"⚠️ Signup continued but email failed: {e}")
    
    return {
        "message": "OTP sent to your email"
    }

@app.post("/verify-email", summary="Verify OTP and activate user account")
async def verify_email(req: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    from src.utils.security import verify_otp
    from datetime import datetime, timezone

    # 1. Fetch user
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")

    # 2. Check expiry
    if not user.email_verification_expires or datetime.now(timezone.utc) > user.email_verification_expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    if (user.email_verification_attempts or 0) >= 5:
        raise HTTPException(status_code=403, detail="Account locked due to too many invalid attempts. Please request a new OTP.")

    # 3. Verify OTP
    if not user.email_verification_otp_hash or not verify_otp(req.otp, user.email_verification_otp_hash):
        user.email_verification_attempts = (user.email_verification_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # 4. Success -> Activate user
    user.is_email_verified = True
    user.email_verification_otp_hash = None
    user.email_verification_expires = None
    user.email_verification_attempts = 0
    await db.commit()

    # 5. Generate JWT token
    token = create_token({
        "user_id": str(user.id),
        "organization_id": str(user.organization_id),
        "role": user.role,
        "email": user.email,
        "name": user.name
    })

    return {
        "access_token": token,
        "user_id": str(user.id),
        "role": user.role,
        "message": "Email verified"
    }

@app.post("/resend-otp", summary="Resend verification OTP")
async def resend_otp(req: ResendOtpRequest, db: AsyncSession = Depends(get_db)):
    from src.utils.security import generate_otp, hash_otp, OTP_EXPIRY_MINUTES
    from src.utils.email_utils import send_otp_email
    from datetime import datetime, timedelta, timezone

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")

    if user.email_verification_expires:
        last_sent = user.email_verification_expires - timedelta(minutes=OTP_EXPIRY_MINUTES)
        seconds_since_last = (datetime.now(timezone.utc) - last_sent).total_seconds()
        
        if seconds_since_last < 60:
            raise HTTPException(status_code=429, detail="Please wait 60 seconds before requesting a new OTP.")

    # Generate new
    plain_otp = generate_otp()
    user.email_verification_otp_hash = hash_otp(plain_otp)
    user.email_verification_expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    user.email_verification_attempts = 0
    await db.commit()

    # Send
    # ── Step 9: Pure Dispatch ──
    email_config = build_email_config(settings)

    await send_otp_email(
        req.email, 
        plain_otp,
        config=email_config
    )

    return {"message": "New OTP sent to your email"}

@app.post("/login", summary="Login to B2B SaaS platform")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    from src.utils.security import verify_password
    # 1. Find user by email
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    
    if not user:
        print(f"DEBUG: Login failed - user not found: {req.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # 2. Verify password — guard against NULL hashed_password (e.g. OAuth-only or corrupted accounts)
    if not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    # Check if email is verified
    if not user.is_email_verified:
        raise HTTPException(status_code=403, detail={"message": "Please verify your email", "error": "email_not_verified"})

        
    # 3. Generate token with required payloads
    print("LOGIN DEBUG →", user.email, user.role)
    token = create_token({
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "organization_id": str(user.organization_id)
    })
    
    return {
        "access_token": token,
        "email": user.email,
        "role": user.role
    }


@app.post("/invite-user", summary="Admin: Invite a team member")
async def invite_team_member(
    req: InviteRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # Validate role value
    allowed_roles = ["admin", "interviewer"]
    if req.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {allowed_roles}")

    # 2. Verify organization exists
    # Explicitly coerce to UUID for lookup
    org_id_uuid = current_user.organization_id
    org_result = await db.execute(select(Organization).where(Organization.id == org_id_uuid))
    org = org_result.scalars().first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # 3. Check if email already registered
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    # 4. Delete any existing pending invite for this email — allows HR to re-send
    existing_invite_res = await db.execute(
        select(Invite).where(
            Invite.email == req.email,
            Invite.organization_id == current_user.organization_id,
            Invite.status == "pending"
        )
    )
    existing_invite = existing_invite_res.scalars().first()
    if existing_invite:
        await db.delete(existing_invite)
        await db.flush()
        logger.info(f"♻️  Deleted old pending invite for {req.email} — issuing fresh token.")

    # 5. Generate a cryptographically secure unique token
    token = secrets.token_urlsafe(32)

    # 6. Create invite record in DB with 24-hour expiry
    invite = Invite(
        email=req.email,
        organization_id=current_user.organization_id,
        role=req.role,
        token=token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(invite)
    await db.commit()

    # 7. Send invite email (HTML)
    invite_link = f"{settings.frontend_url}/accept-invite/{token}"
    role_label  = req.role.replace('_', ' ').title()
    email_html  = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;">
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e3a8a 0%,#3b82f6 100%);padding:40px 32px;text-align:center;">
      <div style="display:inline-block;background:rgba(255,255,255,0.15);padding:6px 14px;border-radius:8px;color:#ffffff;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:16px;">
        🤖 Hiring.AI Platform
      </div>
      <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:800;letter-spacing:-0.025em;">You've been invited!</h1>
      <p style="margin:8px 0 0;color:#dbeafe;font-size:15px;">{org.name} wants you to join their hiring team</p>
    </div>
    <!-- Body -->
    <div style="padding:36px 32px;">
      <p style="margin:0 0 20px;color:#374151;font-size:16px;line-height:1.6;">
        Hi there! You've been added to <strong>{org.name}</strong> on the Hiring.AI platform as a <strong>{role_label}</strong>.
      </p>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:20px 24px;margin-bottom:28px;">
        <p style="margin:0;color:#1e40af;font-size:14px;"><strong>Role assigned:</strong> {role_label}</p>
        <p style="margin:6px 0 0;color:#1e40af;font-size:14px;"><strong>Organization:</strong> {org.name}</p>
      </div>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.5;">
        Click the button below to accept your invite and set up your account. This link expires in <strong>24 hours</strong>.
      </p>
      <div style="text-align:center;margin-bottom:32px;">
        <a href="{invite_link}" style="background:#2563eb;color:#ffffff;padding:14px 32px;text-decoration:none;border-radius:10px;font-size:15px;font-weight:700;display:inline-block;letter-spacing:-0.01em;">
          Accept Invitation →
        </a>
      </div>
      <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center;">
        If the button doesn't work, paste this link into your browser:<br/>
        <a href="{invite_link}" style="color:#3b82f6;word-break:break-all;">{invite_link}</a>
      </p>
    </div>
    <!-- Footer -->
    <div style="padding:24px 32px;border-top:1px solid #e5e5eb;text-align:center;">
      <p style="margin:0;color:#9ca3af;font-size:12px;">© 2024 Hiring.AI Platform. Powered by Advanced Agentic Intelligence.</p>
    </div>
  </div>
</body>
</html>"""

    await send_email(
        to=req.email,
        subject=f"You're invited to join {org.name} on Hiring.AI",
        body=email_html,
        html=True
    )

    return {
        "message": "Invite sent successfully",
        "invite_link": invite_link,
        "expires_in": "24 hours"
    }


@app.post("/accept-invite", summary="Accept a team invite and create account")
async def accept_invite(req: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    # 1. Find invite by token
    result = await db.execute(select(Invite).where(Invite.token == req.token))
    invite = result.scalars().first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invite token")

    # 2. Check status is still pending
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is already {invite.status}")

    # 3. Check not expired
    if datetime.utcnow() > invite.expires_at.replace(tzinfo=None):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(status_code=400, detail="Invite link has expired")

    # 4. Check if email already registered
    existing = await db.execute(select(User).where(User.email == invite.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    # 5. Create the new user
    new_user = User(
        email=invite.email,
        name=req.name,
        hashed_password=hash_password(req.password),
        organization_id=invite.organization_id,
        role=invite.role,
        is_email_verified=True
    )
    db.add(new_user)

    # 6. Mark invite as accepted
    invite.status = "accepted"
    await db.commit()
    
    # 7. Generate login token
    access_token = create_token({
        "user_id": str(new_user.id),
        "email": new_user.email,
        "role": new_user.role,
        "organization_id": str(new_user.organization_id)
    })

    return {
        "access_token": access_token,
        "email": new_user.email,
        "role": new_user.role
    }




@app.post("/suggest", summary="AI Suggestions for Job Configuration", response_model=SuggestionResponse)
async def suggest_requirements(req: SuggestionRequest):
    """
    Generates AI suggestions for skills, screening questions, and interview questions
    based on the job title and currently selected skills.
    """
    llm = get_llm(temperature=0.7, prioritize_local=True)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert technical recruiter and hiring manager. Given a job title and a list of skills the user has already entered, provide suggestions to enhance the job requirements. Provide 5-8 suggested skills, 3-5 screening questions, and 3-5 technical interview questions.\n\nReturn EXACTLY a JSON object with this structure and NO extra text or markdown:\n{{\n  \"suggested_skills\": [\"skill1\"],\n  \"suggested_screening_questions\": [\"q1\"],\n  \"suggested_interview_questions\": [\"q2\"]\n}}"),
        ("human", "Job Title: {job_title}\nAlready Entered Skills: {skills}")
    ])
    
    chain = prompt | llm
    
    try:
        skills_str = ", ".join(req.skills) if req.skills else "None"
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        response = chain.invoke({
            "job_title": req.job_title, 
            "skills": skills_str
        }, config={"callbacks": []})
        
        # Robust JSON extraction
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1]
        if content.startswith("```"):
            content = content.split("```")[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
            
        data = json.loads(content.strip())
        return SuggestionResponse(**data)
        
    except Exception as e:
        logger.error(f"Failed to generate suggestions: {e}")
        # Fallback to empty lists on failure to prevent UI crash
        return SuggestionResponse(
            suggested_skills=["Communication", "Teamwork"],
            suggested_screening_questions=["What is your notice period?"],
            suggested_interview_questions=["Take me through your most complex project."]
        )

@app.post("/jobs/ai-chat", summary="Conversational AI Assistant for Job Creation", response_model=AIChatResponse)
async def ai_chat_assistant(req: AIChatRequest):
    """
    Answers user questions dynamically during job creation based on the current form state (job title, skills).
    """
    llm = get_llm(temperature=0.7, prioritize_local=True)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert technical recruiter and HR assistant. You help the user create a job pipeline and job description. "
                   "CRITICAL INSTRUCTION: Your answers must be HYPER CONCISE and immediately copy-pasteable by the user into their form. "
                   "DO NOT give general career advice or long explanations. If they ask for skills, give a simple comma-separated list. "
                   "If they ask for questions, give 2-3 exact questions. NEVER start with 'Here are some...' or wrap it in conversational pleasantries."),
        ("human", "Current Job Title: {job_title}\\nCurrent Skills: {skills}\\n\\nUser Question: {message}")
    ])
    
    chain = prompt | llm
    
    try:
        skills_str = ", ".join(req.skills) if req.skills else "None"
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        response = chain.invoke({
            "job_title": req.job_title, 
            "skills": skills_str,
            "message": req.message
        }, config={"callbacks": []})
        
        return AIChatResponse(reply=response.content.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Chat failed: {str(e)}")

@app.post("/insights", summary="AI Hiring Insights", response_model=InsightResponse)
async def generate_insights(req: InsightRequest):
    """
    Generates AI hiring insights: estimated volume, quality, and a recommendation based on job config.
    """
    llm = get_llm(temperature=0.7, prioritize_local=True)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert technical recruiter and talent market analyst. Given the job details, provide insights on estimated applicant volume (Low, Medium, High), expected candidate quality (Low, Medium, High), and a 1-sentence actionable recommendation to improve hiring success (e.g. 'Increase salary range to attract senior engineers').\n\nReturn EXACTLY a JSON object with this structure and NO extra text or markdown:\n{{\n  \"estimated_volume\": \"High\",\n  \"expected_quality\": \"Medium\",\n  \"recommendation\": \"Your insight here.\"\n}}"),
        ("human", "Job Title: {job_title}\nLocation: {location}\nExperience: {experience}\nSalary: {salary}")
    ])
    
    chain = prompt | llm
    
    try:
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        response = chain.invoke({
            "job_title": req.job_title,
            "location": req.location,
            "experience": req.experience,
            "salary": req.salary
        }, config={"callbacks": []})
        
        # Robust JSON extraction
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1]
        if content.startswith("```"):
            content = content.split("```")[1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
            
        data = json.loads(content.strip())
        return InsightResponse(**data)
        
    except Exception as e:
        logger.error(f"Failed to generate insights: {e}")
        return InsightResponse(
            estimated_volume="Medium",
            expected_quality="Medium",
            recommendation="Consider adjusting requirements if application volume is low."
        )


@app.get("/jd-templates", summary="Retrieve available JD Generation Style Templates")
async def list_jd_templates(current_user: User = Depends(get_current_user)):
    """Return all available JD styles dynamically from the configuration block."""
    templates = []
    for key, val in JD_TEMPLATES.items():
        templates.append({
            "key": key,
            "name": val.get("name", "Unknown"),
            "description": val.get("description", "")
        })
    return templates


@app.post("/jobs", summary="Submit new hiring request (admin only)")
async def create_job(
    req: NewJobRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Submit new hiring request (admin only).
    Phase 15 & Request: Enforce backpressure control.
    """
    # ── Backpressure Check ────────────────────────────────────
    running_count_stmt = select(func.count(Job.id)).where(Job.status_field == "PROCESSING")
    running_count_res = await db.execute(running_count_stmt)
    running_count = running_count_res.scalar() or 0
    
    if running_count >= settings.max_running_jobs:
        logger.warning("🚨 [Backpressure] System at capacity: {}/{} jobs running", running_count, settings.max_running_jobs)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"System overload: Maximum concurrent jobs ({settings.max_running_jobs}) reached. Please try again later."
        )

    """
    HR submits a hiring request.
    Creates a new LangGraph thread and starts the pipeline.
    Returns job_id and thread_id for future interactions.
    """
    job_id    = str(uuid.uuid4())
    thread_id = f"job-{job_id}"

    # ── [NEW] Refined Hiring Manager & Interviewer Resolution ────────────────
    user_email = current_user.email
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User email missing from session.")

    hm_email = (
        req.hiring_manager_email
        if req.hiring_manager_email and req.hiring_manager_email != "admin@hiring.ai"
        else user_email
    )

    int_email = (
        req.interviewer_email
        if req.interviewer_email
        else user_email
    )

    logger.info({
        "event": "jd_email_prepare",
        "user_email": user_email,
        "hiring_manager_email": hm_email
    })

    # Phase 15 & Request: Generate Trace ID for the root of this pipeline
    trace_id = generate_trace_id()
    set_trace_id(trace_id)
    
    initial_state: HiringState = {
        "job_id":                job_id,
        "trace_id":              trace_id,
        "organization_id":       current_user.organization_id,

        "graph_thread_id":       thread_id,
        "job_title":             req.title,
        "template_type":         req.template_type,
        "department":            req.department,
        "hiring_manager_name":   req.hiring_manager_name,
        "hiring_manager_email":  hm_email,
        "interviewer_email":     int_email,
        "location":              req.location,
        "experience_required":   req.experience_required,
        "employment_type":       req.employment_type,
        "joining_requirement":   req.joining_requirement,
        "required_skills":       req.required_skills,
        "preferred_skills":      req.preferred_skills,
        "screening_questions":   req.screening_questions,
        "technical_test_type":   req.technical_test_type,
        "technical_test_link":   req.technical_test_link,
        "technical_test_mcq":    req.technical_test_mcq,
        "hiring_workflow":       [stage.model_dump() for stage in req.stages],
        "scoring_weights":       req.scoring_weights,
        "salary_range":          req.salary_range or "Competitive",
        "jd_revision_count":     0,
        "repost_attempts":       0,
        "applications":          [],
        "scored_resumes":        [],
        "hr_selected_candidates": [],
        "interview_slots":        [],
        "notifications_sent":     False,
        "pipeline_status":        PipelineStatus.JD_DRAFT.value,
        "current_stage":         "jd_review",
        "error_log":             [],
    }

    # ═══════════════════════════════════════════════════════════════════════════
    # PERSIST TO RELATIONAL DATABASE (SQLAlchemy)
    # ═══════════════════════════════════════════════════════════════════════════
    async with AsyncSessionLocal() as session:
        try:
            new_job = Job(
                id=job_id,
                graph_thread_id=thread_id,
                title=req.title,
                department=req.department,
                hiring_manager_name=req.hiring_manager_name,
                hiring_manager_email=hm_email,
                pipeline_state=PipelineState.JD_DRAFT,
                location=req.location,
                experience_required=req.experience_required,
                employment_type=req.employment_type,
                joining_requirement=req.joining_requirement,
                required_skills=req.required_skills,
                preferred_skills=req.preferred_skills,
                technical_test_type=req.technical_test_type,
                technical_test_link=req.technical_test_link,
                technical_test_mcq=req.technical_test_mcq,
                hiring_workflow=[stage.model_dump() for stage in req.stages],
                scoring_weights=req.scoring_weights,
                template_type=req.template_type,
                jd_draft="🤖 AI is drafting your Job Description... (this usually takes 10-30 seconds)",
                organization_id=current_user.organization_id
            )
            session.add(new_job)

            # Insert Job Stages
            order = 1
            for stage in req.stages:
                job_stage = JobStage(
                    job_id=job_id,
                    stage_name=stage.stage_name,
                    stage_order=order,
                    interviewer_id=stage.interviewer_id
                )
                session.add(job_stage)
                order += 1
                
                # 💡 [WEBSOCKET] Push real-time assignment to interviewer
                if stage.interviewer_id:
                     await manager.broadcast_to_user(str(stage.interviewer_id), {"type": "REFRESH_TASKS", "job_id": job_id})

            # Insert Advanced Screening Questions
            for q_data in req.screening_questions:
                sq = ScreeningQuestion(
                    job_id=job_id,
                    question=q_data.get("question", ""),
                    question_type=q_data.get("type", "text"),
                    is_required=q_data.get("required", True),
                    options=None  # Can be expanded later for MCQ screening questions
                )
                session.add(sq)
                
            # Insert Technical Test (MCQ)
            if req.technical_test_type == "mcq" and req.technical_test_mcq:
                test_id = uuid.uuid4()
                new_test = Test(
                    id=test_id,
                    job_id=job_id,
                    type="mcq"
                )
                session.add(new_test)
                
                for mcq_data in req.technical_test_mcq:
                    tq = TestQuestion(
                        test_id=test_id,
                        question=mcq_data.get("question", ""),
                        options=mcq_data.get("options", []),
                        correct_index=mcq_data.get("correct_index", 0)
                    )
                    session.add(tq)

            await session.commit()
            logger.info(f"✅ Saved Job {job_id}, Screening Questions, and Tests to DB.")
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Failed to save Job {job_id} to DB: {e}")
            raise HTTPException(status_code=500, detail="Database insertion failed")


    pipeline = await get_pipeline()
    config   = {"configurable": {"thread_id": thread_id}}

    logger.info("🚀 Starting pipeline in background for job_id={}", job_id)

    # Invoke pipeline asynchronously so the HTTP request returns instantly
    # even if AI fallback generation takes 60 seconds
    # [NEW] Explicit config to avoid 'get_config' outside runnable context
    background_tasks.add_task(pipeline.ainvoke, initial_state, config={**config, "callbacks": []})

    return {
        "job_id":    job_id,
        "thread_id": thread_id,
        "message":   "Pipeline started. JD is being generated and will be sent for HR review.",
    }


@app.get("/jobs", summary="List all jobs for the organization")
async def list_jobs(
    status: Optional[str] = "active",
    current_user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Fetch all jobs belonging to the current user's organization."""
    org_id = current_user.organization_id
    
    stmt = (
        select(Job)
        .options(selectinload(Job.applications))
        .where(Job.organization_id == org_id)
        .where(Job.is_cancelled == False)
    )

    if status == "active":
        # Include ALL non-terminal processing states so they appear on the dashboard
        active_states = [
            "JD_DRAFT", "JD_APPROVAL_PENDING", "JD_APPROVED", 
            "JOB_POSTED", "WAITING_FOR_APPLICATIONS", "SCREENING", 
            "HR_REVIEW_PENDING", "INTERVIEW_SCHEDULED"
        ]
        stmt = stmt.where(Job.pipeline_state.in_(active_states))
    elif status:
        # Fallback for other potential filters (draft, processing, etc.)
        pass

    result = await db.execute(stmt.order_by(Job.created_at.desc()))
    jobs = result.scalars().all()
    
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "department": j.department,
            "company": getattr(settings, 'company_name', "Hiring AI"),
            "location": j.location,
            "job_type": j.employment_type,
            "salary": j.salary_range,
            "summary": j.summary,
            "template_type": j.template_type or "startup",
            "status": j.status,
            "pipeline_state": j.pipeline_state.value if j.pipeline_state else "JD_DRAFT",
            "is_cancelled": j.is_cancelled or False,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "applicants_count": len(j.applications),
            "shortlist_count": len([a for a in j.applications if a.is_shortlisted]),
            "interviews_count": len([a for a in j.applications if a.interview_slot is not None])
        }
        for j in jobs
    ]


@app.get("/pipeline-board", summary="Get candidates bucketed by pipeline stage for Kanban board")
async def get_pipeline_board(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Returns candidates across all jobs grouped into 4 pipeline stages:
    - screening:  applied, not yet shortlisted
    - hr_review:  shortlisted, HR hasn't decided yet
    - interview:  interview slot scheduled
    - final:      offer sent or rejected
    """
    org_id = current_user.organization_id
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.applications).selectinload(Application.candidate))
        .where(Job.organization_id == org_id)
    )
    jobs = result.scalars().all()

    stages = {"screening": [], "hr_review": [], "interview": [], "final": []}

    for job in jobs:
        for app in job.applications:
            c = app.candidate
            card = {
                "application_id": str(app.id),
                "candidate_id": str(c.id) if c else None,
                "name": c.name if c else "Unknown",
                "email": c.email if c else None,
                "job_id": str(job.id),
                "job_title": job.title,
                "ai_score": round(app.score) if app.score is not None else None,
                "is_shortlisted": app.is_shortlisted,
                "hr_selected": app.hr_selected,
                "has_interview": app.interview_slot is not None,
                "meeting_link": app.meeting_link,
                "offer_sent": app.offer_sent,
                "rejected": app.rejected,
            }

            if app.offer_sent or app.rejected:
                stages["final"].append(card)
            elif app.interview_slot is not None:
                stages["interview"].append(card)
            elif app.is_shortlisted:
                stages["hr_review"].append(card)
            else:
                stages["screening"].append(card)

    return stages


@app.get("/activity-feed", summary="Get recent hiring activity from the real-time feed table")
async def get_activity_feed(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Returns the latest 30 real-time events from the activities table for this organization.
    """
    org_id = current_user.organization_id
    
    # Query Activity joined with Job for job_title
    result = await db.execute(
        select(Activity, Job.title)
        .join(Job, Activity.job_id == Job.id)
        .where(Activity.organization_id == org_id)
        .order_by(Activity.created_at.desc())
        .limit(30)
    )
    rows = result.all()
    
    events = []
    for activity, job_title in rows:
        events.append({
            "type": activity.type,
            "icon": activity.type,
            "title": activity.message,
            "description": f"Pipeline action for {job_title}",
            "timestamp": activity.created_at.isoformat() if activity.created_at else None,
            "job_id": str(activity.job_id),
            "job_title": job_title,
            "candidate_name": "System",
        })
        
    return events


@app.get("/jobs/{job_id}", summary="Get specific job details")
async def get_job(job_id: str, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Fetch complete details of a specific job, including applications."""
    org_id = current_user.organization_id
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.applications).selectinload(Application.candidate))
        .where(Job.id == job_id, Job.organization_id == org_id)
    )
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
        
    return {
        "id": str(job.id),
        "title": job.title,
        "department": job.department,
        "company": getattr(settings, 'company_name', 'Hiring AI'),
        "location": job.location,
        "experience_required": job.experience_required,
        "salary_range": job.salary_range,
        "required_skills": job.required_skills,
        "status": job.status_field or job.status,
        "current_stage": job.current_stage,
        "pipeline_state": job.pipeline_state.value if job.pipeline_state else "JD_DRAFT",
        "is_cancelled": job.is_cancelled or False,
        "jd_draft": job.jd_draft,
        "summary": job.summary,
        "full_jd": job.full_jd,
        "template_type": job.template_type or "startup",
        "technical_test_mcq": job.technical_test_mcq,
        "hiring_workflow": job.hiring_workflow,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "applications": [
            {
                "id": str(a.id),
                "status": getattr(a, 'stage', 'screening') or ("shortlisted" if getattr(a, 'is_shortlisted', False) else "screening"),
                "stage": getattr(a, 'stage', 'screening'),
                "is_shortlisted": getattr(a, 'is_shortlisted', False),
                "score": getattr(a, 'score', None),
                "candidate_name": a.candidate.name if a.candidate else "Unknown Candidate",
                "candidate_email": a.candidate.email if a.candidate else "N/A"
            }
            for a in job.applications
        ]
    }


@app.post("/jobs/{job_id}/cancel", summary="Cancel an active pipeline to save AI costs")
async def cancel_job(job_id: str, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Instantly terminate a hiring pipeline."""
    org_id = current_user.organization_id
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.organization_id == org_id)
    )
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
        
    # 1. Mark as cancelled — preserve pipeline_state so the frontend knows WHERE it stopped
    job.is_cancelled = True
    await db.commit()
    
    # 2. Update LangGraph State to stop auto-resumes or routing
    try:
        pipeline = await get_pipeline()
        config = {"configurable": {"thread_id": f"job-{job_id}"}}
        await pipeline.aupdate_state(config, {"pipeline_status": PipelineStatus.CLOSED.value})
        logger.info(f"🚫 Pipeline {job_id} cancelled by HR at stage: {job.pipeline_state.value}")
    except Exception as e:
        logger.warning(f"Could not update LangGraph state for {job_id} (might not be initialized): {e}")
        
    return {"message": "Pipeline cancelled successfully", "status": job.status}


@app.post("/jobs/{job_id}/resume", summary="Resume a cancelled AI pipeline")
async def resume_job(job_id: str, background_tasks: BackgroundTasks, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Wakes up the LangGraph checkpointer and resumes from exactly where it was cancelled."""
    org_id = current_user.organization_id
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.organization_id == org_id)
    )
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
        
    if not job.is_cancelled:
        return {"message": "Job is already active"}

    # 1. Clear cancelled flag in DB
    job.is_cancelled = False
    await db.commit()
    
    # 2. Update LangGraph State to restore routing logic
    try:
        pipeline = await get_pipeline()
        config = {"configurable": {"thread_id": f"job-{job_id}"}}
        
        # We must overwrite the 'CLOSED' status injected during cancellation back to its real state
        await pipeline.aupdate_state(config, {"pipeline_status": job.pipeline_state.value})
        
        logger.info(f"▶️ Pipeline {job_id} RESUMED by HR at stage: {job.pipeline_state.value}")
        
        # 3. Fire the graph execution exactly from its paused state using None
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        background_tasks.add_task(pipeline.ainvoke, None, config={**config, "callbacks": []})
        
    except Exception as e:
        logger.error(f"❌ Failed to resume LangGraph state for {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume pipeline engine")
        
    return {"message": "Pipeline resumed successfully", "status": job.status}


@app.delete("/jobs/{job_id}", summary="Permanently delete a cancelled job")
async def delete_job(job_id: str, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Permanently removes a job and all its data.
    Only allowed if the job has is_cancelled=True (safety guard to prevent
    accidental deletion of active pipelines).
    """
    org_id = current_user.organization_id
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.organization_id == org_id)
    )
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")

    if not job.is_cancelled:
        raise HTTPException(
            status_code=400,
            detail="Only cancelled jobs can be deleted. Cancel the pipeline first."
        )

    await db.delete(job)
    await db.commit()
    logger.info(f"🗑️  Job {job_id} ({job.title}) permanently deleted by user {current_user.email}")
    return {"message": f"Job '{job.title}' permanently deleted."}

@app.api_route("/jobs/{job_id}/approve-jd", methods=["GET", "POST"], summary="HR approves or rejects the generated JD (Decision 1)")
async def approve_jd(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    req: Optional[JDApprovalRequest] = None,
    current_user: User | None = Depends(get_current_user_optional)
):
    """
    Resumes the LangGraph pipeline paused at the review_jd interrupt.
    - approved=True  → pipeline proceeds to publish_jd
    - approved=False → pipeline loops back to generate_jd with feedback
    """
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    # If it's a GET request (from email click), pull from query params
    if request.method == "GET":
        approved_val = request.query_params.get("approved", "false").lower() == "true"
        feedback_val = request.query_params.get("feedback", "")
    else:
        # POST request from curl/tool
        if not req:
            raise HTTPException(status_code=400, detail="Missing request body")
        approved_val = req.approved
        feedback_val = req.feedback or ""
    # Phase 15: Interaction Trace
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    resume_value = {
        "action_type": "jd_approve" if approved_val else "jd_reject",
        "job_id": job_id,
        "trace_id": trace_id,
        "organization_id": current_user.organization_id if current_user else None,
        "decision": "approve" if approved_val else "reject",
        "approved": approved_val,
        "feedback": feedback_val
    }


    logger.info("📬 [approve_jd] job_id={} approved={} (via {})", job_id, approved_val, request.method)

    # Fire pipeline resume in background — HTTP response returns instantly
    background_tasks.add_task(pipeline.ainvoke, Command(resume=resume_value), config)

    msg = "JD approved — pipeline proceeding to publish." if approved_val else "JD revision requested — AI will regenerate."
    
    if request.method == "GET":
        return HTMLResponse(content=f"""
        <html>
            <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f4f4f4;">
                <div style="background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">
                    <h1 style="color: {'#10b981' if approved_val else '#f59e0b'};">{'✅ Approved' if approved_val else '🔄 Revision Requested'}</h1>
                    <p>{msg}</p>
                    <p style="color: #666; margin-top: 1rem;">You can close this tab now.</p>
                </div>
            </body>
        </html>
        """)

    return {
        "job_id":  job_id,
        "approved": approved_val,
        "message": msg,
    }


@app.post("/jobs/{job_id}/resume-screening", summary="Manually trigger application collection (Bypass 7-day wait)")
async def resume_screening(job_id: str, current_user: User = Depends(require_admin)):
    """
    Resumes the LangGraph pipeline from the WAITING_FOR_APPLICATIONS interrupt.
    This bypasses the standard 7-day Celery wait for testing/demo purposes.
    """
    thread_id = f"job-{job_id}"
    
    # Phase 15: Interaction Trace
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [resume_screening] Manually triggering collection for job_id={}", job_id)


    # Resume the LangGraph pipeline paused at waiting_for_applications
    # [NEW] Explicit config to avoid 'get_config' outside runnable context
    await pipeline.ainvoke(
        Command(resume={
            "job_id": job_id,
            "trace_id": trace_id,
            "action_type": "scheduler_event",
            "decision": "resume_collection",
            "event": "manual_bypass"
        }),

        config={**config, "callbacks": []},
    )

    return {
        "job_id":  job_id,
        "message": "Screening triggered. System is now collecting resumes and scoring.",
    }


@app.post("/jobs/{job_id}/select-candidates", summary="HR selects candidates for interview (Decision 3)")
async def select_candidates(job_id: str, req: CandidateSelectionRequest, current_user: User | None = Depends(get_current_user_optional)):
    """
    Resumes the LangGraph pipeline after the 2-day shortlist review window.
    Selected candidate_ids proceed to interview scheduling.
    Empty list → pipeline closes.
    """
    logger.info("📬 [POST/select_candidates] Start for job_id={}", job_id)
    thread_id = f"job-{job_id}"
    
    # Phase 15: Interaction Trace
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}


    if req.candidate_ids:
        from sqlalchemy import select, and_
        async with AsyncSessionLocal() as session:
            # 1. Direct Job fetch and update
            job_stmt = select(Job).where(Job.id == uuid.UUID(job_id))
            job = (await session.execute(job_stmt)).scalar_one_or_none()
            
            if not job:
                logger.error("❌ [select_candidates] Job {} NOT FOUND", job_id)
                raise HTTPException(status_code=404, detail="Job not found")

            # 2. Validation
            valid_ids_res = await session.execute(
                select(Application.candidate_id).where(
                    and_(
                        Application.job_id == uuid.UUID(job_id),
                        Application.stage == "shortlisted"
                    )
                )
            )
            valid_ids = {str(row[0]).replace("-", "") for row in valid_ids_res.fetchall()}
            invalid_ids = [cid for cid in req.candidate_ids if cid.replace("-", "") not in valid_ids]
            
            if invalid_ids:
                logger.error("🛑 [select_candidates] Invalid candidates selected: {}", invalid_ids)
                # We will continue but log it, or strictly fail
                raise HTTPException(status_code=400, detail=f"Selection contains non-shortlisted candidates: {invalid_ids}")

            # 3. Update Status
            logger.info("🔄 [select_candidates] Updating job status to PROCESSING for UI")
            job.status_field = "PROCESSING"
            session.add(job)
            await session.commit()
            logger.success("✅ [select_candidates] DB status_field updated to PROCESSING")

    # 4. Resume Graph
    try:
        logger.info("⚡ [select_candidates] Resuming LangGraph thread: {}", thread_id)
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        await pipeline.ainvoke(
            Command(resume={
                "action_type": "candidate_select",
                "job_id": job_id,
                "trace_id": trace_id,
                "stage_id": "hr_review",
                "decision": "select",
                "candidate_ids": req.candidate_ids
            }),
            config={**config, "callbacks": []},
        )

        logger.success("🚀 [select_candidates] Graph resumption signal sent")
    except Exception as e:
        logger.error("❌ [select_candidates] Graph resumption failed: {}", e)
        # We don't raise here to avoid user seeing 500 if the UI update already worked
    
    return {
        "job_id": job_id,
        "selected_count": len(req.candidate_ids),
        "message": "Selection confirmed! Interviews are being scheduled." if req.candidate_ids
                   else "No selection made. Pipeline ending.",
    }


@app.get("/jobs/{job_id}/select-candidates", summary="HR selects candidates for interview via link (Decision 3)")
async def select_candidates_get(job_id: str, selected_ids: str = None, token: str = None, current_user: User | None = Depends(get_current_user_optional)):
    """
    GET version of select_candidates for easy clicking from emails.
    selected_ids: Comma-separated list of candidate UUIDs.
    """
    logger.info("📬 [GET/select_candidates] Click from email for job_id={} | ids={}", job_id, selected_ids)
    ids = selected_ids.split(",") if selected_ids else []
    req = CandidateSelectionRequest(candidate_ids=ids)
    res = await select_candidates(job_id, req, current_user)
    
    msg = res["message"]
    
    return HTMLResponse(content=f"""
    <html>
        <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f4f4f4;">
            <div style="background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">
                <h1 style="color: #10b981;">✅ Selection Received</h1>
                <p>{msg}</p>
                <p style="color: #666; margin-top: 1rem;">The pipeline has resumed. You can close this tab now.</p>
            </div>
        </body>
    </html>
    """)





@app.post("/submit-decision", summary="Interviewer submits a decision (approve/reject)")
async def submit_decision(req: DecisionRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Submits a decision for a candidate. Moves to next stage if approved, or rejects.
    """
    user_id = current_user.id
    
    # 1. Fetch Candidate and Current Stage
    stmt = (
        select(Candidate, JobStage)
        .join(JobStage, Candidate.current_stage_id == JobStage.id)
        .where(Candidate.id == req.candidate_id)
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found or not currently at an assigned stage.")
    
    cand, current_stage = row
    
    # Security: Ensure this interviewer is actually assigned to this stage
    if current_stage.interviewer_id != user_id:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="You are not assigned to this candidate's current stage.")

    # 2. Rule: Structured Feedback is REQUIRED before moving forward
    fb_stmt = (
        select(InterviewFeedback)
        .where(
            InterviewFeedback.candidate_id == req.candidate_id,
            InterviewFeedback.stage_id == current_stage.id
        )
    )
    fb_res = await db.execute(fb_stmt)
    if not fb_res.scalars().first():
        raise HTTPException(
            status_code=400, 
            detail=f"Structured feedback is required before submitting a decision for {cand.name}. Please use the Evaluation Form."
        )

    log_msg = f"Interviewer {current_user.name or 'Admin'} {req.decision}ed {cand.name} at stage: {current_stage.stage_name}"
    return await _process_candidate_decision(db, cand, current_stage, current_user, req.decision, log_msg)


@app.post("/submit-feedback", summary="Interviewer submits structured feedback and a decision")
async def submit_feedback(req: FeedbackRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Submits structured feedback for a candidate at a specific stage.
    """
    user_id = current_user.id
    
    # 1. Fetch Candidate and Stage
    stmt = (
        select(Candidate, JobStage)
        .join(JobStage, JobStage.id == req.stage_id)
        .options(joinedload(JobStage.job))
        .where(Candidate.id == req.candidate_id)
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Candidate or Stage not found.")
    
    cand, stage = row
    
    # Security: Ensure this interviewer is actually assigned to this stage
    if str(stage.interviewer_id) != user_id:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="You are not assigned to this candidate's stage.")

    # 2. Rule: Cannot submit twice for same stage
    dup_stmt = (
        select(InterviewFeedback)
        .where(
            InterviewFeedback.candidate_id == req.candidate_id,
            InterviewFeedback.stage_id == req.stage_id,
            InterviewFeedback.interviewer_id == uuid.UUID(user_id) if user_id else None
        )
    )
    dup_res = await db.execute(dup_stmt)
    if dup_res.scalars().first():
        throw_msg = "You have already submitted feedback for this stage."
        raise HTTPException(status_code=400, detail=throw_msg)

    # 3. Create Feedback Entry
    feedback = InterviewFeedback(
        candidate_id=req.candidate_id,
        job_id=stage.job_id,
        stage_id=req.stage_id,
        interviewer_id=uuid.UUID(user_id) if user_id else None,
        decision=req.decision,
        rating=req.rating,
        feedback_text=req.feedback_text
    )
    db.add(feedback)
    
    # 4. Notify HR about the feedback
    try:
        hr_email = stage.job.hiring_manager_email if stage.job and stage.job.hiring_manager_email else "admin@example.com"
        job_title = stage.job.title if stage.job else "the position"
        decision_label = req.decision.upper().replace('_', ' ')
        
        interviewer_name = current_user.name or current_user.email or "An Interviewer"
        subject = f"Interview Feedback Submitted: {cand.name} for {job_title}"
        body = f"Hello,\n\nInterviewer {interviewer_name} has submitted feedback for candidate {cand.name} at stage '{stage.stage_name}'.\n\nDecision: {decision_label}\nRating: {req.rating}/5\nFeedback: {req.feedback_text}\n\nYou can review this candidate on the dashboard.\n\nThank you,\nHiring.AI Assistant"
        
        from src.tools.hiring_tools import send_email
        send_email(to=hr_email, subject=subject, body=body)
        logger.info(f"Feedback notification email sent to HR: {hr_email}")
    except Exception as e:
        logger.error(f"Failed to send feedback email to HR: {e}")
    
    # 5. Handle Pipeline Progression
    log_msg = f"{cand.name} received {decision_label} from {stage.stage_name}"
    
    return await _process_candidate_decision(db, cand, stage, current_user, req.decision, log_msg)


@app.get("/candidates/{candidate_id}/feedback", summary="Get all interview feedback for a candidate")
async def get_candidate_feedback(candidate_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Fetch structured evaluations from all interviewers for a candidate."""
    stmt = (
        select(InterviewFeedback)
        .options(
            joinedload(InterviewFeedback.interviewer),
            joinedload(InterviewFeedback.stage)
        )
        .where(InterviewFeedback.candidate_id == candidate_id)
        .order_by(InterviewFeedback.created_at.asc())
    )
    result = await db.execute(stmt)
    feedbacks = result.scalars().all()
    
    return [
        {
            "id": str(f.id),
            "decision": f.decision,
            "rating": f.rating,
            "feedback_text": f.feedback_text,
            "interviewer_name": f.interviewer.name if f.interviewer else "Unknown",
            "stage_name": f.stage.stage_name if f.stage else "Unknown Stage",
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in feedbacks
    ]


# ─────────────────────────────────────────────────────────────
# Candidate Management (CRUD)
# ─────────────────────────────────────────────────────────────

@app.post("/candidates", response_model=CandidateIdResponse, status_code=201, summary="Create a new candidate profile")
async def create_candidate(
    req: CandidateCreate,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    # Check if candidate profile already exists in this org
    cand_stmt = select(Candidate).where(Candidate.email == req.email, Candidate.organization_id == org_id)
    existing_cand = (await db.execute(cand_stmt)).scalars().first()
    
    if existing_cand:
        return {"candidate_id": existing_cand.id}
    
    # Create new Candidate Profile
    new_cand = Candidate(
        organization_id=org_id,
        name=req.name,
        email=req.email,
        phone=req.phone,
        resume_url=req.resume_url,
        skills=req.skills,
        experience=req.experience,
        interviewer_id=current_user.id,
        status="applied"
    )
    db.add(new_cand)
    await db.commit()
    await db.refresh(new_cand)
    
@app.post("/applications", response_model=ApplicationSimpleResponse, status_code=201, summary="Assign a candidate to a job pipeline")
async def create_application(
    req: ApplicationCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    # 1. Verify Job exists and belongs to org
    job_stmt = select(Job).where(Job.id == req.job_id, Job.organization_id == org_id)
    job = (await db.execute(job_stmt)).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found in your organization")
    
    if job.pipeline_state != PipelineStatus.WAITING_FOR_APPLICATIONS.value:
        raise HTTPException(
            status_code=400, 
            detail=f"Rule Violation: Candidates can ONLY be added while job is active for intake. Current state: {job.pipeline_state}"
        )

    # 2. Verify Candidate exists and belongs to org
    cand_stmt = select(Candidate).where(Candidate.id == req.candidate_id, Candidate.organization_id == org_id)
    candidate = (await db.execute(cand_stmt)).scalars().first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in your organization")

    # 3. Check for duplicate application
    dup_stmt = select(Application).where(Application.candidate_id == req.candidate_id, Application.job_id == req.job_id)
    existing_app = (await db.execute(dup_stmt)).scalars().first()
    if existing_app:
        raise HTTPException(status_code=400, detail="Candidate is already in the pipeline for this job")

    # 4. Create Application record (is_scored defaults to False)
    new_app = Application(
        job_id=req.job_id,
        candidate_id=req.candidate_id,
        stage="APPLICATION_RECEIVED", # Exact match to user spec Phase 2
        source="manual",
        organization_id=org_id,
        applied_at=datetime.now(timezone.utc)
    )
    db.add(new_app)

    # Log activity
    user_name = current_user.name or current_user.email or "Unknown User"
    await log_activity(
        job_id=str(req.job_id),
        message=f"Candidate {candidate.name} was added to role {job.title} by {user_name}",
        type="candidate_added"
    )
    
    await db.commit()
    await db.refresh(new_app)

    # Note: We NO LONGER auto-invoke `resume_graph_with_selection`. 
    # New applications will sit here until the `wait_for_applications` celery task 
    # executes Phase 3 (score_resumes). This guarantees NO stage skipping.
    
    return {
        "application_id": new_app.id,
        "message": "Candidate successfully linked to job pipeline. Awaiting AI screening Phase 3."
    }

async def resume_graph_with_selection(job_id: str, candidate_id: str):
    """
    Background worker to signal the LangGraph pipeline that a 
    manually sourced candidate should proceed to interviews.
    """
    from src.graph.pipeline import get_pipeline
    from langgraph.types import Command
    
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}
    
    try:
        logger.info("⚡ [Auto-Move] Resuming graph for HR selection on job {}", job_id)
        await pipeline.ainvoke(
            Command(resume={
                "action_type": "candidate_select",
                "job_id": job_id,
                "stage_id": "hr_review", # Standard interrupt point
                "decision": "select",
                "selected_ids": [candidate_id]
            }),
            config=config,
        )
        logger.success("🚀 [Auto-Move] Graph resumed successfully")
    except Exception as e:
        logger.error("❌ [Auto-Move] Failed to resume graph: {}", e)

@app.get("/candidates", response_model=List[ApplicationFlatResponse], summary="List all candidates with pipeline context")
async def list_candidates(
    status: Optional[str] = None,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    # 3-Way Join: Application -> Candidate -> Job
    stmt = (
        select(
            Application.candidate_id,
            Candidate.name.label("candidate_name"),
            Candidate.email.label("candidate_email"),
            Application.job_id,
            Job.title.label("job_title"),
            Candidate.status.label("status"),
            Application.stage.label("stage"),
            Application.applied_at.label("updated_at")
        )
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(Job, Application.job_id == Job.id)
        .where(Job.organization_id == org_id)
    )
    
    # Silo visibility based on role: Interviewers only see assigned candidates
    if current_user.role == "interviewer":
        stmt = stmt.where(Application.interviewer_id == current_user.id)

    if status:
        stmt = stmt.where(Candidate.status == status)
        
    result = await db.execute(stmt.order_by(Application.applied_at.desc()))
    rows = result.all()
    
    return [
        {
            "candidate_id": row.candidate_id,
            "candidate_name": row.candidate_name,
            "candidate_email": row.candidate_email,
            "job_id": row.job_id,
            "job_title": row.job_title,
            "status": row.status,
            "stage": row.stage,
            "updated_at": row.updated_at
        }
        for row in rows
    ]

@app.get("/candidates/{candidate_id}", response_model=CandidateResponse, summary="Get full candidate details")
async def get_candidate(
    candidate_id: uuid.UUID, 
    current_user: User = Depends(require_interviewer_or_above), 
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.organization_id == org_id)
    )
    cand = result.scalars().first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    # 3. Secure detailed profile access: Interviewer must be assigned to at least one application
    if current_user.role == "interviewer":
        app_stmt = select(Application).where(Application.candidate_id == candidate_id, Application.interviewer_id == current_user.id)
        app_res = await db.execute(app_stmt)
        if not app_res.scalars().first():
            raise HTTPException(status_code=403, detail="Access denied: You are not assigned to any application for this candidate")

    return cand

@app.put("/candidates/{candidate_id}", response_model=CandidateResponse, summary="Update candidate profile or status")
async def update_candidate(
    candidate_id: uuid.UUID,
    req: CandidateUpdate,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.organization_id == org_id)
    )
    cand = result.scalars().first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 4. Secure updates: Only assigned interviewer or Admin
    if current_user.role == "interviewer":
        app_stmt = select(Application).where(Application.candidate_id == candidate_id, Application.interviewer_id == current_user.id)
        app_res = await db.execute(app_stmt)
        if not app_res.scalars().first():
            raise HTTPException(status_code=403, detail="Access denied: You are not assigned to any application for this candidate")

    # Update fields
    update_data = req.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(cand, key, value)

    await db.commit()
    await db.refresh(cand)
    return cand

@app.delete("/candidates/{candidate_id}", summary="Delete a candidate profile")
async def delete_candidate(
    candidate_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.organization_id == org_id)
    )
    cand = result.scalars().first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    await db.delete(cand)
    await db.commit()
    return {"message": "Candidate deleted successfully"}

@app.get("/applications", response_model=List[ApplicationFlatResponse], summary="List all candidate applications across jobs")
async def list_applications(
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    stmt = (
        select(
            Application.id.label("application_id"),
            Application.candidate_id,
            Candidate.name.label("candidate_name"),
            Candidate.email.label("candidate_email"),
            Application.job_id,
            Job.title.label("job_title"),
            Candidate.status.label("status"),
            Application.stage.label("stage"),
            Application.score.label("score"),
            Application.applied_at.label("updated_at")
        )
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(Job, Application.job_id == Job.id)
        .where(Job.organization_id == org_id)
        .distinct(Application.candidate_id, Application.job_id)
        .order_by(Application.candidate_id, Application.job_id, Application.score.desc(), Application.applied_at.desc())
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        {
            "candidate_id": row.candidate_id,
            "candidate_name": row.candidate_name,
            "candidate_email": row.candidate_email,
            "job_id": row.job_id,
            "job_title": row.job_title,
            "status": row.status,
            "stage": row.stage,
            "score": row.score,
            "updated_at": row.updated_at
        }
        for row in rows
    ]

# ─────────────────────────────────────────────────────────────
# Interview Management
# ─────────────────────────────────────────────────────────────

@app.post("/interviews", response_model=InterviewResponse, status_code=201, summary="Schedule a new interview")
async def schedule_interview(
    req: InterviewCreate,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    # 1. Verify Candidate exists in the organization
    cand_res = await db.execute(
        select(Candidate).where(Candidate.id == req.candidate_id, Candidate.organization_id == org_id)
    )
    cand = cand_res.scalars().first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found in your organization")
        
    # 2. Verify Interviewer exists in the organization
    int_res = await db.execute(
        select(User).where(User.id == req.interviewer_id, User.organization_id == org_id)
    )
    interviewer = int_res.scalars().first()
    if not interviewer:
        raise HTTPException(status_code=404, detail="Interviewer not found in your organization")
        
    # 3. Create Interview
    new_interview = Interview(
        id=uuid.uuid4(),
        organization_id=org_id,
        candidate_id=req.candidate_id,
        application_id=req.application_id,
        interviewer_id=req.interviewer_id,
        scheduled_time=req.scheduled_time,
        meeting_link=req.meeting_link,
        status="scheduled"
    )
    db.add(new_interview)
    await db.commit()
    await db.refresh(new_interview)
    
    # Attach names for response
    new_interview.candidate_name = cand.name
    new_interview.interviewer_name = interviewer.name
    
    return new_interview


@app.get("/interviewer/candidates", summary="List actionable candidates assigned to this interviewer")
async def list_interviewer_candidates(
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns only candidates assigned to this interviewer that are in actionable stages.
    Stages: shortlisted, interview
    """
    user_id = current_user.id
    org_id = current_user.organization_id
    
    logger.info("🔍 [TRACE] list_interviewer_candidates | user_id={} | org_id={}", user_id, org_id)

    # --- NORMALIZE TASK LIST QUERY ---
    stmt = (
        select(Application, Candidate.name, Job.title, Candidate.resume_url, Candidate.skills, Candidate.experience)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(Job, Application.job_id == Job.id)
        .where(
            Job.organization_id == org_id,                                        # Organization Isolation
            Application.stage.in_(["interview", "interviewing", "interview_scheduled"]) # Actionable Stages (post-HR)
        )
    )
    
    # 3. Team-Wide Visibility (Admins & Interviewers see all apps in the org)
    stmt = stmt.order_by(Application.applied_at.desc())                           # Priortize Recent Applications
    
    result = await db.execute(stmt)
    rows = result.all()
    logger.info("✅ [SECURITY] Found {} authorized candidates for user {}", len(rows), user_id)
    
    candidates = []
    for app_row, cand_name, job_title, resume_url, cand_skills, cand_exp in rows:
        candidates.append({
            "application_id": str(app_row.id),
            "candidate_id": str(app_row.candidate_id),
            "candidate_name": cand_name,
            "job_title": job_title,
            "stage": app_row.stage,
            "score": app_row.score or 0,
            "resume_url": resume_url,
            "ai_summary": app_row.ai_reasoning,
            "skills": cand_skills
        })
        
    return candidates


@app.get("/interviewer/interviews", response_model=List[InterviewResponse], summary="List upcoming interviews for this interviewer")
async def list_interviewer_interviews(
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns only upcoming interviews for this interviewer.
    JOIN: interviews -> applications -> candidates -> jobs
    """
    user_id = current_user.id
    org_id = current_user.organization_id
    now = datetime.now(timezone.utc)
    
    logger.info("🔍 [TRACE] list_interviewer_interviews | user_id={} | org_id={}", user_id, org_id)

    # --- NORMALIZE INTERVIEW SCHEDULE QUERY ---
    stmt = (
        select(Interview, Candidate.name.label("candidate_name"), Job.title.label("job_title"))
        # JOIN structure ensures no ambiguous job mappings (as requested)
        .join(Application, Interview.application_id == Application.id)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(Job, Application.job_id == Job.id)
        .where(
            Interview.organization_id == org_id,      # Organization Isolation
            Interview.scheduled_time >= now
        )
    )
    
    # Ownership Isolation (Only for basic interviewers)
    if current_user.role == "interviewer":
         stmt = stmt.where(Interview.interviewer_id == user_id)
    
    stmt = stmt.order_by(Interview.scheduled_time.asc())     # Chronological Order
    
    result = await db.execute(stmt)
    rows = result.all()
    logger.info("✅ [SECURITY] Found {} authorized interviews for user {}", len(rows), user_id)
    
    interviews = []
    for row in rows:
        interview, cand_name, job_title = row
        interviews.append({
            "interview_id": str(interview.id),
            "candidate_name": cand_name,
            "job_title": job_title,
            "scheduled_time": interview.scheduled_time.isoformat(),
            "meeting_link": interview.meeting_link,
            "status": interview.status
        })
        
    return interviews


@app.post("/interviews/{interview_id}/feedback", summary="Submit post-interview feedback and close task")
async def submit_interview_feedback(
    interview_id: uuid.UUID,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Final feedback hook after a meeting.
    Updates interview status and progresses application stage.
    """
    # 1. ROLE CHECK
    if current_user.role != UserRole.interviewer:
        logger.warning("🚫 [SECURITY] Forbidden feedback attempt by role={}", current_user.role)
        raise HTTPException(status_code=403, detail="Strictly for interviewer role only")

    # 2. GET INTERVIEW (with Application join for org check)
    stmt = (
        select(Interview)
        .options(joinedload(Interview.application))
        .where(Interview.id == interview_id)
    )
    result = await db.execute(stmt)
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # 3. OWNERSHIP CHECK
    if interview.interviewer_id != current_user.id:
        logger.error({
            "event": "feedback_failed",
            "user": str(current_user.id),
            "application_id": str(interview.application_id if interview.application else "N/A"),
            "reason": "Ownership mismatch: You are not assigned to this interview"
        })
        raise HTTPException(status_code=403, detail="You are not assigned to this interview")

    application = interview.application
    if not application or application.organization_id != current_user.organization_id:
        logger.error({
            "event": "feedback_failed",
            "user": str(current_user.id),
            "application_id": str(application.id if application else "N/A"),
            "reason": "Organization boundary violation"
        })
        raise HTTPException(status_code=403, detail="Organization boundary violation")

    # 3.5. STAGE VALIDATION (Defensive Pipeline Locking)
    if application.stage == "rejected":
        logger.error({
            "event": "feedback_failed",
            "user": str(current_user.id),
            "application_id": str(application.id),
            "reason": "Invalid stage: Candidate already rejected"
        })
        raise HTTPException(status_code=400, detail="Candidate has already been rejected; feedback cannot be submitted.")

    if application.stage != "interview":
        logger.error({
            "event": "feedback_failed",
            "user": str(current_user.id),
            "application_id": str(application.id),
            "reason": f"Invalid stage: {application.stage}"
        })
        raise HTTPException(status_code=400, detail=f"Cannot submit feedback for application in '{application.stage}' stage.")

    # 4. UPDATE INTERVIEW
    interview.status = "completed"
    interview.feedback_rating = payload.get("rating")
    interview.feedback_notes = payload.get("notes")
    interview.decision = payload.get("decision")

    # 5. OPTIONAL — UPDATE APPLICATION
    decision = payload.get("decision")

    if decision in ["strong_hire", "hire"]:
        application.stage = "final_selected"
    elif decision == "reject":
        application.stage = "rejected"
        application.rejected = True

    # 6. COMMIT
    await db.commit()

    return {"message": "Interview feedback submitted"}



@app.post("/applications/{application_id}/evaluate", summary="Submit interviewer evaluation and move pipeline")
async def evaluate_candidate(
    application_id: uuid.UUID,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified evaluation hook matching the strict specification.
    Allows dot-notation access to current_user and application.
    """
    # 1. ROLE CHECK
    if current_user.role != UserRole.interviewer:
        logger.warning("🚫 [SECURITY] Forbidden access attempt by role={}", current_user.role)
        raise HTTPException(status_code=403, detail="Strictly for interviewer role only")

    # 2. GET APPLICATION
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # 3. OWNERSHIP CHECK
    # Match snippet: Dot-notation access enabled by upgraded auth dependency
    if application.interviewer_id != current_user.id:
        logger.error({
            "event": "evaluation_failed",
            "user": str(current_user.id),
            "application_id": str(application_id),
            "reason": "Ownership mismatch: You are not assigned to this application"
        })
        raise HTTPException(status_code=403, detail="You are not assigned to this application")

    if application.organization_id != current_user.organization_id:
        logger.error({
            "event": "evaluation_failed",
            "user": str(current_user.id),
            "application_id": str(application_id),
            "reason": "Organization boundary violation"
        })
        raise HTTPException(status_code=403, detail="Organization boundary violation")

    # 3.5. STAGE VALIDATION (Defensive Pipeline Locking)
    if application.stage == "rejected":
        logger.error({
            "event": "evaluation_failed",
            "user": str(current_user.id),
            "application_id": str(application_id),
            "reason": "Invalid stage: Candidate already rejected"
        })
        raise HTTPException(status_code=400, detail="Candidate has already been rejected and cannot be evaluated.")

    if application.stage != "shortlisted":
        logger.error({
            "event": "evaluation_failed",
            "user": str(current_user.id),
            "application_id": str(application_id),
            "reason": f"Invalid stage: {application.stage}"
        })
        raise HTTPException(status_code=400, detail=f"Cannot evaluate application in '{application.stage}' stage.")

    # 4. UPDATE STAGE
    decision = payload.get("decision")

    if decision == "select":
        application.stage = "interview_selected"
    elif decision == "reject":
        application.stage = "rejected"
        application.rejected = True
    else:
        raise HTTPException(status_code=400, detail="Invalid decision: must be 'select' or 'reject'")

    # 5. SAVE FEEDBACK
    application.interviewer_score = payload.get("rating")
    application.interviewer_notes = payload.get("notes")
    application.feedback_submitted = True

    # 6. COMMIT
    await db.commit()

    return {"message": "Evaluation submitted successfully"}

@app.get("/interviews", response_model=List[InterviewResponse], summary="List all interviews with filtering")
async def list_interviews(
    status: Optional[str] = None,
    candidate_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(require_interviewer_or_above),
    db: AsyncSession = Depends(get_db)
):
    org_id = current_user.organization_id
    
    # Base query joining Candidate and User for names
    stmt = (
        select(Interview, Candidate.name.label("candidate_name"), User.name.label("interviewer_name"))
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .join(User, Interview.interviewer_id == User.id)
        .where(Interview.organization_id == org_id)
    )
    
    # Role-based silo
    if current_user.role == "interviewer":
        stmt = stmt.where(Interview.interviewer_id == current_user.id)
    
    # Filters
    if candidate_id:
        stmt = stmt.where(Interview.candidate_id == candidate_id)
    if status:
        stmt = stmt.where(Interview.status == status)
        
    result = await db.execute(stmt.order_by(Interview.scheduled_time.asc()))
    
    interviews = []
    for row in result.all():
        interview, cand_name, int_name = row
        interview.candidate_name = cand_name
        interview.interviewer_name = int_name
        interviews.append(interview)
        
    return interviews


@app.post("/send-rejection-email", summary="Manually send a rejection email to a candidate")
async def send_manual_rejection_email(req: RejectionEmailRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Triggers the standard rejection email template.
    Checks that the application is indeed 'rejected' and hasn't received the email yet.
    """
    # 1. Fetch Application with Candidate, Job and current_stage info
    stmt = (
        select(Application)
        .options(
            joinedload(Application.candidate),
            joinedload(Application.current_stage),
            joinedload(Application.job),
            joinedload(Application.candidate).joinedload(Candidate.organization)
        )
        .where(Application.candidate_id == req.candidate_id, Application.job_id == req.job_id)
    )
    res = await db.execute(stmt)
    app = res.scalars().first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found for this candidate and job")

    cand = app.candidate
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 2. Assertions (SaaS Production Security)
    if app.stage != "rejected":
        raise HTTPException(status_code=400, detail=f"Cannot send rejection email to candidate in '{app.stage}' status for this job.")
    
    if app.rejection_sent:
        raise HTTPException(status_code=400, detail="Rejection email has already been sent to this candidate for this job.")

    # 3. Data for Template
    job_title = app.job.title if app.job else "Position"
    company_name = cand.organization.name if cand.organization else "Hiring Team"
    
    # 4. Send Templated Email
    try:
        send_rejection_email_tool.func(
            candidate_email=cand.email,
            candidate_name=cand.name,
            job_title=job_title,
            company_name=company_name
        )
        
        # 5. Update State
        app.rejection_sent = True
        app.rejected_at = datetime.now(timezone.utc)
        await db.commit()
        
        # 6. Log Activity
        await log_activity(
            job_id=str(req.job_id),
            message=f"Rejection email sent to {cand.name}",
            type="rejection_email"
        )

        logger.info(f"📧 Manual rejection email sent to {cand.email} (Job: {job_title})")
        return {"status": "success", "message": f"Rejection email sent to {cand.name}."}

    except Exception as e:
        logger.error(f"Failed to send rejection email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to dispatch email: {e}")


@app.post("/bulk-send-rejection-email", summary="Send rejection emails to multiple candidates")
async def bulk_send_manual_rejection_emails(req: BulkRejectionEmailRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Triggers mass communication for a list of rejected candidates."""
    # Fetch all Applications for this Job and these Candidates
    stmt = (
        select(Application)
        .options(
            joinedload(Application.candidate).joinedload(Candidate.organization),
            joinedload(Application.job)
        )
        .where(Application.job_id == req.job_id, Application.candidate_id.in_(req.candidate_ids))
    )
    res = await db.execute(stmt)
    applications = res.scalars().all()

    sent_count = 0
    errors = []

    for app in applications:
        if app.stage != "rejected" or app.rejection_sent:
            continue
        
        cand = app.candidate
        if not cand:
            continue

        try:
            job_title = app.job.title if app.job else "Position"
            company_name = cand.organization.name if cand.organization else "Hiring Team"
            
            send_rejection_email_tool.func(
                candidate_email=cand.email,
                candidate_name=cand.name,
                job_title=job_title,
                company_name=company_name
            )
            
            app.rejection_sent = True
            app.rejected_at = datetime.now(timezone.utc)
            sent_count += 1
            
            # Individual log
            await log_activity(str(req.job_id), f"Rejection email sent to {cand.name}", "rejection_email")

        except Exception as e:
            errors.append(f"Failed for {cand.name}: {str(e)}")

    await db.commit()

    if sent_count > 0:
        await log_activity(str(req.job_id), f"Bulk rejection emails sent ({sent_count} candidates)", "rejection_email_bulk")

    return {
        "status": "success",
        "sent_count": sent_count,
        "errors": errors
    }





@app.get("/analytics/feedback", summary="Get aggregated interview feedback statistics")
async def get_feedback_analytics(current_user: User = Depends(require_interviewer_or_above), db: AsyncSession = Depends(get_db)):
    """Provides high-level insights from the structured interview data."""
    # 1. Candidate Ratings
    cand_stmt = (
        select(Candidate.name, func.avg(InterviewFeedback.rating).label("avg_rating"))
        .join(InterviewFeedback, InterviewFeedback.candidate_id == Candidate.id)
        .group_by(Candidate.id, Candidate.name)
        .order_by(func.avg(InterviewFeedback.rating).desc())
        .limit(10)
    )
    cand_res = await db.execute(cand_stmt)
    candidate_ratings = [{"name": r[0], "rating": float(r[1])} for r in cand_res.all()]
    
    # 2. Stage Pass Rates
    # We count 'yes' and 'strong_yes' as "passes"
    stage_stmt = (
        select(
            JobStage.stage_name, 
            func.count(InterviewFeedback.id).label("total"),
            func.count(InterviewFeedback.id).filter(InterviewFeedback.decision.in_(["yes", "strong_yes"])).label("passed")
        )
        .join(InterviewFeedback, InterviewFeedback.stage_id == JobStage.id)
        .group_by(JobStage.id, JobStage.stage_name)
    )
    stage_res = await db.execute(stage_stmt)
    stage_pass_rates = [
        {
            "stage": r[0], 
            "pass_rate": (r[2] / r[1] * 100) if r[1] > 0 else 0,
            "total": r[1]
        } 
        for r in stage_res.all()
    ]
    
    # 3. Interviewer Performance
    interviewer_stmt = (
        select(User.name, func.avg(InterviewFeedback.rating).label("avg_rating"), func.count(InterviewFeedback.id).label("count"))
        .join(InterviewFeedback, InterviewFeedback.interviewer_id == User.id)
        .group_by(User.id, User.name)
        .order_by(func.count(InterviewFeedback.id).desc())
    )
    int_res = await db.execute(interviewer_stmt)
    interviewer_metrics = [
        {"name": r[0], "avg_rating_given": float(r[1]), "interview_count": r[2]} 
        for r in int_res.all()
    ]
    
    return {
        "candidate_ratings": candidate_ratings,
        "stage_pass_rates": stage_pass_rates,
        "interviewer_metrics": interviewer_metrics
    }


async def _process_candidate_decision(
    db: AsyncSession,
    cand,
    current_stage,
    current_user: User,
    decision: str, # "approve", "reject", "strong_yes", "yes", "no", "strong_no"
    log_message: str
):
    """Internal helper to handle candidate progression after a decision/feedback."""

    if decision in ("reject", "no", "strong_no"):
        # ── Handle Rejection ──
        # Update specific Application for this job
        stmt = (
            update(Application)
            .where(Application.candidate_id == cand.id, Application.job_id == current_stage.job_id)
            .values(stage="rejected", rejected=True)
        )
        await db.execute(stmt)
        await db.commit()
        
        # Log rejection
        await log_activity(
            job_id=str(current_stage.job_id),
            message=f"{cand.name} rejected at {current_stage.stage_name}",
            type="candidate_rejected"
        )

        logger.info(f"Candidate {cand.name} rejected by {current_user.email}")
        return {"status": "success", "message": "Candidate rejected."}

    else: # approve / yes / strong_yes
        # ── Handle Approval (Move to Next Stage) ──
        job_id = current_stage.job_id
        current_order = current_stage.stage_order
        
        # ── Optional: Fast-Track Logic ──
        # If strong_yes, try to skip the next stage (move to current + 2)
        skip_count = 1
        if decision == "strong_yes":
            skip_count = 2
            log_message += " [FAST-TRACKED]"
            logger.info(f"🚀 Fast-tracking candidate {cand.name} due to strong_yes.")

        # Find the target stage (either next or +2)
        next_stmt = (
            select(JobStage)
            .where(JobStage.job_id == job_id, JobStage.stage_order >= current_order + skip_count)
            .order_by(JobStage.stage_order.asc())
            .limit(1)
        )
        next_res = await db.execute(next_stmt)
        next_stage = next_res.scalars().first()
        
        if next_stage:
            # Update Application context
            await db.execute(
                update(Application)
                .where(Application.candidate_id == cand.id, Application.job_id == job_id)
                .values(
                    current_stage_id=next_stage.id,
                    stage="interviewing", # transition string
                    interviewer_id=next_stage.interviewer_id
                )
            )

            # Log approval
            await log_activity(
                job_id=str(current_stage.job_id),
                message=log_message,
                type="candidate_approved"
            )

            await db.commit()
            
            # Notify NEXT interviewer
            stmt_user = (
                select(JobStage)
                .options(selectinload(JobStage.assigned_user))
                .where(JobStage.id == next_stage.id)
            )
            next_stage_with_user = (await db.execute(stmt_user)).scalars().first()
            
            if next_stage_with_user and next_stage_with_user.assigned_user:
                next_email = next_stage_with_user.assigned_user.email
                subject = f"Interview Task: {cand.name}"
                body = f"""Hello,
                
You have been assigned to the next interview stage for {cand.name}.
Stage: {next_stage.stage_name}

Please log in to your dashboard to review the candidate and provide your evaluation:
http://localhost:8000/dashboard/my-tasks

Best regards,
Hiring.AI System"""
                
                send_email(to=next_email, subject=subject, body=body)
                logger.info(f"Notification sent to next interviewer: {next_email}")

                # Log transition
                await log_activity(
                    job_id=str(current_stage.job_id),
                    message=f"Candidate {cand.name} transitioned to stage: {next_stage.stage_name}",
                    type="stage_transitioned"
                )

            logger.info(f"Candidate {cand.name} moved to stage: {next_stage.stage_name}")
            return {"status": "success", "message": f"Candidate moved to next stage: {next_stage.stage_name}"}
        else:
            # ── No more stages -> Completed interview process ──
            await db.execute(
                update(Application)
                .where(Application.candidate_id == cand.id, Application.job_id == current_stage.job_id)
                .values(stage="completed")
            )
            
            # Log completion
            await log_activity(
                job_id=str(current_stage.job_id),
                message=f"Candidate {cand.name} completed all interview stages.",
                type="process_completed"
            )

            await db.commit()
            
            job_title = current_stage.job.title if current_stage.job else "the position"
            
            # 1. Notify Candidate
            send_email(
                to=cand.email,
                subject=f"Interview Process Completed - {job_title}",
                body=f"Hi {cand.name},\n\nCongratulations on completing all the interview stages for {job_title}! Our team will now review the final evaluations and get back to you with an update shortly.\n\nBest regards,\nHiring Team"
            )

            # 2. Notify HR Manager
            hr_email = current_stage.job.hiring_manager_email if current_stage.job and current_stage.job.hiring_manager_email else "admin@example.com"
            send_email(
                to=hr_email,
                subject=f"Final Decision Required: {cand.name} for {job_title}",
                body=f"Hello,\n\nCandidate {cand.name} has successfully completed all assigned interview stages for the role of {job_title}.\n\nPlease review their evaluations on the dashboard and make a final offer or rejection decision.\n\nDashboard: http://localhost:8000/dashboard/jobs/{current_stage.job_id if current_stage.job_id else ''}\n\nThank you,\nHiring.AI Assistant"
            )
            
            logger.info(f"Candidate {cand.name} completed all interview stages. Notifications sent.")
            return {"status": "success", "message": "Candidate completed all interview stages. HR and Candidate notified."}


@app.post("/jobs/{job_id}/final-decision", summary="HR submits post-interview final decisions (Decision 4)")
async def final_decision(job_id: str, req: FinalDecisionRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Resumes the LangGraph pipeline paused at the send_final_decision interrupt.
    - selected_ids non-empty → offer letters sent
    - selected_ids empty     → all rejections sent
    """
    # 1. VALIDATION: Ensure selected candidates are not already rejected
    if req.selected_ids:
        res = await db.execute(
            select(Application).where(Application.candidate_id.in_(req.selected_ids))
        )
        apps = res.scalars().all()
        for app in apps:
            if app.stage == "rejected" or app.rejected:
                 logger.error({
                     "event": "hire_failed",
                     "user": str(current_user.id),
                     "candidate_id": str(app.candidate_id),
                     "reason": "Candidate was already rejected"
                 })
                 raise HTTPException(status_code=400, detail=f"Candidate {app.candidate_id} was already rejected and cannot be selected for an offer.")

    thread_id = f"job-{job_id}"
    
    # Phase 15: Interaction Trace
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [final_decision] job_id={} offers={}", job_id, req.selected_ids)

    resume_value = {
        "action_type": "final_select",
        "job_id": job_id,
        "trace_id": trace_id,
        "stage_id": "final_decision",
        "decision": "offer",
        "selected_ids": req.selected_ids
    }


    await pipeline.ainvoke(
        Command(resume=resume_value),
        config=config,
    )

    return {
        "job_id":      job_id,
        "offers_sent": len(req.selected_ids),
        "message":     "Final decisions processed. Pipeline complete.",
    }


@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse, summary="Get pipeline status")
async def get_status(job_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return the current pipeline state for a job. Enforces organization isolation."""
    # Org isolation: ensure this job belongs to the calling user's organization
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.organization_id == current_user.organization_id
        )
    )
    job_row = result.scalars().first()
    if not job_row:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found or access denied")
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    state = await pipeline.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail=f"job_id={job_id} not found")

    s = state.values
    return JobStatusResponse(
        job_id=job_id,
        pipeline_status=s.get("pipeline_status", "unknown"),
        status=job_row.status_field or "PROCESSING",
        jd_revision_count=s.get("jd_revision_count", 0),
        repost_attempts=s.get("repost_attempts", 0),
        applications_count=len(s.get("applications", [])),
        shortlist_count=len(s.get("shortlist", [])),
    )


@app.get("/my-tasks", summary="Get tasks for the logged in interviewer")
async def get_my_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns candidates assigned to the logged-in user."""
    # Fetch applications assigned to this specific user (interviewer/viewer)
    stmt = (
        select(Application)
        .options(
            selectinload(Application.candidate), 
            selectinload(Application.job)
        )
        .where(Application.interviewer_id == current_user.id)
    )
    result = await db.execute(stmt)
    applications = result.scalars().all()

    tasks = []
    for app in applications:
        # Get the stage name from the candidate's current stage
        stage_name = "Interview"
        stage_id = None
        if app.current_stage_id:
            stage_res = await db.execute(select(JobStage).where(JobStage.id == app.current_stage_id))
            stage_obj = stage_res.scalars().first()
            if stage_obj:
                stage_name = stage_obj.stage_name
                stage_id = str(stage_obj.id)

        tasks.append({
            "application_id": str(app.id),
            "job_id": str(app.job_id),
            "job_title": app.job.title if app.job else "Unknown Job",
            "candidate_id": str(app.candidate_id),
            "candidate_name": app.candidate.name if app.candidate else "Unknown Candidate",
            "candidate_email": app.candidate.email if app.candidate else "",
            "stage_id": stage_id,
            "stage_name": stage_name,
            "status": "pending_interview" if not app.hr_selected else "interviewed",
            "interview_slot": app.interview_slot.isoformat() if app.interview_slot else None,
            "meeting_link": app.meeting_link,
            "resume_url": f"/api/candidates/{app.candidate_id}/resume" if app.resume_path else None
        })

    return {"tasks": tasks}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/team", summary="Get organization users (admin/interviewers/viewers)")
async def get_team_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.organization_id == current_user.organization_id)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return {
        "team": [
            {
                "id": str(u.id), 
                "name": u.name, 
                "email": u.email, 
                "role": u.role,
                "is_calendar_connected": bool(u.google_refresh_token)
            } 
            for u in users
        ]
    }


@app.delete("/team/{user_id}", summary="Admin: Remove a team member")
async def remove_team_member(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # 1. Find the user
    target_org_id = current_user.organization_id
    
    result = await db.execute(select(User).where(
        User.id == user_id, 
        User.organization_id == uuid.UUID(target_org_id) if isinstance(target_org_id, str) else target_org_id
    ))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found in your organization")
        
    # 2. Prevent self-deletion
    if str(user.id) == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")
        
    # 3. Delete the user
    await db.delete(user)
    await db.commit()
    
    return {"message": f"User {user.email} removed from team"}


@app.get("/me", summary="Get current user profile and integration status")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Returns the authenticated user's details including OAuth status."""
    # Ensure we fetch the actual current user, not just anyone in the organization
    stmt = select(User).where(User.id == current_user.id)
    res = await db.execute(stmt)
    user = res.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    from src.db.models import Integration
    stmt_li = select(Integration).where(
        Integration.organization_id == user.organization_id,
        Integration.provider == "linkedin"
    )
    res_li = await db.execute(stmt_li)
    li_integration = res_li.scalars().first()
    
    linkedin_status = li_integration.status if li_integration else None
    li_meta = li_integration.provider_metadata or {} if li_integration else {}

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "google_connected": user.google_refresh_token is not None,
        "organization_id": str(user.organization_id),
        "linkedin_status": linkedin_status,
        "linkedin_account_name": li_meta.get("account_name"),
        "linkedin_account_picture": li_meta.get("account_picture"),
        "linkedin_company_urn": li_meta.get("company_urn"),
    }


# ─────────────────────────────────────────────────────────────
# GOOGLE OAUTH (Step 2)
# ─────────────────────────────────────────────────────────────

@app.get("/auth/google", summary="Google OAuth: Redirect to consent screen (for connected calendar)")
async def google_auth_redirect(current_user: User = Depends(require_admin)):
    """
    Generates the Google OAuth URL and redirects the user.
    Scope: Calendar. State: JWT-signed user_id.
    """
    from src.api.google_auth_utils import get_google_auth_url
    url = get_google_auth_url(user_id=current_user.id)
    return RedirectResponse(url)


@app.get("/auth/login/google", summary="Google OAuth: Direct Login")
async def google_login_redirect():
    """
    Initiates Google OAuth for login purposes (no current_user required).
    """
    from src.api.google_auth_utils import get_google_login_url
    url = get_google_login_url()
    return RedirectResponse(url)


@app.get("/auth/google/callback", summary="Google OAuth: Callback handler")
async def google_auth_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """
    Exchanges the OAuth code for tokens and stores them in the users table.
    Handles both Google Login and Google Calendar connection flows.
    """
    try:
        from src.api.auth import decode_token, create_token
        from src.api.google_auth_utils import exchange_code_for_tokens
        
        payload = decode_token(state)
        if not payload:
            logger.error("❌ Google OAuth: Invalid state received")
            return RedirectResponse(url=f"{settings.frontend_url}/login?error=google_auth_failed")

        purpose = payload.get("purpose")
        user_id_from_state = payload.get("user_id")

        # 1. Exchange code for credentials (now async-safe via thread)
        try:
            ex_user_id, credentials = await exchange_code_for_tokens(code, state)
        except Exception as e:
            logger.error(f"❌ Google OAuth: Token exchange failed: {e}")
            return RedirectResponse(url=f"{settings.frontend_url}/login?error=google_auth_failed")
        
        if not credentials:
            logger.error("❌ Google OAuth: No credentials returned from exchange")
            return RedirectResponse(url=f"{settings.frontend_url}/login?error=google_auth_failed")

        # 2. Get User Email from Google
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=credentials)
        user_info = await asyncio.to_thread(service.userinfo().get().execute)
        google_email = user_info.get("email")

        async with AsyncSessionLocal() as session:
            # 3. Handle Login vs. Calendar Connection
            if purpose == "google_login":
                stmt = select(User).where(User.email == google_email)
                res = await session.execute(stmt)
                user = res.scalars().first()
                
                if not user:
                    # ── Step A: Check for existing pending invite ──
                    invite_stmt = select(Invite).where(Invite.email == google_email, Invite.status == "pending")
                    invite_res = await session.execute(invite_stmt)
                    invite = invite_res.scalars().first()
                    
                    if invite:
                        google_name = user_info.get("name", google_email.split("@")[0].title())
                        new_user = User(
                            email=google_email,
                            name=google_name,
                            organization_id=invite.organization_id,
                            role=invite.role,
                            is_email_verified=True,
                            google_access_token=credentials.token,
                            google_refresh_token=credentials.refresh_token,
                            google_token_expiry=credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
                        )
                        invite.status = "accepted"
                        session.add(new_user)
                        await session.commit()
                        await session.refresh(new_user)
                        user = new_user
                    else:
                        # Auto-signup
                        google_name = user_info.get("name", google_email.split("@")[0].title())
                        new_org = Organization(name=f"{google_name}'s Organization")
                        session.add(new_org)
                        await session.flush()
                        
                        new_user = User(
                            email=google_email,
                            name=google_name,
                            organization_id=new_org.id,
                            role="admin",
                            is_email_verified=True,
                            google_access_token=credentials.token,
                            google_refresh_token=credentials.refresh_token,
                            google_token_expiry=credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
                        )
                        session.add(new_user)
                        await session.commit()
                        await session.refresh(new_user)
                        user = new_user

                # Redirect to frontend callback
                access_token = create_token({"user_id": str(user.id), "role": user.role, "email": user.email, "organization_id": str(user.organization_id)})
                import urllib.parse
                params = urllib.parse.urlencode({"token": access_token, "role": user.role, "email": user.email})
                return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?{params}")
            
            else: # google_oauth (Calendar Connection)
                if not user_id_from_state:
                    return RedirectResponse(url=f"{settings.frontend_url}/dashboard/settings?error=google_auth_failed")
                    
                stmt = select(User).where(User.id == uuid.UUID(user_id_from_state))
                res = await session.execute(stmt)
                user = res.scalars().first()
                if not user: return RedirectResponse(url=f"{settings.frontend_url}/dashboard/settings?error=google_auth_failed")

                user.google_access_token = credentials.token
                user.google_refresh_token = credentials.refresh_token
                user.google_token_expiry = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
                await session.commit()
                
                return HTMLResponse(content="""
                    <html>
                        <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #f8fafc;">
                            <div style="background: white; padding: 2rem; border-radius: 1.5rem; text-align: center; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
                                <h2 style="color: #0f172a; margin-bottom: 0.5rem;">✅ Google Calendar Connected!</h2>
                                <p style="color: #64748b; margin-bottom: 2rem;">Successfully linked to your profile.</p>
                                <button onclick="window.location.href='http://localhost:5173/dashboard/settings'" style="background: #2563eb; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 0.75rem; font-weight: bold; cursor: pointer;">Return to Settings</button>
                            </div>
                        </body>
                    </html>
                """)
    except Exception as e:
        logger.error(f"🚨 Google OAuth: Critical Callback Failure: {e}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=google_auth_failed")

# ─────────────────────────────────────────────────────────────
# LINKEDIN OAUTH (Multi-Tenant)
# ─────────────────────────────────────────────────────────────

@app.get("/auth/linkedin", summary="LinkedIn OAuth: Redirect to consent screen")
async def linkedin_auth_redirect(current_user: User = Depends(require_admin)):
    """
    Generates the LinkedIn OAuth URL and redirects the user.
    Scope: r_liteprofile r_organization_social w_organization_social.
    """
    from src.api.auth import create_token
    import urllib.parse
    
    org_id = current_user.organization_id
    user_id = current_user.id
    state = create_token({"organization_id": org_id, "user_id": user_id, "purpose": "linkedin_oauth"})
    
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "state": state,
        "scope": "openid profile email w_member_social"
    }
    url = f"https://www.linkedin.com/oauth/v2/authorization?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


@app.delete("/integrations/linkedin", summary="Disconnect LinkedIn for the current organization")
async def disconnect_linkedin_integration(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from src.db.models import Integration, Activity
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Missing organization_id")
        
    stmt = select(Integration).where(Integration.organization_id == uuid.UUID(org_id), Integration.provider == "linkedin")
    res = await db.execute(stmt)
    integration = res.scalars().first()
    
    if integration:
        await db.delete(integration)
        
        # Log activity
        act = Activity(
            organization_id=uuid.UUID(org_id),
            message="LinkedIn disconnected",
            type="linkedin_disconnected"
        )
        db.add(act)
        await db.commit()
        return {"message": "LinkedIn integration removed"}
    
    return {"message": "LinkedIn integration not found"}


@app.delete("/integrations/google", summary="Disconnect Google Calendar for the current user")
async def disconnect_google_integration(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Clears Google OAuth tokens for the current user."""
    from src.db.models import Activity
    
    # We use get_current_user to find the actual user object
    # The tokens are stored on the User model
    current_user.google_access_token = None
    current_user.google_refresh_token = None
    current_user.google_token_expiry = None
    
    # Log activity
    act = Activity(
        organization_id=current_user.organization_id,
        message=f"Google Calendar disconnected for {current_user.name}",
        type="google_disconnected"
    )
    db.add(act)
    await db.commit()
    
    return {"message": "Google Calendar integration removed"}


@app.get("/integrations/linkedin/test", summary="Test the LinkedIn integration for the current organization")
async def test_linkedin_integration(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from src.db.models import Integration
    from src.utils.crypto import decrypt_token
    from datetime import datetime, timezone
    from src.tools.platforms.linkedin import refresh_linkedin_token
    import httpx
    
    org_id = current_user.organization_id
    if not org_id:
        return "Token expired or invalid"
        
    stmt = select(Integration).where(Integration.organization_id == uuid.UUID(org_id), Integration.provider == "linkedin")
    res = await db.execute(stmt)
    integration = res.scalars().first()
    
    if not integration or not integration.access_token:
        if integration and getattr(integration, "status", None) != "error":
            integration.status = "error"
            await db.commit()
        return "Token expired or invalid"
        
    # Auto-refresh if expired
    if integration.expires_at and integration.expires_at < datetime.now(timezone.utc):
        if not integration.refresh_token:
            integration.status = "expired"
            await db.commit()
            return "Token expired or invalid"
            
        success = await refresh_linkedin_token(integration, db)
        if not success:
            integration.status = "expired"
            await db.commit()
            return "Token expired or invalid"
            
        from src.db.models import Integration
        stmt = select(Integration).where(
            Integration.organization_id == current_user.organization_id,
            Integration.provider == "linkedin"
        )
        integration = (await db.execute(stmt)).scalar_one_or_none()
        
        if not integration:
            return "Not connected"
            
        access_token = decrypt_token(integration.access_token)
    
    # Try an API call to test connection
    acl_url = "https://api.linkedin.com/v2/organizationAcls?q=roleAssignee"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": "202401"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(acl_url, headers=headers)
        if resp.status_code == 200:
            if integration.status != "active":
                integration.status = "active"
                await db.commit()
            return "LinkedIn connection is valid"
        else:
            integration.status = "error"
            await db.commit()
            return "Token expired or invalid"

@app.get("/auth/linkedin/callback", summary="LinkedIn OAuth: Callback handler")
async def linkedin_auth_callback(code: str = None, state: str = None, error: str = None, error_description: str = None, db: AsyncSession = Depends(get_db)):
    """
    Exchanges the OAuth code for tokens, fetches company URN, and upserts into Integration table.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"LinkedIn OAuth Error: {error_description}")
        
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
        
    from src.api.auth import decode_token
    payload = decode_token(state)
    if not payload or payload.get("purpose") != "linkedin_oauth":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
        
    org_id = payload.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="Missing organization in state")
        
    import httpx
    
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
        "redirect_uri": settings.linkedin_redirect_uri
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Request with form URL encodings for tokens
        token_resp = await client.post(token_url, data=token_data)
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve access token from LinkedIn")
            
        token_data_json = token_resp.json()
        access_token = token_data_json.get("access_token")
        refresh_token = token_data_json.get("refresh_token")
        expires_in = token_data_json.get("expires_in")
        
        from datetime import datetime, timezone, timedelta
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        
        # Fetch organization URN
        acl_url = "https://api.linkedin.com/v2/organizationAcls?q=roleAssignee"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": "202401"
        }
        acl_resp = await client.get(acl_url, headers=headers)
        
        company_urn = None
        logger.info("[LinkedIn OAuth] ACL response status: {} body: {}", acl_resp.status_code, acl_resp.text[:500])
        if acl_resp.status_code == 200:
            elements = acl_resp.json().get("elements", [])
            logger.info("[LinkedIn OAuth] Found {} organization ACL element(s)", len(elements))
            if elements:
                company_urn = elements[0].get("organization")
                logger.info("[LinkedIn OAuth] company_urn extracted: {}", company_urn)

        # Fetch personal profile info (name, picture) — always available
        account_name = None
        account_picture = None
        account_sub = None
        userinfo_resp = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}", "LinkedIn-Version": "202401"}
        )
        logger.info("[LinkedIn OAuth] userinfo status: {}", userinfo_resp.status_code)
        if userinfo_resp.status_code == 200:
            ui = userinfo_resp.json()
            account_name = ui.get("name") or f"{ui.get('given_name', '')} {ui.get('family_name', '')}".strip()
            account_picture = ui.get("picture")
            account_sub = ui.get("sub")
            logger.info("[LinkedIn OAuth] account_name: {}", account_name)

    metadata = {}
    if company_urn:
        metadata["company_urn"] = company_urn
    if account_name:
        metadata["account_name"] = account_name
    if account_picture:
        metadata["account_picture"] = account_picture
    if account_sub:
        metadata["account_sub"] = account_sub
        
    async with AsyncSessionLocal() as session:
        from src.db.models import Integration
        # Upsert integration
        stmt = select(Integration).where(Integration.organization_id == uuid.UUID(org_id), Integration.provider == "linkedin")
        res = await session.execute(stmt)
        integration = res.scalars().first()
        
        from src.utils.crypto import encrypt_token

        encrypted_access = encrypt_token(access_token) if access_token else None
        encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

        if integration:
            integration.access_token = encrypted_access
            if encrypted_refresh:
                integration.refresh_token = encrypted_refresh
            if expires_at:
                integration.expires_at = expires_at
            integration.provider_metadata = metadata
            integration.status = "active"
        else:
            integration = Integration(
                organization_id=uuid.UUID(org_id),
                provider="linkedin",
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                provider_metadata=metadata,
                status="active"
            )
            session.add(integration)
            
        # Log Activity
        org = await session.get(Organization, uuid.UUID(org_id))
        org_name = org.name if org else "the organization"
        act = Activity(
            organization_id=uuid.UUID(org_id),
            message=f"LinkedIn connected for {org_name}",
            type="integration_connected"
        )
        session.add(act)
        
        await session.commit()
        
    return RedirectResponse(url=f"{settings.frontend_url}/dashboard/settings?linkedin_connected=true")

# ── WEB SOCKET EVENT STREAM ──────────────────────────────────────────

# ==============================
# WEBSOCKET ENDPOINT (FIX)
# ==============================
from fastapi import WebSocket, WebSocketDisconnect, Query
from src.api.auth import authenticate_websocket

@app.websocket("/api/events")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    print("🔥 WS request received")

    await websocket.accept()
    print("✅ WebSocket accepted")

    try:
        # ✅ Keep connection alive (CRITICAL FIX)
        while True:
            try:
                # This will wait for client message OR timeout
                data = await websocket.receive_text()
                print("📩 Received:", data)
                await websocket.send_text("pong")
            except Exception:
                # 👉 If no message, still keep alive (prevents loop crash)
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("🔴 Client disconnected")

    except Exception as e:
        print("❌ WS error:", e)

