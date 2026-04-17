import asyncio
import os
import sys
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        # Check lengths of raw checkpoint data
        res = await session.execute(
            text("SELECT thread_id, checkpoint_id, length(checkpoint::text) as size_bytes FROM checkpoints WHERE thread_id = 'job-b4e069df-5f95-4916-b0c4-1517bd5a3fc5' ORDER BY size_bytes DESC LIMIT 10")
        )
        rows = res.all()
        print("📊 TOP 10 CHECKPOINT SIZES (Bytes):")
        for row in rows:
            print(f"🧵 ID: {row.checkpoint_id} | Size: {row.size_bytes / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    asyncio.run(main())
