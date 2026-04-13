import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import text

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        print(f"🚀 Forcing definitive sync for {job_id}...")
        
        # We need to set state to SCREENING and result in 'active' status
        await session.execute(
            text("UPDATE jobs SET pipeline_state = 'SCREENING', status = 'PROCESSING', jd_approved = True WHERE id = :id"),
            {"id": job_id}
        )
        await session.commit()
        print("✅ [DASHBOARD_SYNC_SUCCESS] JD marked as complete, pipeline advanced to SCREENING.")

if __name__ == "__main__":
    asyncio.run(main())
