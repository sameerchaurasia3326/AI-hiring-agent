import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, Job
from sqlalchemy import select, update
from src.scheduler.tasks import process_outbox_queue

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Reset the outbox item to PENDING so we can try again
        # We also force the provider to SMTP this time in the code logic
        res = await session.execute(
            select(Outbox).where(Outbox.type == "JD_APPROVAL_REQUEST").order_by(Outbox.created_at.desc()).limit(1)
        )
        item = res.scalar_one_or_none()
        if not item:
            print("❌ No JD_APPROVAL_REQUEST found in outbox.")
            return

        print(f"🔍 Found item {item.id} (Status: {item.status}). Resetting to PENDING...")
        item.status = "PENDING"
        item.retry_count = 0
        await session.commit()
        
    # 2. Trigger the processor manually
    print("🚀 Triggering dispatcher...")
    p = process_outbox_queue()
    print(f"✅ Handled {p} items.")

if __name__ == "__main__":
    asyncio.run(main())
