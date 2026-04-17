
import asyncio
from sqlalchemy import text
from src.db.database import engine

async def purge():
    print("🧹 [Cleanup] Purging corrupted checkpoints from thread-ids...")
    async with engine.begin() as conn:
        try:
            # We clear job-related threads which are experiencing the memory allocation error
            await conn.execute(text("DELETE FROM checkpoints WHERE thread_id LIKE 'job-%';"))
            print("✅ [Cleanup] Success: Corrupted checkpoints purged.")
        except Exception as e:
            print(f"❌ [Cleanup] Failed: {e}")

if __name__ == "__main__":
    asyncio.run(purge())
