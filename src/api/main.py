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

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from loguru import logger

from sqlalchemy import select, update, func, text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from langgraph.types import Command
from src.graph.pipeline import get_pipeline
from src.state.schema import HiringState, PipelineStatus
from src.db.database import AsyncSessionLocal, get_db
from src.db.models import (
    Job, ScreeningQuestion, Test, TestQuestion, PipelineState,
    Organization, User, Invite, JobStage, Candidate, Application,
    Activity, InterviewFeedback
)
from src.api.auth import get_current_user, require_admin, require_interviewer_or_above, hash_password, verify_password, create_token
from src.config.settings import settings
from src.utils.activity import log_activity
from src.tools.hiring_tools import send_email, send_rejection_email_tool
from src.api.google_auth_utils import get_google_auth_url, exchange_code_for_tokens
from src.tools.llm_factory import get_llm
from langchain_core.prompts import ChatPromptTemplate

app = FastAPI(
    title="Hiring AI — Automation System",
    description="AI-driven hiring pipeline powered by LangGraph + LangChain",
    version="1.0.0",
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
            active_states = [
                PipelineStatus.JD_DRAFT.value,
                PipelineStatus.WAITING_FOR_APPLICATIONS.value,
                PipelineStatus.SCREENING.value,
                PipelineStatus.JD_APPROVAL_PENDING.value,
                PipelineStatus.HR_REVIEW_PENDING.value
            ]
            result = await session.execute(
                select(Job).where(Job.pipeline_state.in_(active_states))
            )
            jobs = result.scalars().all()
            for job in jobs:
                thread_id = f"job-{job.id}"
                config = {"configurable": {"thread_id": thread_id}}
                state = await pipeline.aget_state(config)
                
                # If there is a next task, check if it's waiting on an interrupt
                if state.next:
                    is_interrupted = False
                    for task in state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            is_interrupted = True
                            break
                            
                    if not is_interrupted:
                        logger.info(f"🔄 Auto-resuming orphaned LangGraph thread: {thread_id}")
                        asyncio.create_task(pipeline.ainvoke(None, config))
                        
    # Run in background to avoid blocking Uvicorn startup
    asyncio.create_task(resume_jobs())



# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class JobStageRequest(BaseModel):
    name: str = Field(..., alias="stage_name")
    user_id: Optional[str] = Field(None, alias="assigned_user_id")

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=None
    )

class NewJobRequest(BaseModel):
    title:                  str = Field(..., alias="job_title")
    stages:                 List[JobStageRequest] = Field(..., alias="hiring_workflow")
    
    # Optional fields with defaults to support simplified title/stages request
    department:             str = "Engineering"
    hiring_manager_name:    str = "Admin"
    hiring_manager_email:   str = "admin@hiring.ai"
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

class RejectionEmailRequest(BaseModel):
    candidate_id: uuid.UUID

class BulkRejectionEmailRequest(BaseModel):
    candidate_ids: List[uuid.UUID]

class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "hiring_manager", "interviewer", "viewer"]

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

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/signup", summary="Register a new B2B company and admin user")
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # 1. Create Organization
    new_org = Organization(name=req.company_name)
    db.add(new_org)
    await db.flush()  # To generate new_org.id
    
    # 2. Create User linked to Organization
    new_user = User(
        email=req.email,
        password=hash_password(req.password),
        name=req.email.split("@")[0],
        organization_id=new_org.id,
        role="admin"
    )
    db.add(new_user)
    await db.commit()
    
    return {
        "message": "Signup successful",
        "organization_id": str(new_org.id),
        "user_id": str(new_user.id)
    }

@app.post("/login", summary="Login to B2B SaaS platform")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Find user by email
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    
    if not user:
        print(f"DEBUG: Login failed - user not found: {req.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # 2. Verify password
    if not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # 3. Generate token with required payloads (user_id + organization_id + role)
    token = create_token({
        "user_id": str(user.id),
        "organization_id": str(user.organization_id),
        "role": user.role
    })
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "role": user.role,
        "name": user.name,
        "organization_id": str(user.organization_id),
        "google_connected": bool(user.google_refresh_token)
    }


@app.post("/invite-user", summary="Admin: Invite a team member")
async def invite_team_member(
    req: InviteRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # Validate role value
    allowed_roles = ["admin", "interviewer", "viewer"]
    if req.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {allowed_roles}")

    # 2. Verify organization exists
    # Explicitly coerce to UUID for lookup
    org_id_uuid = uuid.UUID(current_user.get("organization_id"))
    org_result = await db.execute(select(Organization).where(Organization.id == org_id_uuid))
    org = org_result.scalars().first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # 3. Check if email already registered
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    # 4. Check if invite already exists and is pending
    existing_invite = await db.execute(
        select(Invite).where(
            Invite.email == req.email,
            Invite.organization_id == current_user.get("organization_id"),
            Invite.status == "pending"
        )
    )
    if existing_invite.scalars().first():
        raise HTTPException(status_code=400, detail="An invite for this email is already pending.")

    # 5. Generate a cryptographically secure unique token
    token = secrets.token_urlsafe(32)

    # 6. Create invite record in DB with 24-hour expiry
    invite = Invite(
        email=req.email,
        organization_id=current_user.get("organization_id"),
        role=req.role,
        token=token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(invite)
    await db.commit()

    # 7. Send invite email
    invite_link = f"{settings.frontend_url}/accept-invite/{token}"
    email_body = f"""You have been invited to join {org.name} on Hiring.AI!

Role: {req.role.replace('_', ' ').title()}
Company: {org.name}

Click the link below to accept your invitation and create your account:
{invite_link}

This invite link will expire in 24 hours.

Welcome aboard!
Hiring.AI Team"""

    send_email(
        to=req.email,
        subject="You are invited to join Hiring.AI",
        body=email_body
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
        password=hash_password(req.password),
        organization_id=invite.organization_id,
        role=invite.role
    )
    db.add(new_user)

    # 6. Mark invite as accepted
    invite.status = "accepted"
    await db.commit()

    return {
        "message": "Account created successfully! You can now log in.",
        "email": invite.email,
        "role": invite.role
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
        response = chain.invoke({
            "job_title": req.job_title, 
            "skills": skills_str
        })
        
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
        response = chain.invoke({
            "job_title": req.job_title, 
            "skills": skills_str,
            "message": req.message
        })
        
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
        response = chain.invoke({
            "job_title": req.job_title,
            "location": req.location,
            "experience": req.experience,
            "salary": req.salary
        })
        
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


@app.post("/jobs", summary="Submit new hiring request (admin only)")
async def create_job(
    req: NewJobRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    HR submits a hiring request.
    Creates a new LangGraph thread and starts the pipeline.
    Returns job_id and thread_id for future interactions.
    """
    job_id    = str(uuid.uuid4())
    thread_id = f"job-{job_id}"

    initial_state: HiringState = {
        "job_id":                job_id,
        "organization_id":       current_user.get("organization_id"),
        "graph_thread_id":       thread_id,
        "job_title":             req.title,
        "department":            req.department,
        "hiring_manager_name":   req.hiring_manager_name,
        "hiring_manager_email":  req.hiring_manager_email,
        "interviewer_email":     req.interviewer_email or req.hiring_manager_email,
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
        "meeting_links":         [],
        "error_log":             [],
    }

    # ═══════════════════════════════════════════════════════════════════════════
    # PERSIST TO RELATIONAL DATABASE (SQLAlchemy)
    # ═══════════════════════════════════════════════════════════════════════════
    async with AsyncSessionLocal() as session:
        try:
            new_job = Job(
                id=job_id,
                title=req.title,
                department=req.department,
                hiring_manager_name=req.hiring_manager_name,
                hiring_manager_email=req.hiring_manager_email,
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
                jd_draft="🤖 AI is drafting your Job Description... (this usually takes 10-30 seconds)",
                organization_id=current_user.get("organization_id")
            )
            session.add(new_job)

            # Insert Job Stages
            order = 1
            for stage in req.stages:
                uid = uuid.UUID(stage.user_id) if stage.user_id else None
                
                job_stage = JobStage(
                    job_id=job_id,
                    stage_name=stage.name,
                    stage_order=order,
                    assigned_user_id=uid
                )
                session.add(job_stage)
                order += 1

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
    background_tasks.add_task(pipeline.ainvoke, initial_state, config=config)

    return {
        "job_id":    job_id,
        "thread_id": thread_id,
        "message":   "Pipeline started. JD is being generated and will be sent for HR review.",
    }


@app.get("/jobs", summary="List all jobs for the organization")
async def list_jobs(current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Fetch all jobs belonging to the current user's organization."""
    org_id = current_user.get("organization_id")
    # Multi-tenant isolation enforced here
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.applications))
        .where(Job.organization_id == org_id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "department": j.department,
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
async def get_pipeline_board(current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Returns candidates across all jobs grouped into 4 pipeline stages:
    - screening:  applied, not yet shortlisted
    - hr_review:  shortlisted, HR hasn't decided yet
    - interview:  interview slot scheduled
    - final:      offer sent or rejected
    """
    org_id = current_user.get("organization_id")
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
                "ai_score": round(app.ai_score) if app.ai_score is not None else None,
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
async def get_activity_feed(current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Returns the latest 30 real-time events from the activities table for this organization.
    """
    org_id = current_user.get("organization_id")
    
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
async def get_job(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Fetch complete details of a specific job, including applications."""
    org_id = current_user.get("organization_id")
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
        "location": job.location,
        "experience_required": job.experience_required,
        "salary_range": job.salary_range,
        "required_skills": job.required_skills,
        "status": job.status,
        "pipeline_state": job.pipeline_state.value if job.pipeline_state else "JD_DRAFT",
        "is_cancelled": job.is_cancelled or False,
        "jd_draft": job.jd_draft,
        "technical_test_mcq": job.technical_test_mcq,
        "hiring_workflow": job.hiring_workflow,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "applications": [
            {
                "id": str(a.id),
                "status": a.status,
                "score": a.score,
                "candidate_name": a.candidate.name if a.candidate else "Unknown Candidate",
                "candidate_email": a.candidate.email if a.candidate else "N/A"
            }
            for a in job.applications
        ]
    }


@app.post("/jobs/{job_id}/cancel", summary="Cancel an active pipeline to save AI costs")
async def cancel_job(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Instantly terminate a hiring pipeline."""
    org_id = current_user.get("organization_id")
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


@app.delete("/jobs/{job_id}", summary="Permanently delete a cancelled job")
async def delete_job(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Permanently removes a job and all its data.
    Only allowed if the job has is_cancelled=True (safety guard to prevent
    accidental deletion of active pipelines).
    """
    org_id = current_user.get("organization_id")
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
    logger.info(f"🗑️  Job {job_id} ({job.title}) permanently deleted by user {current_user.get('email')}")
    return {"message": f"Job '{job.title}' permanently deleted."}

@app.api_route("/jobs/{job_id}/approve-jd", methods=["GET", "POST"], summary="HR approves or rejects the generated JD (Decision 1)")
async def approve_jd(job_id: str, request: Request, req: Optional[JDApprovalRequest] = None, current_user: Dict[str, Any] = Depends(get_current_user)):
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
    resume_value = {
        "job_id": job_id,
        "organization_id": current_user.get("organization_id"),
        "decision": "approve" if approved_val else "reject",
        "approved": approved_val, 
        "feedback": feedback_val
    }

    logger.info("📬 [approve_jd] job_id={} approved={} (via {})", job_id, approved_val, request.method)

    await pipeline.ainvoke(
        Command(resume=resume_value),  # value returned by interrupt() in review_jd
        config=config,
    )

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
async def resume_screening(job_id: str, current_user: Dict[str, Any] = Depends(require_admin)):
    """
    Resumes the LangGraph pipeline from the WAITING_FOR_APPLICATIONS interrupt.
    This bypasses the standard 7-day Celery wait for testing/demo purposes.
    """
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [resume_screening] Manually triggering collection for job_id={}", job_id)

    # Resume the LangGraph pipeline paused at publish_jd's interrupt
    await pipeline.ainvoke(
        Command(resume={
            "job_id": job_id,
            "stage_id": "screening",
            "decision": "resume_collection"
        }),
        config=config,
    )

    return {
        "job_id":  job_id,
        "message": "Screening triggered. System is now collecting resumes and scoring.",
    }


@app.post("/jobs/{job_id}/select-candidates", summary="HR selects candidates for interview (Decision 3)")
async def select_candidates(job_id: str, req: CandidateSelectionRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Resumes the LangGraph pipeline after the 2-day shortlist review window.
    Selected candidate_ids proceed to interview scheduling.
    Empty list → pipeline closes.
    """
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [select_candidates] job_id={} selected={}", job_id, req.candidate_ids)

    # Resume the LangGraph pipeline paused at the HR_REVIEW_PENDING interrupt.
    await pipeline.ainvoke(
        Command(resume={
            "job_id": job_id,
            "stage_id": "hr_review",
            "decision": "select",
            "selected_ids": req.candidate_ids
        }),
        config=config,
    )

    return {
        "job_id":          job_id,
        "selected_count":  len(req.candidate_ids),
        "message":         "Candidates selected. Interview scheduling in progress." if req.candidate_ids
                           else "No candidates selected. Pipeline closing.",
    }


@app.get("/jobs/{job_id}/select-candidates", summary="HR selects candidates for interview via link (Decision 3)")
async def select_candidates_get(job_id: str, selected_ids: str = None, token: str = None, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    GET version of select_candidates for easy clicking from emails.
    selected_ids: Comma-separated list of candidate UUIDs.
    """
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
async def submit_decision(req: DecisionRequest, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Submits a decision for a candidate. Moves to next stage if approved, or rejects.
    """
    user_id = current_user.get("user_id")
    
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
    if str(current_stage.assigned_user_id) != user_id:
        if current_user.get("role") != "admin":
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

    log_msg = f"Interviewer {current_user.get('name') or 'Admin'} {req.decision}ed {cand.name} at stage: {current_stage.stage_name}"
    return await _process_candidate_decision(db, cand, current_stage, current_user, req.decision, log_msg)


@app.post("/submit-feedback", summary="Interviewer submits structured feedback and a decision")
async def submit_feedback(req: FeedbackRequest, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Submits structured feedback for a candidate at a specific stage.
    """
    user_id = current_user.get("user_id")
    
    # 1. Fetch Candidate and Stage
    stmt = (
        select(Candidate, JobStage)
        .join(JobStage, JobStage.id == req.stage_id)
        .where(Candidate.id == req.candidate_id)
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Candidate or Stage not found.")
    
    cand, stage = row
    
    # Security: Ensure this interviewer is actually assigned to this stage
    if str(stage.assigned_user_id) != user_id:
        if current_user.get("role") != "admin":
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
    
    # 3. Handle Pipeline Progression
    decision_label = req.decision.upper().replace('_', ' ')
    log_msg = f"{cand.name} received {decision_label} from {stage.stage_name}"
    
    return await _process_candidate_decision(db, cand, stage, current_user, req.decision, log_msg)


@app.get("/candidates/{candidate_id}/feedback", summary="Get all interview feedback for a candidate")
async def get_candidate_feedback(candidate_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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


@app.get("/candidates/{candidate_id}", summary="Get basic candidate details")
async def get_candidate(candidate_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Fetch basic info for a single candidate."""
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    cand = result.scalars().first()
    
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    return {
        "id": str(cand.id),
        "name": cand.name,
        "email": cand.email,
        "status": cand.status,
        "current_stage_id": str(cand.current_stage_id) if cand.current_stage_id else None,
        "rejection_email_sent": cand.rejection_email_sent,
        "rejected_at": cand.rejected_at.isoformat() if cand.rejected_at else None
    }


@app.post("/send-rejection-email", summary="Manually send a rejection email to a candidate")
async def send_manual_rejection_email(req: RejectionEmailRequest, current_user: Dict[str, Any] = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """
    Triggers the standard rejection email template.
    Checks that the candidate is indeed 'rejected' and hasn't received the email yet.
    """
    # 1. Fetch Candidate with Org, Job and Stage info
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.current_stage).joinedload(JobStage.job),
            joinedload(Candidate.organization)
        )
        .where(Candidate.id == req.candidate_id)
    )
    res = await db.execute(stmt)
    cand = res.scalars().first()

    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 2. Assertions (SaaS Production Security)
    if cand.status != "rejected":
        raise HTTPException(status_code=400, detail=f"Cannot send rejection email to candidate in '{cand.status}' status.")
    
    if cand.rejection_email_sent:
        raise HTTPException(status_code=400, detail="Rejection email has already been sent to this candidate.")

    # 3. Data for Template
    job_title = "Position"
    company_name = "Hiring Team"
    
    if cand.organization:
        company_name = cand.organization.name

    if cand.current_stage and cand.current_stage.job:
        job_title = cand.current_stage.job.title

    # 4. Send Templated Email
    try:
        # We call the tool function directly.
        # Note: tool.func is the underlying function for LangChain @tool
        send_rejection_email_tool.func(
            candidate_email=cand.email,
            candidate_name=cand.name,
            job_title=job_title,
            company_name=company_name
        )
        
        # 5. Update State
        cand.rejection_email_sent = True
        cand.rejected_at = datetime.now(timezone.utc)
        await db.commit()
        
        # 6. Log Activity (Step 6)
        if cand.current_stage and cand.current_stage.job_id:
            await log_activity(
                job_id=str(cand.current_stage.job_id),
                message=f"Rejection email sent to {cand.name}",
                type="rejection_email"
            )

        logger.info(f"📧 Manual rejection email sent to {cand.email} (Company: {company_name})")
        return {"status": "success", "message": f"Rejection email sent to {cand.name}."}

    except Exception as e:
        logger.error(f"Failed to send rejection email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to dispatch email: {e}")


@app.post("/bulk-send-rejection-email", summary="Send rejection emails to multiple candidates")
async def bulk_send_manual_rejection_emails(req: BulkRejectionEmailRequest, current_user: Dict[str, Any] = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Triggers mass communication for a list of rejected candidates."""
    # Fetch all candidates
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.current_stage).joinedload(JobStage.job),
            joinedload(Candidate.organization)
        )
        .where(Candidate.id.in_(req.candidate_ids))
    )
    res = await db.execute(stmt)
    candidates = res.scalars().all()

    sent_count = 0
    errors = []
    job_ids = set()

    for cand in candidates:
        if cand.status != "rejected" or cand.rejection_email_sent:
            continue
        
        try:
            job_title = cand.current_stage.job.title if cand.current_stage and cand.current_stage.job else "Position"
            company_name = cand.organization.name if cand.organization else "Hiring Team"
            
            send_rejection_email_tool.func(
                candidate_email=cand.email,
                candidate_name=cand.name,
                job_title=job_title,
                company_name=company_name
            )
            
            cand.rejection_email_sent = True
            cand.rejected_at = datetime.now(timezone.utc)
            sent_count += 1
            if cand.current_stage:
                job_ids.add(str(cand.current_stage.job_id))
            
            # Individual log
            if cand.current_stage:
                 await log_activity(str(cand.current_stage.job_id), f"Rejection email sent to {cand.name}", "rejection_email")

        except Exception as e:
            errors.append(f"Failed for {cand.name}: {str(e)}")

    await db.commit()

    # Bulk log (Step 6)
    for jid in job_ids:
        await log_activity(jid, f"Bulk rejection emails sent ({sent_count} candidates)", "rejection_email_bulk")

    return {
        "status": "success",
        "sent_count": sent_count,
        "errors": errors
    }


@app.get("/candidates", summary="List all candidates with optional status filter")
async def list_candidates(status: Optional[str] = None, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Returns all candidates across all jobs. 
    Can be filtered by ?status=rejected for example.
    """
    stmt = (
        select(Candidate)
        .options(
            joinedload(Candidate.current_stage).joinedload(JobStage.job)
        )
    )
    if status:
        stmt = stmt.where(Candidate.status == status)
    
    stmt = stmt.order_by(Candidate.created_at.desc())
    
    res = await db.execute(stmt)
    candidates = res.scalars().all()

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "email": c.email,
            "status": c.status,
            "job_title": c.current_stage.job.title if c.current_stage and c.current_stage.job else "N/A",
            "rejected_at_stage": c.current_stage.stage_name if c.current_stage else "N/A",
            "rejection_email_sent": c.rejection_email_sent,
            "rejected_at": c.rejected_at.isoformat() if c.rejected_at else None
        }
        for c in candidates
    ]


@app.get("/analytics/feedback", summary="Get aggregated interview feedback statistics")
async def get_feedback_analytics(current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
    current_user: Dict[str, Any],
    decision: str, # "approve", "reject", "strong_yes", "yes", "no", "strong_no"
    log_message: str
):
    """Internal helper to handle candidate progression after a decision/feedback."""

    if decision in ("reject", "no", "strong_no"):
        # ── Handle Rejection ──
        cand.status = "rejected"
        await db.commit()
        
        # Log rejection
        await log_activity(
            job_id=str(current_stage.job_id),
            message=f"{cand.name} rejected at {current_stage.stage_name}",
            type="candidate_rejected"
        )

        logger.info(f"Candidate {cand.name} rejected by {current_user.get('email')}")
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
            cand.current_stage_id = next_stage.id
            
            # ── Sync Application assigned_user_id ──
            await db.execute(
                update(Application)
                .where(Application.candidate_id == cand.id, Application.job_id == job_id)
                .values(assigned_user_id=next_stage.assigned_user_id)
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
            cand.status = "completed"
            
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
async def final_decision(job_id: str, req: FinalDecisionRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Resumes the LangGraph pipeline paused at the send_final_decision interrupt.
    - selected_ids non-empty → offer letters sent
    - selected_ids empty     → all rejections sent
    """
    thread_id = f"job-{job_id}"
    pipeline  = await get_pipeline()
    config    = {"configurable": {"thread_id": thread_id}}

    logger.info("📬 [final_decision] job_id={} offers={}", job_id, req.selected_ids)

    resume_value = {
        "job_id": job_id,
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
async def get_status(job_id: str, current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return the current pipeline state for a job. Enforces organization isolation."""
    # Org isolation: ensure this job belongs to the calling user's organization
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.organization_id == current_user.get("organization_id")
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
        jd_revision_count=s.get("jd_revision_count", 0),
        repost_attempts=s.get("repost_attempts", 0),
        applications_count=len(s.get("applications", [])),
        shortlist_count=len(s.get("shortlist", [])),
    )


@app.get("/my-tasks", summary="Get tasks for the logged in interviewer")
async def get_my_tasks(
    current_user: Dict[str, Any] = Depends(get_current_user),
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
        .where(Application.assigned_user_id == uuid.UUID(current_user.get("user_id")))
    )
    result = await db.execute(stmt)
    applications = result.scalars().all()

    tasks = []
    for app in applications:
        # Get the stage name from the candidate's current stage
        stage_name = "Interview"
        stage_id = None
        if app.candidate and app.candidate.current_stage_id:
            stage_res = await db.execute(select(JobStage).where(JobStage.id == app.candidate.current_stage_id))
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
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.organization_id == current_user.get("organization_id"))
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
    current_user: Dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    # 1. Find the user
    target_org_id = current_user.get("organization_id")
    
    result = await db.execute(select(User).where(
        User.id == user_id, 
        User.organization_id == uuid.UUID(target_org_id) if isinstance(target_org_id, str) else target_org_id
    ))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found in your organization")
        
    # 2. Prevent self-deletion
    if str(user.id) == current_user.get("user_id"):
        raise HTTPException(status_code=400, detail="You cannot remove yourself")
        
    # 3. Delete the user
    await db.delete(user)
    await db.commit()
    
    return {"message": f"User {user.email} removed from team"}


@app.get("/me", summary="Get current user profile and integration status")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Returns the authenticated user's details including OAuth status."""
    stmt = select(User).where(User.organization_id == current_user.get("organization_id"))
    res = await db.execute(stmt)
    user = res.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "google_connected": user.google_refresh_token is not None,
        "organization_id": str(user.organization_id)
    }


# ─────────────────────────────────────────────────────────────
# GOOGLE OAUTH (Step 2)
# ─────────────────────────────────────────────────────────────

@app.get("/auth/google", summary="Google OAuth: Redirect to consent screen (for connected calendar)")
async def google_auth_redirect(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Generates the Google OAuth URL and redirects the user.
    Scope: Calendar. State: JWT-signed user_id.
    """
    from src.api.google_auth_utils import get_google_auth_url
    url = get_google_auth_url(user_id=current_user.get("user_id"))
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
    from src.api.auth import decode_token, create_token
    from src.api.google_auth_utils import exchange_code_for_tokens
    
    payload = decode_token(state)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    purpose = payload.get("purpose")
    user_id_from_state = payload.get("user_id")

    # 1. Exchange code for credentials
    # We need to ensure the flow used for exchange has the same scopes as the initiation
    # But exchange_code_for_tokens uses get_google_auth_flow which has default scopes.
    # Actually, flow.fetch_token() doesn't strictly need scopes matched if the auth was successful.
    ex_user_id, credentials = await exchange_code_for_tokens(code, state)
    
    if not credentials:
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")

    # 2. Get User Email from Google (for Login)
    from googleapiclient.discovery import build
    service = build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()
    google_email = user_info.get("email")

    async with AsyncSessionLocal() as session:
        # 3. Handle Login vs. Calendar Connection
        if purpose == "google_login":
            # Lookup user by email
            stmt = select(User).where(User.email == google_email)
            res = await session.execute(stmt)
            user = res.scalars().first()
            
            if not user:
                # ── Auto-signup: Create a new org + admin user for this Google account ──
                google_name = user_info.get("name", google_email.split("@")[0].title())
                org_name = f"{google_name}'s Organization"
                
                new_org = Organization(name=org_name)
                session.add(new_org)
                await session.flush()  # Get the org ID
                
                new_user = User(
                    email=google_email,
                    name=google_name,
                    organization_id=new_org.id,
                    role="admin",
                    google_access_token=credentials.token,
                    google_refresh_token=credentials.refresh_token,
                    google_token_expiry=credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                user = new_user

            # Success: Generate token and redirect to frontend auth handler
            access_token = create_token({"user_id": str(user.id), "role": user.role, "email": user.email, "organization_id": str(user.organization_id)})
            
            # Redirect to frontend auth callback — the frontend page will store the token
            import urllib.parse
            params = urllib.parse.urlencode({"token": access_token, "role": user.role, "email": user.email})
            return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?{params}")
        
        else: # purpose == "google_oauth" (Calendar Connection)
            if not user_id_from_state:
                raise HTTPException(status_code=400, detail="Missing user_id for calendar connection")
                
            stmt = select(User).where(User.id == uuid.UUID(user_id_from_state))
            res = await session.execute(stmt)
            user = res.scalars().first()
            
            if not user:
                 raise HTTPException(status_code=404, detail="User not found")

            # Store tokens
            user.google_access_token = credentials.token
            user.google_refresh_token = credentials.refresh_token
            user.google_token_expiry = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
            
            await session.commit()
            
            return HTMLResponse(content="""
                <html>
                    <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #f8fafc;">
                        <div style="background: white; padding: 2rem; border-radius: 1.5rem; text-align: center; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
                            <h2 style="color: #0f172a; margin-bottom: 0.5rem;">✅ Google Calendar Connected!</h2>
                            <p style="color: #64748b; margin-bottom: 2rem;">Your tokens have been securely stored in your profile.</p>
                            <button onclick="window.location.href='http://localhost:5173/dashboard/settings'" style="background: #2563eb; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 0.75rem; font-weight: bold; cursor: pointer;">Return to Settings</button>
                        </div>
                    </body>
                </html>
            """)
