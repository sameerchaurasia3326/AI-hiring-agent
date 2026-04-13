import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Organization
from src.utils.production_safety import lease_guard, StructuredLogger
from loguru import logger

# Mock a slow node
@lease_guard
async def slow_processing_node(state: dict):
    job_id = state.get("job_id")
    logger.info(f"🐢 [Node] Starting 70s slow process for {job_id}...")
    # This should trigger at least 2 heartbeats (at 30s and 60s)
    await asyncio.sleep(70)
    logger.info(f"🏁 [Node] Slow process finished for {job_id}")
    return state

async def run_heartbeat_test():
    logger.info("🧪 Starting Heartbeat Verification Test...")
    
    async with AsyncSessionLocal() as session:
        org_res = await session.execute(select(Organization).limit(1))
        org = org_res.scalar_one_or_none()
        if not org:
            logger.error("❌ Need at least one Organization to run tests.")
            return
        org_id = org.id

    job_id = str(uuid.uuid4())
    
    # 1. Create Job
    async with AsyncSessionLocal() as session:
        job = Job(id=job_id, organization_id=org_id, title="Heartbeat Test Job", pipeline_state="SCREENING")
        session.add(job)
        await session.commit()
    
    # 2. Start the slow node in the background
    state = {"job_id": job_id}
    node_task = asyncio.create_task(slow_processing_node(state))
    
    # 3. Monitor locked_at timestamp
    timestamps = []
    
    logger.info("👀 Monitoring database for heartbeat refreshes...")
    for i in range(5): # Check every 20s for 100s total
        await asyncio.sleep(20)
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Job).where(Job.id == job_id))
            job = res.scalar_one()
            ts = job.locked_at
            if ts:
                timestamps.append(ts)
                logger.info(f"   [{i+1}] Current locked_at: {ts.strftime('%H:%M:%S')}")
            else:
                logger.warning(f"   [{i+1}] No lease found yet.")

    # 4. Final verification
    await node_task 
    
    logger.info(f"📊 Collected {len(timestamps)} timestamps.")
    
    # Filter for unique timestamps (seconds precision)
    unique_ts = set([t.replace(microsecond=0) for t in timestamps])
    
    print("\n" + "="*50)
    if len(unique_ts) >= 3:
        print("✅ TEST PASSED: Heartbeat refreshed the lease at least twice!")
    else:
        print(f"❌ TEST FAILED: Only {len(unique_ts)} unique timestamps found.")
        print(f"Refreshes: {[t.strftime('%H:%M:%S') for t in sorted(list(unique_ts))]}")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(run_heartbeat_test())
