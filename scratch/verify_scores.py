
import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Candidate
from sqlalchemy import select
from sqlalchemy.orm import joinedload

async def main():
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    print(f"📊 [Verification] Checking applications for job_id: {job_id}")
    
    async with AsyncSessionLocal() as session:
        # Join Application with Candidate to get names
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.job_id == job_id)
        )
        res = await session.execute(stmt)
        apps = res.scalars().all()
        
        if not apps:
            print("❌ NO APPLICATIONS FOUND for this job.")
            return

        for app in apps:
            name = app.candidate.name if app.candidate else "Unknown"
            print(f"👤 Candidate: {name}")
            print(f"   - Scored: {app.is_scored}")
            print(f"   - Score: {app.score}")
            print(f"   - Stage: {app.stage}")
            print(f"   - Status: {app.status}")
            print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
