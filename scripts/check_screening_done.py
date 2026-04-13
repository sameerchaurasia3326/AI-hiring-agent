import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Job
from sqlalchemy import select, text, func

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        # Check if all 3 applications are scored
        res = await session.execute(
            select(func.count(Application.id))
            .where(Application.job_id == job_id, Application.is_scored == True)
        )
        scored_count = res.scalar()
        print(f"📊 Scored applications: {scored_count}/3")
        
        if scored_count >= 3:
            print("✅ Screening complete! Advancing to SHORTLISTING...")
            await session.execute(
                text("UPDATE jobs SET pipeline_state = 'SHORTLISTING' WHERE id = :id"),
                {"id": job_id}
            )
            await session.commit()
            print("🚀 Dashboard updated: SCREENING is now checkmarked.")
        else:
            print("⏳ Still waiting for AI to complete scoring...")

if __name__ == "__main__":
    asyncio.run(main())
