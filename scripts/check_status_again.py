import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import text

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT title, pipeline_state, jd_approved, status FROM jobs WHERE id = :id"), 
            {"id": job_id}
        )
        job = res.first()
        if job:
            print(f"📌 DB STATE: {job.pipeline_state} | APPROVED: {job.jd_approved} | COMPUTED STATUS: {job.status}")
        else:
            print("❌ Job not found.")

if __name__ == "__main__":
    asyncio.run(main())
