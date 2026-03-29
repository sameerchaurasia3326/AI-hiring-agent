"""
src/nodes/application_collector.py
────────────────────────────────────
LangGraph Node: collect_applications
──────────────────────────────────────
Reads resumes from intake directory and returns ApplicationRecord list.
NO routing — graph edge (route_after_application_check) decides next step.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from datetime import datetime, timezone

from loguru import logger
from langgraph.types import interrupt

from src.config import settings
from src.state.schema import HiringState, ApplicationRecord, PipelineStatus
from src.utils.activity import log_activity_sync

_SUPPORTED_EXT = {".pdf", ".docx", ".doc", ".txt"}


def collect_applications(state: HiringState) -> dict:
    """Scan RESUME_INTAKE_DIR and return any new ApplicationRecords."""
    intake = Path(settings.resume_intake_dir)
    intake.mkdir(parents=True, exist_ok=True)

    existing = {a["resume_path"] for a in state.get("applications", [])}
    new_apps: list[ApplicationRecord] = []

    for f in intake.iterdir():
        if f.suffix.lower() not in _SUPPORTED_EXT or str(f) in existing:
            continue
        stem = f.stem.replace("_", " ").replace("-", " ").title()
        parts = [p for p in stem.split() if p.lower() not in {"resume", "cv"}]
        new_apps.append({
            "candidate_id": uuid.uuid4().hex,
            "name":         " ".join(parts) or stem,
            "email":        f"{f.stem.lower()}@example.com",
            "resume_path":  str(f),
            "applied_at":   datetime.now(timezone.utc).isoformat(),
        })
        
        job_id = state.get("job_id", "")
        if job_id:
            log_activity_sync(job_id, message=f"Resume uploaded for {' '.join(parts) or stem}", type="resume_uploaded")

    all_apps = state.get("applications", []) + new_apps
    logger.info("📥 [collect_applications] {} total ({} new)", len(all_apps), len(new_apps))

    # ── Wait State Logic ──────────────────────────────────────────────────────
    # If no applications found, and no scheduler event (7-day timer) has fired,
    # we MUST interrupt to pause the graph.
    if not all_apps and not state.get("scheduler_event"):
        logger.info("⏸ [collect_applications] No resumes found. Pausing for application window.")
        # The value returned by interrupt() is what the scheduler/resume caller provides
        interrupt_val = interrupt({
            "type": "waiting_for_applications",
            "job_id": state.get("job_id"),
            "organization_id": state.get("organization_id")
        })
        # If we were resumed with a scheduler event, it will be in the state next time
        if interrupt_val:
            return {"scheduler_event": interrupt_val}

    return {
        "applications":    new_apps,
        "pipeline_status": (
            PipelineStatus.SCREENING.value if all_apps
            else PipelineStatus.WAITING_FOR_APPLICATIONS.value
        ),
    }
