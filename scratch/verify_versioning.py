import asyncio
import sys
import os
import uuid

# Add src to path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, Job
from src.graph.pipeline import run_reconstructed_pipeline
from sqlalchemy import select, delete

async def verify_versioning():
    job_id = 'b4e069df-5f95-4916-b0c4-1517bd5a3fc5'
    
    print(f"\n--- [VERIFICATION] Starting versioning test for Job {job_id} ---")

    async with AsyncSessionLocal() as db:
        # 0. Cleanup any existing test data to start fresh (Standard test isolation)
        await db.execute(delete(Outbox).where(Outbox.job_id == job_id))
        await db.execute(select(Job).where(Job.id == job_id))
        res = await db.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if job:
            job.last_email_version = 1
        await db.commit()
        print("✅ Environment reset.")

    # 1. Trigger Cycle 1 (Standard)
    print("\n[Cycle 1] Running standard pipeline (should create V1)...")
    await run_reconstructed_pipeline(job_id, state_updates={"force_resend": False})

    # 2. Trigger Cycle 2 (Force Resend)
    print("\n[Cycle 2] Running pipeline with force_resend=True (should create V2)...")
    await run_reconstructed_pipeline(job_id, state_updates={"force_resend": True})

    # 3. Final Database Audit
    print("\n--- [FINAL AUDIT] ---")
    async with AsyncSessionLocal() as db:
        stmt = select(Outbox).where(Outbox.job_id == job_id).order_by(Outbox.version.asc())
        res = await db.execute(stmt)
        items = res.scalars().all()
        
        print(f"Total Outbox Entries found: {len(items)}")
        for item in items:
            print(f"- Type: {item.type} | Version: {item.version} | Status: {item.status} | Created: {item.created_at}")

        job_res = await db.execute(select(Job).where(Job.id == job_id))
        job = job_res.scalar_one_or_none()
        print(f"\nFinal Job 'last_email_version': {job.last_email_version}")

        if len(items) >= 2 and job.last_email_version >= 2:
            print("\n✅ VERIFICATION SUCCESSFUL: Multiple versions preserved in audit log.")
        else:
            print("\n❌ VERIFICATION FAILED: Versioning logic did not increment correctly.")

if __name__ == "__main__":
    asyncio.run(verify_versioning())
