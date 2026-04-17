
import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Application
from sqlalchemy import select, func

async def main():
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    print(f"📊 [Audit] Checking job: {job_id}")
    
    async with AsyncSessionLocal() as session:
        # Check unscored count
        unscored_stmt = select(func.count(Application.id)).where(
            Application.job_id == job_id,
            Application.is_scored == False
        )
        unscored_res = await session.execute(unscored_stmt)
        unscored = unscored_res.scalar()

        # Check scored count
        scored_stmt = select(func.count(Application.id)).where(
            Application.job_id == job_id,
            Application.is_scored == True
        )
        scored_res = await session.execute(scored_stmt)
        scored = scored_res.scalar()

        print(f"✅ Result for {job_id}:")
        print(f"   - UNSCORED Candidates: {unscored}")
        print(f"   - SCORED Candidates: {scored}")

        if unscored > 0:
            print("💡 Observation: infer_stage SHOULD return 'score_resumes'.")
        elif scored > 0:
            print("💡 Observation: infer_stage might be skipping to 'send_shortlist_to_hr'.")

if __name__ == "__main__":
    asyncio.run(main())
