
import asyncio
import uuid
import sys
from loguru import logger
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import select
from src.graph.pipeline import run_reconstructed_pipeline

async def main():
    logger.info("📡 [Trigger Script] Starting autonomous pipeline pass...")
    
    async with AsyncSessionLocal() as session:
        # Get the most recent job
        stmt = select(Job).order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalar_one_or_none()
        
        if not job:
            logger.error("❌ [Trigger Script] No jobs found in database.")
            return

        # Use a fresh thread ID to bypass stale 186-candidate checkpoints
        # and use our newly hardened 'Replace' state logic.
        thread_id = f"fresh_pass_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}

        job_id = str(job.id)
        logger.info(f"🎯 [Trigger Script] Target Job ID: {job_id} ({job.title})")

    # Launch the resilient pipeline engine
    try:
        await run_reconstructed_pipeline(job_id, config=config)
        logger.success("🏁 [Trigger Script] Autonomous pass successfully initiated.")
    except Exception as e:
        logger.exception(f"❌ [Trigger Script] Pipeline initiation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
