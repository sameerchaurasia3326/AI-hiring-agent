import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox
from sqlalchemy import delete
from src.scheduler.tasks import process_outbox_queue

async def main():
    async with AsyncSessionLocal() as session:
        # 1. Clear any old notification records for this specific job
        print("🧹 Clearing old notification state...")
        await session.execute(
            delete(Outbox).where(Outbox.job_id == 'b4e069df-5f95-4916-b0c4-1517bd5a3fc5')
        )
        await session.commit()
    
    # 2. Re-trigger the pipeline (will be done via shell)
    print("✅ Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(main())
