import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Job, Candidate, User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        user_id = '252a926a-438c-406b-a7ee-653e1a08aa80'
        u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not u:
            print("USER NOT FOUND")
            return
        print(f"USER: {u.id}, ORG: {u.organization_id}, ROLE: {u.role}")
        
        stmt = (
            select(Application.id, Application.stage, Application.interviewer_id, 
                   Job.organization_id.label('job_org'), 
                   Application.organization_id.label('app_org'), 
                   Candidate.name)
            .join(Candidate, Application.candidate_id == Candidate.id)
            .join(Job, Application.job_id == Job.id)
        )
        res = await session.execute(stmt)
        apps = res.all()
        
        print(f"TOTAL_APPS_IN_SYSTEM: {len(apps)}")
        for a in apps:
            match = "MATCH" if str(a.job_org) == str(u.organization_id) else "NO_MATCH"
            print(f"APP: {a.id}, STAGE: '{a.stage}', INT_ID: {a.interviewer_id}, JOB_ORG: {a.job_org}, APP_ORG: {a.app_org}, CAND: {a.name}, ORG_MATCH: {match}")

if __name__ == "__main__":
    asyncio.run(main())
