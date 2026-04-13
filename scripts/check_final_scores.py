import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Candidate
from sqlalchemy import select

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Candidate.name, Application.score, Application.stage)
            .join(Application)
            .where(Application.job_id == job_id)
        )
        apps = res.all()
        print(f"📈 RESULTS for Job {job_id}:")
        for name, score, stage in apps:
            print(f"👤 {name}: Score={score} | Stage={stage}")

if __name__ == "__main__":
    asyncio.run(main())
