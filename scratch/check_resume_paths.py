
import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Candidate
from sqlalchemy import select
from sqlalchemy.orm import joinedload
import os

async def main():
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    print(f"📂 [Audit] Verifying resume paths for job_id: {job_id}")
    
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.job_id == job_id)
        )
        res = await session.execute(stmt)
        apps = res.scalars().all()
        
        for app in apps:
            name = app.candidate.name if app.candidate else "Unknown"
            path = app.resume_path
            exists = os.path.exists(path) if path else False
            print(f"👤 Candidate: {name}")
            print(f"   - Stored Path: {path}")
            print(f"   - File Exists: {exists}")
            print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
