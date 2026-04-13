import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox, DeadLetterQueue
from sqlalchemy import select
from src.scheduler.tasks import process_outbox_queue

async def main():
    async with AsyncSessionLocal() as session:
        # Check for our specific JD approval request
        res = await session.execute(
            select(Outbox).where(Outbox.type == "JD_APPROVAL_REQUEST").order_by(Outbox.created_at.desc()).limit(1)
        )
        item = res.scalar_one_or_none()
        if not item:
            print("❌ JD_APPROVAL_REQUEST NOT FOUND.")
            return

        print(f"📦 ITEM_FOUND: status={item.status} retries={item.retry_count}")
        
        if item.status != "SENT":
            print(f"🔄 Status is {item.status}. Force-resetting to PENDING...")
            item.status = "PENDING"
            item.retry_count = 0
            await session.commit()
            
            print("🚀 Executing process_outbox_queue()...")
            p = process_outbox_queue()
            print(f"✅ Handled {p} items.")
        else:
            print("✅ Item is already marked as SENT.")

if __name__ == "__main__":
    asyncio.run(main())
