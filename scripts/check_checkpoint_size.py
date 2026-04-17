import asyncio
import os
import sys
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Check size of checkpoints for this job
        res = await session.execute(
            text("SELECT thread_id, length(checkpoint::text) as size FROM checkpoints WHERE thread_id = 'job-b4e069df-5f95-4916-b0c4-1517bd5a3fc5' ORDER BY size DESC LIMIT 5")
        )
        rows = res.all()
        print("💾 CHECKPOINT SIZES:")
        for row in rows:
            print(f"🧵 {row.thread_id}: {row.size / 1024 / 1024:.2f} MB")
            
        if rows and rows[0].size > 50 * 1024 * 1024:
            print("⚠️ Checkpoint is getting large. This might be causing the memory error.")

if __name__ == "__main__":
    asyncio.run(main())
