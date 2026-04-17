import asyncio
import uuid
import time
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Job
from sqlalchemy import select, text, func

async def monitor():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    print(f"🕵️ Monitoring scoring for job {job_id}...")
    
    timeout = time.time() + 300 # 5 minute timeout
    while time.time() < timeout:
        async with AsyncSessionLocal() as session:
            # Check if all 3 applications are scored
            res = await session.execute(
                select(func.count(Application.id))
                .where(Application.job_id == job_id, Application.is_scored == True)
            )
            scored_count = res.scalar()
            
            if scored_count >= 3:
                print(f"✅ All {scored_count} candidates scored! Advancing dashboard...")
                # Update both pipeline state AND status to ensure blue tick
                await session.execute(
                    text("UPDATE jobs SET pipeline_state = 'SHORTLISTING', status = 'PROCESSING' WHERE id = :id"),
                    {"id": job_id}
                )
                await session.commit()
                print("🚀 DASHBOARD UPDATED: Screening complete, Shortlisting active.")
                return
            
            print(f"⏳ Progress: {scored_count}/3 scored. Waiting 15s...")
        await asyncio.sleep(15)
    print("❌ Timeout waiting for scores.")

if __name__ == "__main__":
    asyncio.run(monitor())
