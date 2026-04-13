
import asyncio
from sqlalchemy import text
from src.db.database import engine

async def migrate():
    print("🚀 [Migration] Adding interrupt_payload column to jobs table...")
    async with engine.begin() as conn:
        try:
            # We use a raw SQL command for the migration
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS interrupt_payload JSONB;"))
            print("✅ [Migration] Success: column interrupt_payload added.")
        except Exception as e:
            print(f"❌ [Migration] Failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
