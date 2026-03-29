# Hiring.AI — Autonomous AI Hiring Platform

> An enterprise-grade, end-to-end AI recruitment system. It orchestrates your entire hiring pipeline — from generating job descriptions to scheduling interviews — using a stateful LangGraph agent with human-in-the-loop controls.

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Quick Start](#4-quick-start)
5. [Features](#5-features)
6. [Hiring Pipeline Flow](#6-hiring-pipeline-flow)
7. [Resume Scoring System](#7-resume-scoring-system)
8. [Dashboard & UI](#8-dashboard--ui)
9. [Authentication & RBAC](#9-authentication--rbac)
10. [Multi-Tenancy Design](#10-multi-tenancy-design)
11. [API Reference](#11-api-reference)
12. [Background Jobs](#12-background-jobs)
13. [Fault Tolerance](#13-fault-tolerance)
14. [Integrations](#14-integrations)
15. [Environment Variables](#15-environment-variables)
16. [Frontend Structure](#16-frontend-structure)
17. [Future Improvements](#17-future-improvements)

---

## 1. Overview

Hiring.AI eliminates recruiter burnout by running a **24/7 autonomous hiring agent**. It handles:

- AI-generated, market-aware job descriptions
- Multi-layer resume parsing and scoring
- Autonomous candidate shortlisting with explainable AI rankings
- Google Calendar-integrated interview scheduling
- Automated email communications at every stage
- Real-time pipeline visibility with live activity feeds

Each feature is **fully interruptible** — admins can pause, review, override, or cancel the AI at any point, keeping humans firmly in control.

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    React SPA (Vite)                        │
│   Dashboard · Jobs · Candidates · Interviews · Analytics   │
└────────────────────┬──────────────────────────────────────┘
                     │ HTTPS / Axios (JWT)
┌────────────────────▼──────────────────────────────────────┐
│              FastAPI Backend (Python 3.13)                  │
│    Auth · Jobs · Candidates · Activity · Pipeline API      │
└────────┬───────────────────────┬──────────────────────────┘
         │                       │
┌────────▼────────┐   ┌──────────▼──────────────────────────┐
│  LangGraph      │   │           Celery Workers              │
│  State Machine  │   │  Resume Batching · Retry Logic ·      │
│  (Async Nodes)  │   │  7-day Follow-up Timers               │
└────────┬────────┘   └──────────┬──────────────────────────┘
         │                       │
┌────────▼───────────────────────▼──────────────────────────┐
│         PostgreSQL                     Redis               │
│  Jobs · Users · Candidates ·    Celery Broker/Cache        │
│  Activities · LangGraph                                    │
│  Checkpoints                                               │
└────────────────────────────────────────────────────────────┘
```

### LangGraph State Machine
The AI pipeline is a **directed acyclic graph with interrupt nodes**. Key properties:
- **Stateful Persistence**: Every graph transition is checkpointed to PostgreSQL via `AsyncPostgresSaver`. If the server crashes mid-scoring, it resumes from the exact same node.
- **Human-in-the-Loop**: Explicit `interrupt()` nodes pause the graph and wait for admin approval before proceeding (e.g., JD review, shortlist review).
- **Conditional Routing**: Python-free routing via LangGraph conditional edges — no brittle if/else logic in node code.
- **Resume on Restart**: Orphaned pipelines (e.g., from server crashes) are auto-detected and resumed on startup.

---

## 3. Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.13, FastAPI, SQLAlchemy (Async) |
| **Orchestration** | LangGraph, LangChain, Celery |
| **Database** | PostgreSQL (primary + checkpoints), Redis (broker/cache) |
| **Frontend** | React 18, Vite, TailwindCSS v4, Framer Motion, Lucide React |
| **LLMs** | Gemini 2.0 Flash (primary), OpenAI GPT-4o, Ollama (local fallback) |
| **Auth** | JWT (HS256), bcrypt password hashing |
| **Integrations** | Google Calendar API, Google Meet, LinkedIn API, SMTP/Resend Email |

---

## 4. Quick Start

### Prerequisites
- Python 3.13+, Node.js 18+
- PostgreSQL running locally (or Docker)
- Redis running locally (or Docker)

### One-Command Start
```bash
# Install dependencies and start everything
./start.sh

# Stop all processes
./stop.sh
```

### Manual Setup
```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.db.init_db       # Initialize DB & run migrations
uvicorn src.api.main:app --reload

# Celery Worker
celery -A src.scheduler.tasks worker --loglevel=info

# Frontend
cd frontend && npm install && npm run dev
```

Access the app at **http://localhost:5173**. API docs at **http://localhost:8000/docs**.

---

## 5. Features

### 🤖 AI Job Description Generator
- Enter just a title, department, and required skills — the AI builds a full SEO-optimized JD.
- **HR AI Assistant**: A split-screen wizard in the job creation form provides real-time AI suggestions and one-click field filling.
- **Approval Loop**: The generated JD is held at `JD_APPROVAL_PENDING` until an admin explicitly approves or requests changes.
- **Revision Tracking**: Each revision is counted; excessive revision loops trigger automatic escalation.

### 📄 Multi-Layer Resume Scoring
- **PDF/TXT Parsing**: Extracts PII, projects, skills, and experience in structured JSON.
- **Semantic Scoring**: Vector embeddings measure conceptual relevance beyond keyword matching.
- **LLM Deep Evaluation**: Chain-of-Thought reasoning gives each candidate a score (0–100) with explicit pros/cons.
- **Configurable Weights**: Admins set custom `scoring_weights` per job: `{ "skills": 0.5, "experience": 0.3, "education": 0.2 }`.

### 🏅 Autonomous Candidate Shortlisting
- AI ranks all applicants and moves top scorers to "Shortlisted" automatically.
- HR can review and override the shortlist before it advances.

### 📅 Automated Interview Coordination
- **Interviewer Assignment**: Admins assign specific team members to interview stages.
- **Google Calendar Sync**: Checks interviewer availability in real time.
- **Google Meet Generation**: Creates meeting links and sends both parties a calendar invite + confirmation email.
- **7-Day Follow-up**: Celery scheduled task automatically follows up with non-responding candidates.

### 📧 Automated Email Notifications
- Candidates receive stage-change emails automatically (application received, shortlisted, interview invite, offer/rejection).
- All emails are generated with context from the specific JD and candidate profile.

### 🔴 Cancel AI Pipeline (Cost Control)
- Any active pipeline can be cancelled mid-flow from the Job Detail page.
- Cancellation is **non-destructive**: the `pipeline_state` is preserved so the UI shows exactly which stage the pipeline reached before stopping.
- Only cancelled jobs can be deleted, preventing accidental loss of active pipeline data.
- A visual red ❌ marker shows the exact stage where the pipeline was cancelled.

### 🗑️ Delete Cancelled Jobs
- Admins can permanently delete a cancelled job and all its associated data.
- Backend safety guard: the `DELETE /jobs/{id}` endpoint rejects requests for non-cancelled jobs.

### 🟡 Global System Status Indicator
- A live status badge in the top header shows the overall system state.
- **🟡 AI Processing...** — at least one pipeline is actively running.
- **🟢 All systems active** — no active pipelines, system is idle.
- Animated pulse effect when processing is in progress.

### 📡 Live Activity Feed
- A real-time event stream in the dashboard showing the latest AI actions.
- Events are logged when: a resume is parsed, a candidate is scored, a candidate is shortlisted, an interview is scheduled, or an email is sent.
- Displays the last 30 events per organization, refreshed every 10 seconds.
- Each event type has a distinct icon and colour.

### 📊 Job Progress Tracker
- A 5-stage visual pipeline tracker shown on every job card and the full Job Detail page:
  `JD Generated → Screening → Shortlisting → Interview → Final Decision`
- **Completed stages**: blue ✔ check icon.
- **Current active stage**: animated blue spinner.
- **Cancelled stage**: red ❌ X with "Cancelled here" label.
- **Pending stages**: grey empty circles.
- Uses the raw `pipeline_state` enum from the backend for pixel-precise accuracy.

### 👥 Team Management
- Admins can invite team members via email with a **signed invitation token** (7-day expiry).
- Invited users accept via a dedicated link and set their own password.
- Roles:
  - `admin` — full access: create jobs, invite team, view analytics, cancel/delete pipelines.
  - `interviewer` — scoped to "My Tasks": view assigned candidates, submit interview feedback.

### 🔐 Authentication
- JWT-based authentication with HS256 signing.
- Token contains: `user_id`, `role`, `organization_id`, and expiry.
- Axios interceptors auto-attach JWT to every request.
- 401 responses globally redirect to `/login` and clear local storage.

---

## 6. Hiring Pipeline Flow

```
Job Created
     │
     ▼
[1] JD_DRAFT ──────────────────── AI generates Job Description
     │
     ▼
[2] JD_APPROVAL_PENDING ───────── ⏸ HR reviews & approves/edits
     │
     ▼
[3] JD_APPROVED → JOB_POSTED ─── AI publishes JD to LinkedIn/job boards
     │
     ▼
[4] WAITING_FOR_APPLICATIONS ──── Candidates apply (PDF resume upload)
     │
     ▼
[5] SCREENING ─────────────────── AI parses, embeds, and scores each resume
     │
     ▼
[6] HR_REVIEW_PENDING ─────────── ⏸ HR reviews AI shortlist; can override
     │
     ▼
[7] INTERVIEW_SCHEDULED ───────── AI books Google Meet, sends calendar invites
     │
     ▼
[8] OFFER_SENT ────────────────── AI drafts & sends offer/rejection email

[At ANY stage] ─ Admin clicks "Cancel Pipeline" → pipeline stops immediately
```

---

## 7. Resume Scoring System

| Layer | Mechanism | Weight |
|:---|:---|:---|
| **Hard Filter** | Regex/rule-based: checks mandatory skills | Blocking |
| **Semantic Match** | Cosine similarity (OpenAI/Gemini embeddings) | 40% |
| **LLM Evaluation** | Chain-of-Thought: projects, depth, role-fit | 40% |
| **Screening Score** | Answers to custom screening questions | 20% |

Final output per candidate:
```json
{
  "score": 87,
  "pros": ["Strong Python background", "Led distributed systems"],
  "cons": ["No Kubernetes experience"],
  "recommendation": "Strongly Recommended"
}
```

---

## 8. Dashboard & UI

### Admin Dashboard
- **Hero Section**: Contextual call-to-action ("Resume Pipeline", "Review JD", "Check Shortlist") based on the furthest-pending job.
- **Stats Grid**: Live counters — Active Jobs, Total Applicants, Shortlisted, Interviews Scheduled.
- **Job Cards**: Each card shows title, department, applicant counts, and a compact 5-stage progress tracker.
- **Live Activity Feed**: Scrollable real-time log of pipeline events.
- **Pipeline Board**: Kanban-style view of all candidates bucketed by stage.
- **AI Insights**: Recommendations panel surfacing actionable hiring intelligence.

### Interviewer Dashboard
- **My Tasks**: Filtered view showing only candidates assigned to this interviewer.
- **Feedback Forms**: Quick-entry interview score and notes per candidate.

### Job Detail Page
- Full 5-stage progress tracker with cancel-point highlighting.
- Generated JD preview (or "Pipeline Cancelled" message if cancelled with no JD).
- Candidate list with AI scores, shortlist status, and interview slots.
- Interview Stages configuration panel.
- **Cancel AI Pipeline** button (shown for active jobs only).
- **Delete Job** button (shown only for cancelled jobs — navigates back to Dashboard after deletion).

---

## 9. Authentication & RBAC

| Route / Action | `admin` | `interviewer` |
|:---|:---:|:---:|
| Create Job | ✅ | ❌ |
| Cancel / Delete Pipeline | ✅ | ❌ |
| Invite Team Members | ✅ | ❌ |
| View All Jobs | ✅ | ❌ |
| View Assigned Candidates | ✅ | ✅ |
| Submit Interview Feedback | ✅ | ✅ |
| View Analytics | ✅ | ❌ |

---

## 10. Multi-Tenancy Design

All data is **organization-scoped**. The `get_current_user` FastAPI dependency injects `organization_id` into every DB query.

```
Organizations (1)
  └── Users (N) [admin | interviewer]
       └── Jobs (N)
            ├── Applications (N)
            │    └── Candidates (1)
            ├── Activities (N)       ← Live Feed events
            └── JobStages (N)
```

- No cross-organization data leakage is possible at the query level.
- Invitations are scoped to the inviting admin's organization.

---

## 11. API Reference

### Auth
| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/signup` | `POST` | Create organization + admin user |
| `/api/login` | `POST` | Authenticate; returns JWT |
| `/api/invite` | `POST` | Send invitation email to a new team member |
| `/api/accept-invite` | `POST` | Accept invite and set password |

### Jobs
| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/jobs` | `GET` | List all jobs (with `pipeline_state`, `is_cancelled`) |
| `/api/jobs` | `POST` | Create a new job and start the AI pipeline |
| `/api/jobs/{id}` | `GET` | Full job details including applications |
| `/api/jobs/{id}/cancel` | `POST` | Cancel active pipeline (preserves stage info) |
| `/api/jobs/{id}` | `DELETE` | Permanently delete a cancelled job |
| `/api/jobs/{id}/approve-jd` | `POST` | Approve or reject the AI-generated JD |

### Candidates & Applications
| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/jobs/{id}/apply` | `POST` | Submit a resume (PDF/TXT) for a job |
| `/api/candidates/{id}` | `GET` | Full candidate profile + AI score |
| `/api/hr-review/{id}` | `POST` | HR shortlist approval/rejection |

### Dashboard Data
| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/activity-feed` | `GET` | Latest 30 pipeline events for the org |
| `/api/pipeline-board` | `GET` | Candidates bucketed by Kanban stage |
| `/api/suggest` | `POST` | AI field suggestions during job creation |

---

## 12. Background Jobs

Celery + Redis power all async operations:

| Task | Trigger | Description |
|:---|:---|:---|
| Resume Scoring | On apply | Parallel PDF parsing + multi-layer scoring |
| Interview Scheduling | On shortlist approval | Calendar check + Meet link + invite emails |
| 7-Day Follow-up | Scheduled | Re-send interview invite to no-response candidates |
| LLM Retry | On API failure | Exponential backoff to secondary LLM provider |

---

## 13. Fault Tolerance

| Scenario | Behaviour |
|:---|:---|
| Server crash mid-pipeline | LangGraph resumes from last checkpoint on next request |
| LLM rate limit | `llm_factory` transparently switches Gemini → OpenAI → Ollama |
| Orphaned pipeline on restart | `startup_resume_orphaned_jobs` re-queues active jobs on boot |
| Pipeline cancelled mid-flow | `pipeline_state` frozen at cancellation stage; `is_cancelled` flag set |
| Browser refresh on job form | `localStorage` preserves unsaved draft fields |

---

## 14. Integrations

| Service | Usage |
|:---|:---|
| **Google Calendar API** | Read/write interview availability |
| **Google Meet** | Auto-generate meeting links |
| **LinkedIn API** | Programmatic job posting |
| **SMTP / Resend** | Transactional emails for all pipeline events |
| **PDF Parser** | Extract resume text for scoring |

---

## 15. Environment Variables

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/hiring_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
SECRET_KEY=your_super_secret_jwt_key_here

# LLMs
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key          # Optional fallback
OPENROUTER_API_KEY=your_openrouter_key  # Optional fallback

# Google
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Email
RESEND_API_KEY=your_resend_key
FROM_EMAIL=noreply@yourdomain.com
```

---

## 16. Frontend Structure

```
frontend/src/
├── pages/
│   ├── Dashboard.tsx        # Admin overview: stats, hero, job cards, activity feed
│   ├── JobDetail.tsx        # Job detail: JD, candidates, progress tracker, cancel/delete
│   ├── Login.tsx            # Auth page
│   ├── Signup.tsx           # Org + admin creation
│   ├── MyTasks.tsx          # Interviewer task queue
│   └── AcceptInvite.tsx     # Invitation acceptance flow
├── components/
│   ├── Sidebar.tsx          # Navigation with role-based menu items
│   ├── HeroSection.tsx      # Contextual action card for admins
│   ├── StatsGrid.tsx        # Live KPI counters
│   ├── ActivityFeed.tsx     # Real-time pipeline event log (10s polling)
│   ├── JobProgress.tsx      # 5-stage visual pipeline tracker
│   ├── PipelineBoard.tsx    # Kanban candidate view
│   ├── ActionCenter.tsx     # Quick actions panel
│   └── AiInsights.tsx       # AI recommendation cards
└── services/
    └── api.ts               # Axios client with JWT interceptors + all API methods
```

---

## 17. Future Improvements

- **Stripe Integration**: Usage-based billing per active job cycle.
- **Pipeline Resume**: Auto-resume interrupted pipelines when user logs back in (LangGraph checkpoints already persist state).
- **Video Interview AI**: Real-time sentiment analysis during Google Meet sessions.
- **Slack App**: Push notifications when a candidate reaches a new stage.
- **Custom Workflow Builder**: Drag-and-drop LangGraph node editor for custom hiring logic.
- **CSV Export**: Download candidate scoreboards per job.
- **Webhook Support**: Notify external ATS or HRIS systems on stage changes.

---

## License

MIT — built for the future of hiring.
