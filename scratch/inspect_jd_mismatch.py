
import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import select

async def main():
    print("🔍 [Stateless Audit] Checking JD content for the latest job...")
    async with AsyncSessionLocal() as session:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalar_one_or_none()
        
        if job:
            print(f"✅ FOUND JOB_ID: {job.id}")
            print(f"📌 TITLE: {job.title}")
            print(f"📄 JD_DRAFT PREVIEW (First 300 chars):\n{job.jd_draft[:300]}...")
            print("-" * 40)
            print(f"📜 FULL_JD PREVIEW (First 300 chars):\n{job.full_jd[:300] if job.full_jd else 'EMPTY'}...")
        else:
            print("❌ NO JOB FOUND.")

if __name__ == "__main__":
    asyncio.run(main())
