import asyncio
import sys
import os
import argparse
import uuid
from loguru import logger

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Job
from src.state.schema import PipelineStatus
from sqlalchemy import update

async def reset_job(job_id: str):
    """Resets a failed job to JD_DRAFT state so it can be re-run."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(
                    pipeline_state=PipelineStatus.JD_DRAFT.value,
                    hr_feedback=None,
                    locked_by=None,
                    locked_at=None
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount > 0:
                print(f"✅ Job {job_id} successfully reset to JD_DRAFT.")
                print("🚀 It should now appear in your dashboard. You can re-trigger it from the UI or it will resume shortly.")
            else:
                print(f"⚠️  Job {job_id} not found in database.")
                
    except Exception as e:
        print(f"❌ Failed to reset job: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset a FAILED Hiring.AI job to JD_DRAFT.")
    parser.add_argument("--job_id", required=True, help="UUID of the job to reset")
    args = parser.parse_args()
    
    asyncio.run(reset_job(args.job_id))
