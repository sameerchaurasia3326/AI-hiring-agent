import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Application
from sqlalchemy import text, select, func

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        print(f"🛠️  Finalizing state for job {job_id}...")
        
        # 1. Force consistent state: Approved + Screening
        await session.execute(
            text("UPDATE jobs SET pipeline_state = 'SCREENING', status = 'PROCESSING', jd_approved = True WHERE id = :id"),
            {"id": job_id}
        )
        
        # 2. Check candidates
        res = await session.execute(
            select(func.count(Application.id)).where(Application.job_id == job_id)
        )
        count = res.scalar()
        print(f"👥 verified {count} candidates in pipeline.")
        
        await session.commit()
        print("✅ Pipeline definitively aligned. JD checkmark restored, SCREENING active.")

if __name__ == "__main__":
    asyncio.run(main())
