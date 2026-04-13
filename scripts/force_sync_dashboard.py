import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        print(f"🚀 Forcing dashboard sync for job {job_id}...")
        
        # Manually advance the state and mark as approved
        await session.execute(
            text("UPDATE jobs SET pipeline_state = 'WAITING_FOR_APPLICATIONS', jd_approved = True WHERE id = :id"),
            {"id": job_id}
        )
        await session.commit()
        print("✅ [DASHBOARD_SYNCED] Blue tick restored, progress advanced.")

if __name__ == "__main__":
    asyncio.run(main())
