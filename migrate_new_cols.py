import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        try:
            # 1. Rename ai_score to score
            await session.execute(text("ALTER TABLE applications RENAME COLUMN ai_score TO score;"))
            print("Renamed ai_score to score")
            
            # 2. Add stage column
            await session.execute(text("ALTER TABLE applications ADD COLUMN stage VARCHAR(50);"))
            print("Added stage column")
            
            # 3. Update stage for existing shortlisted applications
            await session.execute(text("UPDATE applications SET stage = 'shortlisted' WHERE is_shortlisted = TRUE;"))
            await session.execute(text("UPDATE applications SET stage = 'screening' WHERE is_shortlisted = FALSE AND rejected = FALSE;"))
            await session.execute(text("UPDATE applications SET stage = 'rejected' WHERE rejected = TRUE;"))
            print("Migrated existing stage data")
            
            await session.commit()
            print("Migration successful")
        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
