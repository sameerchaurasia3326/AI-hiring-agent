
import asyncio
from sqlalchemy import select
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Candidate, Job

async def verify():
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    async with AsyncSessionLocal() as session:
        # Check Job Title
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
        print(f"🎯 Job Title: {job.title if job else 'NOT FOUND'}")
        
        # Check applications
        stmt = (
            select(Candidate.name, Application.is_scored, Application.score)
            .join(Application, Application.candidate_id == Candidate.id)
            .where(Application.job_id == job_id)
            .order_by(Application.score.desc())
        )
        results = (await session.execute(stmt)).all()
        
        print(f"\n📊 Screening Results for {len(results)} Candidates:")
        for name, is_scored, score in results:
            status = "✅ SCORED" if is_scored else "⏳ PENDING"
            print(f"  - {name}: {status} | Score: {score}")

if __name__ == "__main__":
    asyncio.run(verify())
