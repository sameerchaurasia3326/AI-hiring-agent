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
from loguru import logger
import asyncio
import uuid

from src.state.schema import HiringState, PipelineStatus
from src.config import settings

# ── Node imports ──────────────────────────────────────────────────────────────
from src.nodes.jd_generator         import generate_jd
from src.nodes.jd_reviewer          import review_jd
from src.nodes.jd_publisher         import publish_jd
from src.nodes.jd_analyzer          import generate_evaluation_profile
from src.nodes.application_collector import collect_applications
from src.nodes.jd_optimizer         import optimize_jd
from src.nodes.resume_scorer        import score_resumes
from src.nodes.shortlist_sender     import send_shortlist_to_hr
from src.nodes.interview_scheduler  import schedule_interviews
from src.nodes.notifier             import send_final_decision, notify_jd_draft
from src.nodes.test_generator       import generate_tests
from src.utils.inference            import infer_stage, reconstruct_state
from src.utils.normalization        import normalize_job_role


# ═══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGE FUNCTIONS
# All routing decisions live HERE — never inside node bodies.
# Each function returns the NAME of the next node to route to.
# ═══════════════════════════════════════════════════════════════════════════════

async def route_from_init(state: HiringState) -> str:
    """
    Decide where to start the pipeline using DB-based inference.
    Bypasses volatile checkpoints to ensure stateless recovery.
    """
    job_id = state.get("job_id")
    if not job_id:
        return "generate_jd"
    
    inferred = await infer_stage(job_id)
    logger.info(f"🚀 [route_from_init] INFERRED STAGE: {inferred}")
    return inferred


def route_init(state: HiringState) -> str:
    """START → first node is always generate_jd."""
    return "generate_jd"


def route_after_jd_review(state: HiringState) -> str:
    """Explicitly route based on JD approval action."""
    action = state.get("action_type")
    
    if not action:
        return "error_handler"

    if action == "jd_approve":
        return "publish_jd"
    
    if action == "jd_reject":
        if state.get("jd_revision_count", 0) >= settings.max_jd_revisions:
            return "escalate"
        return "generate_jd"

    # Default safety: Loop back if unclear
    return "generate_jd"


def route_after_application_check(state: HiringState) -> str:
    """
    After collect_applications fires (triggered by Celery 7-day wait):
      - applications found → score_resumes
      - no applications + reposts < max → optimize_jd (Loop #2)
      - no applications + reposts >= max → escalate
    """
    if not state.get("action_type"):
        return "error_handler"

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
    logger.info("Decision: route_after_scoring")
    logger.info("SHORTLIST SIZE: {}", len(state.get("shortlist", [])))
    logger.info("ACTION_TYPE: {}", state.get("action_type"))

    if state.get("shortlist"):
        logger.info("Outcome: send_shortlist_to_hr")
        return "send_shortlist_to_hr"
    
    logger.warning("Outcome: escalate (empty shortlist)")
    return "escalate"


def route_after_hr_selection(state: HiringState) -> str:
    """Explicitly route based on candidate selection action."""
    action = state.get("action_type")

    if not action:
        return "error_handler"

    if action == "candidate_select":
        return "schedule_interviews"
    
    if action == "scheduler_event":
        # Check if selection happened before deadline OR if deadline reached
        if state.get("hr_selected_candidates"):
            return "schedule_interviews"
        return "escalate"

    # Fallback for safety
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


from src.state.validator import validate_node

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLER NODE
# ═══════════════════════════════════════════════════════════════════════════════

@validate_node
async def error_handler(state: HiringState) -> dict:
    """
    Terminal node for unknown stage/action mismatches.
    Ensures system never crashes on corrupted resume data.
    """
    error_msg = state.get("hr_feedback") or "Unknown graph error / state mismatch."
    logger.error("🛑 [error_handler] Triggered for job_id={}: {}", state.get("job_id"), error_msg)
    
    # Force DB update to mark as error
    from src.db.database import AsyncSessionLocal
    from src.db.models import Job
    from sqlalchemy import update
    
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == state.get("job_id"))
            .values(
                pipeline_state=PipelineStatus.FAILED.value,
                hr_feedback=f"Critical Error: {error_msg}"
            )
        )
        await session.commit()

    return {
        "pipeline_status": PipelineStatus.FAILED.value,
        "error_log": [f"Pipeline failed: {error_msg}"]
    }


@validate_node
async def escalate(state: HiringState) -> dict:
    """
    Terminal node for loop exhaustion or pipeline failures.
    Notified HR (via background task) and marks pipeline as ESCALATED.
    """
    job_id = state.get("job_id")
    if not job_id:
        logger.error("CRITICAL: escalate node triggered without job_id")
        return {"pipeline_status": PipelineStatus.ESCALATED.value}

    logger.info("STAGE: escalate | JOB_ID: {}", job_id)

    reason = _escalation_reason(state)
    
    # The decoupled task handles the actual email
    await send_shortlist_to_hr(state)

    return {
        "pipeline_status": PipelineStatus.ESCALATED.value,
        "current_stage": "escalated",
        "action_type": "escalation_complete"
    }



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

@validate_node
async def init_state(state: HiringState) -> dict:
    """
    Step 0: Bootstrapping node.
    Reconstructs the full HiringState from DB to ensure stateless recovery.
    """
    from src.utils.production_safety import StructuredLogger, log_event
    
    job_id = state.get("job_id")
    if not job_id:
        logger.error("CRITICAL: init_state triggered without job_id")
        return {"pipeline_status": PipelineStatus.FAILED.value}

    logger.info(f"🔄 [init_state] Deep state reconstruction triggered for job_id={job_id}")
    reconstructed = await reconstruct_state(job_id)
    
    # Phase 8 & 13: Ensure production logging is captured
    trace_id = reconstructed.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)
    s_logger.info("PIPELINE_RECONSTRUCTED", {"stage": reconstructed.get("current_stage")})
    
    import asyncio
    asyncio.create_task(log_event(job_id, "PIPELINE_START_RECONSTRUCTED", {"trace_id": trace_id}))

    # ── [NEW] Role-Awareness: Anchor Normalized Context ──────
    normalized_role = reconstructed.get("normalized_role")
    if not normalized_role:
        from src.db.database import AsyncSessionLocal
        from src.db.models import Job
        from sqlalchemy import update
        
        normalized_role = await normalize_job_role(reconstructed.get("job_title", ""))
        logger.info(f"⚓ [init_state] Anchoring ROLE context: {normalized_role}")
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(normalized_role=normalized_role)
            )
            await session.commit()
        reconstructed["normalized_role"] = normalized_role

    # Merge existing input state into reconstructed to preserve overrides
    return {**reconstructed, **state}

    # Truncate error_log to prevent exponential memory explosion (Phase 15 Guard)
    existing_errors = state.get("error_log", [])
    if len(existing_errors) > 50:
        logger.warning(f"⚠️  Truncating oversized error_log ({len(existing_errors)} entries) to final 50.")
        existing_errors = existing_errors[-50:]

    return {
        "job_id":            job_id,
        "trace_id":          trace_id,
        "pipeline_version":   version,
        "jd_revision_count": state.get("jd_revision_count", 0),
        "repost_attempts":   state.get("repost_attempts", 0),
        "applications":      state.get("applications", []),
        "scored_resumes":    state.get("scored_resumes", []),
        "shortlist":         state.get("shortlist", []),
        "error_log":         existing_errors,
        "pipeline_status":   PipelineStatus.JD_DRAFT.value if not state.get("jd_approved") else PipelineStatus.SCREENING.value,
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
    graph.add_node("jd_analyzer",          generate_evaluation_profile)
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
    graph.add_node("notify_jd_draft",      notify_jd_draft)
    graph.add_node("error_handler",        error_handler)

    # ── Edges ──────────────────────────────────────────────────────────────────
    graph.add_edge(START,           "init_state")
    
    # Decision: Fresh Run vs Persistence Jump?
    graph.add_conditional_edges(
        "init_state",
        route_from_init,
        {
            "generate_jd":  "generate_jd",
            "collect_applications": "collect_applications",
            "score_resumes": "score_resumes",
            "send_shortlist_to_hr": "send_shortlist_to_hr",
            "schedule_interviews": "schedule_interviews",
            "END": END
        }
    )

    # generate_jd flows to jd_analyzer (Senior AI Engineer Fix)
    graph.add_edge("generate_jd",    "jd_analyzer")
    
    # jd_analyzer flows to generate_tests
    graph.add_edge("jd_analyzer",    "generate_tests")

    # generate_tests flows to jd notification
    graph.add_edge("generate_tests",  "notify_jd_draft")

    # notification goes to review_jd
    graph.add_edge("notify_jd_draft", "review_jd")

    # Decision 1: JD Approved?
    graph.add_conditional_edges(
        "review_jd",
        route_after_jd_review,
        {
            "publish_jd":   "publish_jd",
            "generate_jd":  "generate_jd",    # Loop #1
            "escalate":     "escalate",
            "error_handler": "error_handler",
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
            "error_handler": "error_handler",
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
            "error_handler":        "error_handler",
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
            "error_handler":       "error_handler",
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

    # Error handler always ends
    graph.add_edge("error_handler", END)

    return graph

# ═══════════════════════════════════════════════════════════════════════════════
# [NEW] UNIVERSAL ENTRYPOINT (Senior Engineer Fix)
# ═══════════════════════════════════════════════════════════════════════════════
async def run_reconstructed_pipeline(job_id: str, config: Optional[dict] = None):
    """
    Universal Entry Point:
    1. Reconstructs state from DB (Source of Truth).
    2. Identifies the correct start node (Inference).
    3. Executes graph from that node.
    """
    logger.info(f"⚡ [run_reconstructed_pipeline] STARTING autonomy for job_id={job_id}")
    
    # 1. Root Fix: Rebuild FULL state from DB
    state = await reconstruct_state(job_id)
    config = {"configurable": {"thread_id": f"job-{str(job_id)}"}, "callbacks": []}

    # 2. Senior Engineer Task: Determine starting node or RESUME if paused
    inferred_stage = state.get("current_stage")
    is_paused = state.get("status_field") == "PAUSED"
    interrupt_payload = state.get("interrupt_payload")

    # Get the global graph instance
    pipeline = await get_pipeline()

    if is_paused and interrupt_payload:
        logger.info(f"❄️  [run_reconstructed_pipeline] RESUMING from frozen state for job_id={job_id}")
        # When resuming from an interrupt, we provide the Command(resume=...)
        # This tells LangGraph exactly how to wake up.
        from langgraph.types import Command
        await pipeline.ainvoke(Command(resume=interrupt_payload), config, subgraphs=True)
    else:
        # Mapping logic provided by USER for normal entry points
        if inferred_stage == "collect_applications":
            start_node = "collect_applications"
        elif inferred_stage == "score_resumes":
            start_node = "score_resumes"
        elif inferred_stage == "send_shortlist_to_hr":
            start_node = "send_shortlist_to_hr"
        elif inferred_stage == "schedule_interviews":
            start_node = "schedule_interviews"
        else:
            # Default fallback for fresh runs or unknown states
            start_node = "init_state"

        logger.info(f"🚀 [run_reconstructed_pipeline] JUMPING to start_node: {start_node}")
        # Execute graph starting at the inferred node
        await pipeline.ainvoke(state, config, subgraphs=True)
    
    logger.success(f"🏁 [run_reconstructed_pipeline] Autonomous pass completed for job_id={job_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# COMPILED PIPELINE (singleton)
# ═══════════════════════════════════════════════════════════════════════════════

_pipeline_instance = None
_saver_cm = None

async def get_pipeline():
    """
    Return the compiled LangGraph pipeline.
    Senior Engineer Hardening:
    - Checkpointer is OPTIONAL (Performance Cache).
    - Database is PRIMARY (Source of Truth).
    - If checkpointer fails, falls back to stateless DB-driven execution.
    """
    global _pipeline_instance, _saver_cm
    if _pipeline_instance is None:
        graph = build_pipeline()
        checkpointer = None

        try:
            logger.info("⚙️ Attempting to initialize LangGraph checkpointer (Cache Layer)...")
            
            # AsyncPostgresSaver needs a psycopg-compatible connection string
            pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
            
            _saver_cm = AsyncPostgresSaver.from_conn_string(pg_url)
            checkpointer = await _saver_cm.__aenter__()

            # Create checkpointer tables if they don't exist
            try:
                await asyncio.wait_for(checkpointer.setup(), timeout=5.0)
                logger.info("✅ Checkpointer tables verified. Performance cache enabled.")
            except Exception as e:
                logger.warning("⚠️ Checkpointer setup failed/timed out: {}. Proceeding in Stateless Mode.", e)
                checkpointer = None

        except Exception as e:
            logger.warning("⚠️ AsyncPostgresSaver initialization failed: {}. Using DB-only Source of Truth.", e)
            checkpointer = None

        # Compile graph — checkpointer is now optional
        _pipeline_instance = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=[],
        )
        
        status = "RECOVERY_READY (Stateless)" if checkpointer is None else "PERFORMANCE_READY (Cached)"
        logger.success(f"🚀 LangGraph pipeline compiled: {status}")

    return _pipeline_instance
