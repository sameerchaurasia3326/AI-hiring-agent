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

from src.config import settings
from src.state.schema import HiringState, ApplicationRecord, PipelineStatus

_SUPPORTED_EXT = {".pdf", ".docx", ".doc"}


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

    all_apps = state.get("applications", []) + new_apps
    logger.info("📥 [collect_applications] {} total ({} new)", len(all_apps), len(new_apps))

    return {
        "applications":    all_apps,
        "pipeline_status": (
            PipelineStatus.SCREENING.value if all_apps
            else PipelineStatus.WAITING_FOR_APPLICATIONS.value
        ),
    }
