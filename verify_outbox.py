import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Outbox).where(Outbox.type == "JD_APPROVAL_REQUEST").order_by(Outbox.created_at.desc()).limit(1)
        )
        item = res.scalar_one_or_none()
        if item:
            print(f"✅ ITEM_FOUND: id={item.id} status={item.status} retries={item.retry_count}")
        else:
            print("❌ ITEM_NOT_FOUND")

if __name__ == "__main__":
    asyncio.run(main())
