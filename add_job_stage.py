import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        try:
            # 1. Add current_stage column to jobs table
            await session.execute(text("ALTER TABLE jobs ADD COLUMN current_stage VARCHAR(100);"))
            print("Added current_stage column to jobs table")
            
            # 2. Update existing jobs with status='ACTION_REQUIRED' to have current_stage='shortlisting'
            await session.execute(text("UPDATE jobs SET current_stage = 'shortlisting' WHERE status = 'ACTION_REQUIRED';"))
            print("Migrated existing status data to current_stage")
            
            await session.commit()
            print("Migration successful")
        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
