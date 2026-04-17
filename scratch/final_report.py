
import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Application, Candidate
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

async def main():
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    print(f"🏁 [DEFINITIVE REPORT] Auditing System State for Job: {job_id}")
    print("=" * 60)
    
    async with AsyncSessionLocal() as session:
        # 1. Job Config
        job_stmt = select(Job).where(Job.id == job_id)
        job = (await session.execute(job_stmt)).scalar()
        
        if not job:
            print("❌ ERROR: Job not found in database.")
            return

        print(f"📌 TITLE: {job.title}")
        print(f"📌 SKILLS: {job.required_skills}")
        print(f"📄 JD Draft (Start): {job.jd_draft[:150]}...")
        print("-" * 60)

        # 2. Candidate Status
        app_stmt = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.job_id == job_id)
        )
        apps = (await session.execute(app_stmt)).scalars().all()
        
        print(f"📊 APPLICATION STATUS ({len(apps)} total):")
        for app in apps:
            name = app.candidate.name if app.candidate else "Unknown"
            print(f"👤 {name}:")
            print(f"   - Scored: {app.is_scored}")
            print(f"   - Final Score: {app.score}")
            print(f"   - AI Reasoning: {app.ai_reasoning[:150] if app.ai_reasoning else 'None'}...")
            print(f"   - Current Stage: {app.stage}")
            print(f"   - Rejected: {app.rejected}")
            print("-" * 30)

        # 3. Inference Verification
        from src.utils.inference import infer_stage
        next_step = await infer_stage(job_id)
        print(f"🚀 INFERRED NEXT STEP: {next_step}")

if __name__ == "__main__":
    asyncio.run(main())
