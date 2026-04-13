
import asyncio
import os
import sys
import uuid
from sqlalchemy import select

# Add project root to path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Job, Application, Candidate, User
from src.nodes.shortlist_sender import send_shortlist_to_hr

async def verify_email():
    job_id = "d5f14ddc-d933-403b-8d0f-6b481cc6fae9"
    
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if not job:
            print("❌ Job not found.")
            return
            
        # Get candidates with scores
        stmt = (
            select(Application.score, Candidate.name, Candidate.email)
            .join(Candidate, Application.candidate_id == Candidate.id)
            .where(Application.job_id == job.id, Application.score > 0)
        )
        res = await session.execute(stmt)
        shortlist_data = []
        for score, name, email in res.all():
            shortlist_data.append({
                "name": name,
                "email": email,
                "score": float(score)
            })
            
        # Get admin email
        admin_stmt = select(User.email).where(User.organization_id == job.organization_id).limit(1)
        admin_email = (await session.execute(admin_stmt)).scalar() or "sameerchaurasia3326@gmail.com"

        print(f"🎯 Target Admin Email: {admin_email}")
        print(f"📊 Shortlist size: {len(shortlist_data)}")

        state = {
            "job_id": job_id,
            "job_title": job.title,
            "admin_email": admin_email,
            "shortlist": shortlist_data,
            "shortlist_sent_to_hr": False
        }

    print("\n📧 Triggering send_shortlist_to_hr node...")
    try:
        # This will call our purified node
        new_state = await send_shortlist_to_hr(state)
        
        if new_state.get("shortlist_sent_to_hr"):
            print("✅ Node reported SUCCESS.")
        else:
            print("❌ Node did not report SUCCESS.")
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_email())
