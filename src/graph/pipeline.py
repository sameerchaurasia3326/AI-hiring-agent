"""
src/graph/pipeline.py
──────────────────────
THE LANGGRAPH PIPELINE — The central state machine graph.

Architecture principles:
  ✅ Every action = a LangGraph node
  ✅ Every decision = a conditional edge function (route_*)
  ✅ Tools = LangChain @tool, called via .invoke() inside nodes
  ✅ No Python if/else routing inside node bodies
  ✅ All loop guards live HERE as edge conditions
  ✅ Human-in-the-loop via LangGraph interrupt()
  ✅ Time waits via Celery tasks (non-blocking)
  ✅ State persisted across restarts via Postgres checkpointer

Graph nodes:
  init_state            ── initialise the run
  generate_jd           ── LLM: draft/revise JD
  review_jd             ── INTERRUPT: wait for HR JD approval
  publish_jd            ── post JD + fire 7-day Celery timer
  collect_applications  ── scan intake dir for resumes
  optimize_jd           ── LLM: rewrite JD to get more applicants
  score_resumes         ── LLM: score + shortlist candidates
  send_shortlist_to_hr  ── email shortlist + fire 2-day Celery timer
  schedule_interviews   ── book calendar + send invites
  send_final_decision   ── INTERRUPT: offer / rejection emails
  escalate              ── notify HR of loop exhaustion
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.state.schema import HiringState, PipelineStatus
from src.config import settings

# ── Node imports ──────────────────────────────────────────────────────────────
from src.nodes.jd_generator         import generate_jd
from src.nodes.jd_reviewer          import review_jd
from src.nodes.jd_publisher         import publish_jd
from src.nodes.application_collector import collect_applications
from src.nodes.jd_optimizer         import optimize_jd
from src.nodes.resume_scorer        import score_resumes
from src.nodes.shortlist_sender     import send_shortlist_to_hr
from src.nodes.interview_scheduler  import schedule_interviews
from src.nodes.notifier             import send_final_decision
from src.nodes.test_generator       import generate_tests


# ═══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGE FUNCTIONS
# All routing decisions live HERE — never inside node bodies.
# Each function returns the NAME of the next node to route to.
# ═══════════════════════════════════════════════════════════════════════════════

def route_init(state: HiringState) -> str:
    """START → first node is always generate_jd."""
    return "generate_jd"


def route_after_jd_review(state: HiringState) -> str:
    """
    After HR reviews the JD:
      - approved           → publish_jd
      - !approved + revisions < max → generate_jd (loop back)
      - !approved + revisions >= max → escalate
    """
    if state.get("jd_approved"):
        return "publish_jd"
    if state.get("jd_revision_count", 0) >= settings.max_jd_revisions:
        return "escalate"
    return "generate_jd"


def route_after_application_check(state: HiringState) -> str:
    """
    After collect_applications fires (triggered by Celery 7-day wait):
      - applications found → score_resumes
      - no applications + reposts < max → optimize_jd (Loop #2)
      - no applications + reposts >= max → escalate
    """
    has_applications = len(state.get("applications", [])) > 0
    if has_applications:
        return "score_resumes"
    if state.get("repost_attempts", 0) >= settings.max_repost_attempts:
        return "escalate"
    return "optimize_jd"


def route_after_optimize_jd(state: HiringState) -> str:
    """
    After JD is optimized for reposting:
      - go back through JD approval loop (reset revision count was done in node)
    """
    return "generate_jd"


def route_after_scoring(state: HiringState) -> str:
    """
    After resume scoring:
      - shortlist has candidates → send_shortlist_to_hr
      - empty shortlist          → escalate (no one qualified)
    """
    if state.get("shortlist"):
        return "send_shortlist_to_hr"
    return "escalate"


def route_after_hr_selection(state: HiringState) -> str:
    """
    After HR review period expires (2-day Celery wait):
      - HR selected candidates → schedule_interviews
      - HR did not respond     → escalate (close pipeline)
    """
    if state.get("hr_selected_candidates"):
        return "schedule_interviews"
    return "escalate"


def route_after_final_decision(state: HiringState) -> str:
    """
    After offer/rejection emails sent:
      - any offers sent → END
      - all rejected    → END
    Always ends; status already stored in DB.
    """
    return END


def route_escalate(state: HiringState) -> str:
    """Escalate always terminates the pipeline."""
    return END


# ═══════════════════════════════════════════════════════════════════════════════
# ESCALATION NODE
# ═══════════════════════════════════════════════════════════════════════════════

from src.tools.hiring_tools import send_hr_notification_tool

def escalate(state: HiringState) -> dict:
    """
    Terminal node for loop exhaustion or pipeline failures.
    Notifies HR and marks pipeline as ESCALATED.
    """
    reason = _escalation_reason(state)

    send_hr_notification_tool.invoke({
        "hr_email":  state.get("hiring_manager_email", settings.hr_email),
        "subject":   f"[Hiring AI] ⚠️ Pipeline Escalated — {state.get('job_title', 'Role')}",
        "html_body": f"""
<h2>⚠️ Hiring Pipeline Escalated</h2>
<p><strong>Job:</strong> {state.get('job_title')}</p>
<p><strong>Reason:</strong> {reason}</p>
<p>Please review and take manual action.</p>
<ul>
  <li>JD Revisions: {state.get('jd_revision_count', 0)}/{settings.max_jd_revisions}</li>
  <li>Repost Attempts: {state.get('repost_attempts', 0)}/{settings.max_repost_attempts}</li>
  <li>Applications received: {len(state.get('applications', []))}</li>
  <li>Shortlisted: {len(state.get('shortlist', []))}</li>
</ul>
""",
    })

    return {"pipeline_status": PipelineStatus.ESCALATED.value}


def _escalation_reason(state: HiringState) -> str:
    if state.get("jd_revision_count", 0) >= settings.max_jd_revisions:
        return f"Maximum JD revisions ({settings.max_jd_revisions}) reached without HR approval."
    if state.get("repost_attempts", 0) >= settings.max_repost_attempts:
        return f"Maximum repost attempts ({settings.max_repost_attempts}) reached with no applications."
    if not state.get("shortlist"):
        return "No candidates met the scoring threshold."
    if not state.get("hr_selected_candidates"):
        return "HR did not select any candidates within the 2-day review window."
    return "Unknown pipeline failure."


# ═══════════════════════════════════════════════════════════════════════════════
# INIT NODE
# ═══════════════════════════════════════════════════════════════════════════════

def init_state(state: HiringState) -> dict:
    """Initialise defaults for a fresh pipeline run."""
    return {
        "jd_revision_count": state.get("jd_revision_count", 0),
        "repost_attempts":   state.get("repost_attempts", 0),
        "applications":      state.get("applications", []),
        "scored_resumes":    state.get("scored_resumes", []),
        "shortlist":         state.get("shortlist", []),
        "error_log":         state.get("error_log", []),
        "pipeline_status":   PipelineStatus.JD_DRAFT.value,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD THE GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

def build_pipeline() -> StateGraph:
    """
    Construct and compile the LangGraph StateGraph.

    Node map:
      START
        → init_state
          → generate_jd
            → review_jd  [INTERRUPT]
              ├─ approved          → publish_jd
              ├─ rejected < max    → generate_jd        (Loop #1)
              └─ rejected >= max   → escalate
                → publish_jd
                  → collect_applications
                    ├─ apps found  → score_resumes
                    ├─ no apps < max   → optimize_jd → generate_jd  (Loop #2)
                    └─ no apps >= max  → escalate
                      → score_resumes
                        ├─ shortlist → send_shortlist_to_hr
                        └─ empty     → escalate
                          → send_shortlist_to_hr
                            → schedule_interviews  [route on hr_selected_candidates]
                              └─ none selected → escalate
                              → schedule_interviews
                                → send_final_decision  [INTERRUPT]
                                  → END
      escalate → END
    """
    graph = StateGraph(HiringState)

    # ── Register nodes ─────────────────────────────────────────────────────────
    graph.add_node("init_state",           init_state)
    graph.add_node("generate_jd",          generate_jd)
    graph.add_node("generate_tests",       generate_tests)
    graph.add_node("review_jd",            review_jd)
    graph.add_node("publish_jd",           publish_jd)
    graph.add_node("collect_applications", collect_applications)
    graph.add_node("optimize_jd",          optimize_jd)
    graph.add_node("score_resumes",        score_resumes)
    graph.add_node("send_shortlist_to_hr", send_shortlist_to_hr)
    graph.add_node("schedule_interviews",  schedule_interviews)
    graph.add_node("send_final_decision",  send_final_decision)
    graph.add_node("escalate",             escalate)

    # ── Edges ──────────────────────────────────────────────────────────────────
    graph.add_edge(START,           "init_state")
    graph.add_edge("init_state",    "generate_jd")

    # generate_jd flows to generate_tests
    graph.add_edge("generate_jd",    "generate_tests")

    # generate_tests always goes to review_jd
    graph.add_edge("generate_tests",  "review_jd")

    # Decision 1: JD Approved?
    graph.add_conditional_edges(
        "review_jd",
        route_after_jd_review,
        {
            "publish_jd":   "publish_jd",
            "generate_jd":  "generate_jd",    # Loop #1
            "escalate":     "escalate",
        },
    )

    # publish_jd fires Celery timer; graph is paused until scheduler resumes it
    graph.add_edge("publish_jd", "collect_applications")

    # Decision 2: Applications received?
    graph.add_conditional_edges(
        "collect_applications",
        route_after_application_check,
        {
            "score_resumes": "score_resumes",
            "optimize_jd":   "optimize_jd",   # Loop #2
            "escalate":      "escalate",
        },
    )

    # optimize_jd sends back to JD loop
    graph.add_conditional_edges(
        "optimize_jd",
        route_after_optimize_jd,
        {"generate_jd": "generate_jd"},
    )

    # Decision: shortlist non-empty?
    graph.add_conditional_edges(
        "score_resumes",
        route_after_scoring,
        {
            "send_shortlist_to_hr": "send_shortlist_to_hr",
            "escalate":             "escalate",
        },
    )

    # send_shortlist fires Celery 2-day timer; graph pauses for HR
    # Decision 3: HR selected candidates?
    graph.add_conditional_edges(
        "send_shortlist_to_hr",
        route_after_hr_selection,
        {
            "schedule_interviews": "schedule_interviews",
            "escalate":            "escalate",
        },
    )

    # schedule_interviews always goes to final decision
    graph.add_edge("schedule_interviews", "send_final_decision")

    # Decision 4: Offer / rejection sent → END
    graph.add_conditional_edges(
        "send_final_decision",
        route_after_final_decision,
        {END: END},
    )

    # Escalation always ends
    graph.add_conditional_edges(
        "escalate",
        route_escalate,
        {END: END},
    )

    return graph


# ═══════════════════════════════════════════════════════════════════════════════
# COMPILED PIPELINE (singleton)
# ═══════════════════════════════════════════════════════════════════════════════

_pipeline_instance = None
_saver_cm = None

async def get_pipeline():
    """
    Return the compiled LangGraph pipeline with async Postgres checkpointer.
    Singleton — created once per process.
    """
    global _pipeline_instance, _saver_cm
    if _pipeline_instance is None:
        graph = build_pipeline()

        # AsyncPostgresSaver needs a psycopg-compatible connection string
        # (psycopg doesn't like the +asyncpg dialect prefix)
        pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _saver_cm = AsyncPostgresSaver.from_conn_string(pg_url)
        checkpointer = await _saver_cm.__aenter__()

        # Create checkpointer tables if they don't exist
        await checkpointer.setup()

        _pipeline_instance = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=[],
        )

    return _pipeline_instance
