import asyncio
import sys
import os
import json
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from src.db.database import AsyncSessionLocal
from src.db.models import EventStore, Job
from loguru import logger

async def replay_job(job_id: str):
    logger.info(f"🧐 Reconstructing lineage for Job: {job_id}")
    
    async with AsyncSessionLocal() as session:
        # 1. Fetch Job basic info
        job_res = await session.execute(select(Job).where(Job.id == job_id))
        job = job_res.scalar_one_or_none()
        if not job:
            logger.error("❌ Job not found.")
            return

        print(f"\n{'='*60}")
        print(f" JOB LINEAGE: {job.title}")
        print(f" Status: {job.pipeline_state}")
        print(f" Version: {job.pipeline_version}")
        print(f"{'='*60}\n")

        # 2. Fetch all events strictly ordered by sequence (Phase 15 & Request)
        stmt = (
            select(EventStore)
            .where(EventStore.job_id == job_id)
            .order_by(EventStore.sequence.asc())
        )

        res = await session.execute(stmt)
        events = res.scalars().all()

        if not events:
            print(" No events found in Event Store for this job.")
            return

        for i, event in enumerate(events, 1):
            ts = event.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{i:02d}] {ts} | {event.event_type:25} | {json.dumps(event.payload)}")

        print(f"\n{'='*60}")
        print(f" Total Events: {len(events)}")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/replay_job_state.py <job_id>")
        sys.exit(1)
    
    asyncio.run(replay_job(sys.argv[1]))
