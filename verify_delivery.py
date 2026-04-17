import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Outbox
from sqlalchemy import text

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        # Check Job record
        res1 = await session.execute(
            text("SELECT hiring_manager_email, hiring_manager_name, title FROM jobs WHERE id = :id"),
            {"id": job_id}
        )
        job = res1.first()
        
        if job:
            print(f"📌 JOB_DETAILS: Title='{job.title}' Handler='{job.hiring_manager_name}' Target='{job.hiring_manager_email}'")
        
        # Check Outbox
        res2 = await session.execute(
            text("SELECT status, retry_count, last_attempt_at FROM outbox WHERE job_id = :id AND type = 'JD_APPROVAL_REQUEST' ORDER BY created_at DESC LIMIT 1"),
            {"id": job_id}
        )
        outbox = res2.first()
        
        if outbox:
            print(f"📦 OUTBOX_STATUS: {outbox.status} (Retries: {outbox.retry_count}, Last: {outbox.last_attempt_at})")
        else:
            print("❌ NO_OUTBOX_RECORD_FOUND_FOR_THIS_JOB")

if __name__ == "__main__":
    asyncio.run(main())
