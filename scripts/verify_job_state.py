import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import text

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT title, pipeline_state, jd_approved FROM jobs WHERE id = :id"), 
            {"id": job_id}
        )
        job = res.first()
        if job:
            print(f"📌 JOB: '{job.title}' | STATE: {job.pipeline_state} | APPROVED: {job.jd_approved}")
            
            if job.pipeline_state == "JD_APPROVAL_PENDING" and job.jd_approved:
                print("🔄 State is stuck at PENDING but APPROVED=True. Advancing to WAITING_FOR_APPLICATIONS...")
                await session.execute(
                    text("UPDATE jobs SET pipeline_state = 'WAITING_FOR_APPLICATIONS' WHERE id = :id"),
                    {"id": job_id}
                )
                await session.commit()
                print("✅ [SYNC_COMPLETE] Progress advanced.")
        else:
            print("❌ Job not found.")

if __name__ == "__main__":
    asyncio.run(main())
