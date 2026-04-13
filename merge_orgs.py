import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Candidate, Application, Interview, Activity, InterviewFeedback
from sqlalchemy import update

async def merge_organizations():
    OLD_ORG_ID = "73353b4b-6f88-4a11-9df5-9a376b59b5a7"
    NEW_ORG_ID = "6705065f-28e0-4d67-9caf-55318586c918"

    async with AsyncSessionLocal() as session:
        print(f"🚀 Merging {OLD_ORG_ID} into {NEW_ORG_ID}...")

        # 1. Update Jobs
        res_jobs = await session.execute(
            update(Job).where(Job.organization_id == OLD_ORG_ID).values(organization_id=NEW_ORG_ID)
        )
        print(f"✅ Updated {res_jobs.rowcount} Jobs")

        # 2. Update Candidates
        res_cand = await session.execute(
            update(Candidate).where(Candidate.organization_id == OLD_ORG_ID).values(organization_id=NEW_ORG_ID)
        )
        print(f"✅ Updated {res_cand.rowcount} Candidates")

        # 3. Update Applications
        res_apps = await session.execute(
            update(Application).where(Application.organization_id == OLD_ORG_ID).values(organization_id=NEW_ORG_ID)
        )
        print(f"✅ Updated {res_apps.rowcount} Applications")

        # 4. Update Interviews
        res_intv = await session.execute(
            update(Interview).where(Interview.organization_id == OLD_ORG_ID).values(organization_id=NEW_ORG_ID)
        )
        print(f"✅ Updated {res_intv.rowcount} Interviews")

        # 5. Update Activities
        res_act = await session.execute(
            update(Activity).where(Activity.organization_id == OLD_ORG_ID).values(organization_id=NEW_ORG_ID)
        )
        print(f"✅ Updated {res_act.rowcount} Activities")

        await session.commit()
        print("🎉 Migration complete!")

if __name__ == "__main__":
    asyncio.run(merge_organizations())
