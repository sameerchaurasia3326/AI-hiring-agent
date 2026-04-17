import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Candidate, Application, Job
from sqlalchemy import select, update

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    resumes = [
        {"name": "Aanchal Chaurasia", "email": "aanchal@hiring.ai", "path": "/Users/sameer/Documents/hiring.ai/Aanchal Chaurasia Resume.pdf"},
        {"name": "Akash Chaurasia", "email": "akash@hiring.ai", "path": "/Users/sameer/Documents/hiring.ai/Akash_Chaurasia_13_10_25.pdf"},
        {"name": "Vaibhav", "email": "vaibhav@hiring.ai", "path": "/Users/sameer/Documents/hiring.ai/vaibhav new resume.pdf"}
    ]

    async with AsyncSessionLocal() as session:
        # 1. Get Org ID if available
        res = await session.execute(select(Job.organization_id).where(Job.id == job_id))
        org_id = res.scalar()

        for r in resumes:
            print(f"📄 Injecting {r['name']}...")
            # Check if candidate exists
            c_res = await session.execute(select(Candidate).where(Candidate.email == r["email"]))
            candidate = c_res.scalar_one_or_none()
            
            if not candidate:
                candidate = Candidate(
                    id=uuid.uuid4(),
                    name=r["name"],
                    email=r["email"],
                    organization_id=org_id
                )
                session.add(candidate)
                await session.flush()

            # Create Application
            # Check if already applied
            a_res = await session.execute(
                select(Application).where(Application.job_id == job_id, Application.candidate_id == candidate.id)
            )
            if not a_res.scalar_one_or_none():
                app = Application(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    candidate_id=candidate.id,
                    resume_path=r["path"],
                    stage="screening",
                    source="manual",
                    organization_id=org_id
                )
                session.add(app)
        
        # 2. Advance Job State to SCREENING to trigger the next node
        await session.execute(
            update(Job).where(Job.id == job_id).values(pipeline_state="SCREENING")
        )
        
        await session.commit()
    print("✅ Injection complete. Candidates are now in the SCREENING phase.")

if __name__ == "__main__":
    asyncio.run(main())
