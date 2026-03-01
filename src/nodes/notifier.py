"""
src/nodes/notifier.py
──────────────────────
LangGraph Node: send_final_decision
─────────────────────────────────────
Second interrupt node — waits for HR's post-interview decision.
Invokes send_offer_letter_tool or send_rejection_email_tool (LangChain @tool)
for each candidate. NO routing logic inside node.
State: INTERVIEW_SCHEDULED → OFFER_SENT | CLOSED
"""
from __future__ import annotations

from langgraph.types import interrupt
from loguru import logger

from src.state.schema import HiringState, PipelineStatus
from src.tools.hiring_tools import send_offer_letter_tool, send_rejection_email_tool


def send_final_decision(state: HiringState) -> dict:
    """Interrupt for HR post-interview decision, then send offer/rejection via tools."""
    shortlist    = state.get("shortlist", [])
    job_title    = state.get("job_title", "the role")
    salary_range = state.get("salary_range", "Competitive")

    logger.info("⏸  [notifier] Interrupting for final HR decision...")

    # ── Interrupt: HR provides { selected_ids: [...] } via API ───────────────
    hr_response: dict = interrupt({
        "type":       "final_decision",
        "message":    "Interviews completed. Provide final candidate decisions.",
        "candidates": [{"id": c["candidate_id"], "name": c["name"]} for c in shortlist],
    })

    selected_ids = set(hr_response.get("selected_ids", []))
    updated = [dict(c) for c in shortlist]
    offer_count = 0

    for c in updated:
        if c["candidate_id"] in selected_ids:
            # ── Invoke: offer letter tool ─────────────────────────────────────
            send_offer_letter_tool.invoke({
                "candidate_email": c["email"],
                "candidate_name":  c["name"],
                "job_title":       job_title,
                "salary_range":    salary_range,
            })
            c["offer_sent"] = True
            offer_count += 1
        else:
            # ── Invoke: rejection email tool ──────────────────────────────────
            send_rejection_email_tool.invoke({
                "candidate_email": c["email"],
                "candidate_name":  c["name"],
                "job_title":       job_title,
            })
            c["rejected"] = True

    logger.success("✅ [notifier] {} offer(s) | {} rejection(s)", offer_count, len(updated) - offer_count)
    return {
        "shortlist":       updated,
        "pipeline_status": PipelineStatus.OFFER_SENT.value if offer_count else PipelineStatus.CLOSED.value,
    }
