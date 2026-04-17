import asyncio
import os
import sys
import uuid
from loguru import logger
from sqlalchemy import select

sys.path.append(os.getcwd())
from src.graph.pipeline import get_pipeline
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Candidate

async def kickstart():
    job_id_str = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    job_id = uuid.UUID(job_id_str)
    thread_id = f"job-{job_id_str}"
    
    pipeline = await get_pipeline()
    config = {"configurable": {"thread_id": thread_id}}

    print(f"🚀 Injecting memory for: {job_id_str}")
    
    # Phase 2 & 15: Memory Injection - Force the AI to see the candidates
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Application.id, Candidate.name, Application.resume_path, Candidate.email)
            .join(Candidate)
            .where(Application.job_id == job_id)
        )
        apps = [{"id": str(r[0]), "name": r[1], "resume_path": r[2], "candidate_id": str(r[0]), "email": r[3]} for r in res.all()]
        print(f"✅ Found {len(apps)} candidates in DB.")

    initial_state = {
        "job_id": job_id,
        "pipeline_status": "SCREENING",
        "current_stage": "screening",
        "jd_approved": True,
        "applications": apps,
        "action_type": "resume_injection"
    }
    
    try:
        # Definitive sync-safe invocation
        print("🤖 AI Scorer entered the room. Starting evaluations...")
        await pipeline.ainvoke(initial_state, config)
        print("✅ Scorer finished the pass!")
    except Exception as e:
        print(f"❌ Failed to launch: {e}")

if __name__ == "__main__":
    asyncio.run(kickstart())
