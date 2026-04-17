"""
src/nodes/application_collector.py
────────────────────────────────────
LangGraph Node: collect_applications
──────────────────────────────────────
Production Hardened:
1. Atomic Lease Guard (Phase 1).
2. Safe Tool Execution (Phase 10).
3. Structured Logging (Phase 14).
"""
from __future__ import annotations

import os
from loguru import logger
from datetime import datetime, timezone

from src.state.schema import HiringState, PipelineStatus
from src.state.validator import validate_node
from src.utils.production_safety import lease_guard, StructuredLogger, log_event, safe_tool_call

@validate_node
@lease_guard
async def collect_applications(state: HiringState) -> dict:
    """
    Collects applications from various sources.
    Phase 10: Uses safe_tool_call for external IO/Scraping.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)

    if not job_id:
        return state

    s_logger.info("APPLICATION_COLLECTION_STARTED")
    await log_event(job_id, "APPLICATION_COLLECTION_STARTED")

    job_title = state.get("job_title", "Job")
    
    # In this implementation, we assume applications are already in a local directory
    # linked to the job. A real production system would trigger a scraper tool here.
    
    # Mocking external collection with a safe wrapper
    async def _mock_scrape():
        # logic to fetch from LinkedIn/Indeed/Email
        return []

    collected = await safe_tool_call(_mock_scrape)
    if collected is None:
        s_logger.warning("COLLECTION_INTERRUPTED", {"reason": "safe_tool_captured_error"})
        collected = []

    # Current local logic: check for candidates already in state
    current_apps = state.get("applications", [])
    
    s_logger.info("APPLICATION_COLLECTION_COMPLETED", {"new_count": len(collected), "total_count": len(current_apps)})
    await log_event(job_id, "APPLICATION_COLLECTION_FINISHED", {"count": len(current_apps)})

    return {
        "applications": current_apps,
        "pipeline_status": PipelineStatus.SCREENING.value,
    }
