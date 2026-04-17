"""
scripts/test_retry_classification.py
───────────────────────────────────
Verifies that:
1. Permanent errors (ValueError) skip retries and go to DLQ immediately.
2. Transient errors (TimeoutError) continue to retry with backoff.
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, delete, text
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, DeadLetterQueue, Organization, Job
from src.utils.production_safety import is_retryable_error

# ─────────────────────────────────────────────────────────────
# MOCK DISPATCHERS
# ─────────────────────────────────────────────────────────────

async def mock_permanent_fail(*args, **kwargs):
    raise ValueError("PERMANENT_FAIL: Invalid email format")

async def mock_transient_fail(*args, **kwargs):
    raise ConnectionError("TRANSIENT_FAIL: Database timeout")

# ─────────────────────────────────────────────────────────────
# TEST SUITE
# ─────────────────────────────────────────────────────────────

async def test_classification():
    logger.info("🧪 Starting Retry Classification Tests...")
    
    async with AsyncSessionLocal() as session:
        # PREP: Ensure dummy org exists
        org_res = await session.execute(select(Organization).limit(1))
        org = org_res.scalar_one_or_none()
        if not org:
            logger.error("❌ Need an organization to run tests.")
            return

        job_id = str(uuid.uuid4())
        job = Job(id=job_id, organization_id=org.id, title="Retry Test Job")
        session.add(job)
        await session.commit()

        try:
            # 1. TEST PERMANENT FAIL (Should go to DLQ instantly)
            logger.info("📍 Testing Permanent Fail (ValueError)...")
            item_p = Outbox(
                job_id=job_id,
                type="TEST_PERM",
                payload={"email": "bad"},
                status="PENDING"
            )
            session.add(item_p)
            await session.commit()
            await session.refresh(item_p)

            # Simulate logic from tasks.py
            try:
                # This would be the 'with_resilience' call
                await mock_permanent_fail()
            except Exception as e:
                if not is_retryable_error(e):
                    logger.info("✅ is_retryable_error correctly identified ValueError as permanent.")
                    # Move to DLQ
                    dlq_item = DeadLetterQueue(
                        job_id=item_p.job_id,
                        payload=item_p.payload,
                        reason=str(e),
                        retry_count=1,
                        failed_at=datetime.now(timezone.utc)
                    )
                    session.add(dlq_item)
                    item_p.status = "FAILED"
                    await session.commit()

            # Verify DLQ entry exists
            res = await session.execute(select(DeadLetterQueue).where(DeadLetterQueue.job_id == job_id, DeadLetterQueue.reason.contains("PERMANENT_FAIL")))
            if res.scalar_one_or_none():
                logger.success("🚀 SUCCESS: Permanent failure fast-failed to DLQ!")
            else:
                logger.error("❌ FAILURE: Permanent failure did NOT hit DLQ.")

            # 2. TEST TRANSIENT FAIL (Should NOT hit DLQ, should increment retry)
            logger.info("📍 Testing Transient Fail (ConnectionError)...")
            item_t = Outbox(
                job_id=job_id,
                type="TEST_TRANS",
                payload={"email": "ok@test.com"},
                status="PENDING"
            )
            session.add(item_t)
            await session.commit()
            await session.refresh(item_t)

            try:
                await mock_transient_fail()
            except Exception as e:
                if is_retryable_error(e):
                    logger.info("✅ is_retryable_error correctly identified ConnectionError as transient.")
                    item_t.retry_count += 1
                    await session.commit()
            
            # Verify it's STILL in Outbox (not DLQ)
            res_dlq = await session.execute(select(DeadLetterQueue).where(DeadLetterQueue.job_id == job_id, DeadLetterQueue.reason.contains("TRANSIENT_FAIL")))
            res_node = await session.execute(select(Outbox).where(Outbox.id == item_t.id))
            
            if res_dlq.scalar_one_or_none():
                logger.error("❌ FAILURE: Transient error fast-failed to DLQ incorrectly.")
            elif res_node.scalar_one().retry_count == 1:
                logger.success("🚀 SUCCESS: Transient error correctly queued for retry!")

        finally:
            # Cleanup
            await session.execute(text(f"DELETE FROM dead_letter_queue WHERE job_id = '{job_id}'"))
            await session.execute(text(f"DELETE FROM outbox WHERE job_id = '{job_id}'"))
            await session.execute(text(f"DELETE FROM jobs WHERE id = '{job_id}'"))
            await session.commit()

if __name__ == "__main__":
    asyncio.run(test_classification())
