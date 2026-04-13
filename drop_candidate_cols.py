import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal, engine

async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE candidates DROP COLUMN IF EXISTS status;"))
        await conn.execute(text("ALTER TABLE candidates DROP COLUMN IF EXISTS interviewer_id;"))
        await conn.execute(text("ALTER TABLE candidates DROP COLUMN IF EXISTS current_stage_id;"))
        await conn.execute(text("ALTER TABLE candidates DROP COLUMN IF EXISTS rejection_email_sent;"))
        await conn.execute(text("ALTER TABLE candidates DROP COLUMN IF EXISTS rejected_at;"))
    print("Dropped redundant columns successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
