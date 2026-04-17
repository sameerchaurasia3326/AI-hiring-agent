import asyncio
import os
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Job, Candidate, User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        user_id = '252a926a-438c-406b-a7ee-653e1a08aa80'
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            print(f'ERROR: User {user_id} not found')
            return
        
        print(f'USER_ROLE: {user.role}')
        print(f'USER_ORG: {user.organization_id}')
        
        # Check all apps for this organization
        stmt = (
            select(Application.id, Application.stage, Application.interviewer_id, Candidate.name)
            .join(Candidate, Application.candidate_id == Candidate.id)
            .join(Job, Application.job_id == Job.id)
            .where(Job.organization_id == user.organization_id)
        )
        res = await session.execute(stmt)
        rows = res.all()
        print(f'TOTAL_APPS_IN_ORG: {len(rows)}')
        for r in rows:
            print(f'  App: {r.id}, Stage: {r.stage}, AssignedInterviewer: {r.interviewer_id}, Candidate: {r.name}')

if __name__ == "__main__":
    asyncio.run(main())
