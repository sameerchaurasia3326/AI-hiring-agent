import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal, engine

async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE applications ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP WITH TIME ZONE;"))
        await conn.execute(text("ALTER TABLE applications ADD COLUMN IF NOT EXISTS current_stage_id UUID REFERENCES job_stages(id) ON DELETE SET NULL;"))
    print("Added columns to applications table successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
