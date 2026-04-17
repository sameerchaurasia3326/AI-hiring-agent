"""
scripts/verify_idempotency.py
─────────────────────────────
Verifies that duplicate outbox inserts for (job_id, type) are correctly ignored.
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, Organization, Job

async def verify():
    logger.info("🧪 Starting Outbox Idempotency Verification...")
    
    async with AsyncSessionLocal() as session:
        # 1. Setup Org/Job
        org_res = await session.execute(select(Organization).limit(1))
        org = org_res.scalar_one_or_none()
        if not org:
            logger.error("❌ Need an organization to run tests.")
            return

        job_id = str(uuid.uuid4())
        job = Job(id=job_id, organization_id=org.id, title="Test Job")
        session.add(job)
        await session.commit()

        try:
            # 2. First Insert (Should Succeed)
            logger.info(f"📍 Attempting first insert for job {job_id}...")
            stmt1 = (
                insert(Outbox)
                .values(
                    job_id=job_id,
                    type="IDEM_TEST",
                    payload={"msg": "first"},
                    status="PENDING",
                    created_at=datetime.now(timezone.utc)
                )
                .on_conflict_do_nothing(index_elements=["job_id", "type"])
            )
            await session.execute(stmt1)
            await session.commit()
            
            # 3. Second Insert (Should be ignored, NO ERROR)
            logger.info("📍 Attempting duplicate insert (should DO NOTHING)...")
            stmt2 = (
                insert(Outbox)
                .values(
                    job_id=job_id,
                    type="IDEM_TEST",
                    payload={"msg": "second - IGNORE ME"},
                    status="PENDING",
                    created_at=datetime.now(timezone.utc)
                )
                .on_conflict_do_nothing(index_elements=["job_id", "type"])
            )
            await session.execute(stmt2)
            await session.commit()
            
            # 4. Count Check
            res = await session.execute(select(Outbox).where(Outbox.job_id == job_id, Outbox.type == "IDEM_TEST"))
            items = res.scalars().all()
            
            print("\n" + "="*50)
            if len(items) == 1:
                print("✅ VERIFICATION SUCCESS: Only 1 row exists after 2 attempts!")
                print(f"   Payload in DB: {items[0].payload}")
            else:
                print(f"❌ VERIFICATION FAILED: Found {len(items)} rows.")
            print("="*50 + "\n")

        finally:
            # Cleanup
            await session.execute(text(f"DELETE FROM jobs WHERE id = '{job_id}'"))
            await session.commit()

if __name__ == "__main__":
    from sqlalchemy import text # for cleanup
    asyncio.run(verify())
