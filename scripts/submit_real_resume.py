import asyncio
import os
from sqlalchemy import select
from pathlib import Path

# Load environment before any app imports
from dotenv import load_dotenv
load_dotenv(override=True)

from src.db.database import AsyncSessionLocal
from src.db.models import Job, Candidate, Application, User

async def run():
    async with AsyncSessionLocal() as session:
        # 1. Get the most recent active job
        stmt = select(Job).where(Job.is_cancelled == False).order_by(Job.created_at.desc())
        job = (await session.execute(stmt)).scalars().first()
        
        if not job:
            print("No active jobs found in the database.")
            return

        print(f"🔧 Target Job: {job.title} (ID: {job.id})")
        print(f"🏢 Organization: {job.organization_id}")
        
        # 2. Get the hiring manager for the org
        stmt_user = select(User).where(User.organization_id == job.organization_id, User.role == 'hiring_manager')
        hm = (await session.execute(stmt_user)).scalars().first()
        if not hm:
            print("No hiring manager found for this organization.")
            return

        # 3. Create or Fetch Candidate linked to a real physical PDF
        # We'll use Vaibhav's resume from the root directory
        resume_tgt = "/Users/sameer/Documents/hiring.ai/vaibhav new resume.pdf"
        
        stmt_dup = select(Candidate).filter(Candidate.email == "vaibhav.test@hiring.ai")
        cand = (await session.execute(stmt_dup)).scalars().first()
        
        if not cand:
            cand = Candidate(
                organization_id=job.organization_id,
                name="Vaibhav (Real Payload Test)",
                email="vaibhav.test@hiring.ai",
                phone="555-010-1010",
                resume_url=resume_tgt,
                status="applied",
                interviewer_id=hm.id
            )
            session.add(cand)
            await session.flush()
            print(f"👤 Created candidate: {cand.name} (ID: {cand.id})")
        else:
            cand.resume_url = resume_tgt  # Ensure correct path is set
            print(f"👤 Using existing candidate: {cand.name} (ID: {cand.id})")
            
        # 4. Create Application Link
        stmt_app = select(Application).filter(Application.candidate_id == cand.id, Application.job_id == job.id)
        app = (await session.execute(stmt_app)).scalars().first()
        
        if not app:
            app = Application(
                job_id=job.id,
                candidate_id=cand.id,
                stage="shortlisting",
                source="manual",
                organization_id=job.organization_id
            )
            session.add(app)
            await session.flush()
            print(f"🔗 Linked Candidate to Job (Application ID: {app.id})")
        else:
            print(f"🔗 Candidate already linked to Job.")
            
        await session.commit()
    
    # 5. Trigger the LangGraph Pipeline Resumption
    print("\n🚀 Firing LangGraph Pipeline Resumption Event...")
    from src.api.main import resume_graph_with_selection
    await resume_graph_with_selection(str(job.id), str(cand.id))
    print("✅ Done! Tail the application logs to watch the Resume Scorer process this file.")

if __name__ == "__main__":
    asyncio.run(run())
