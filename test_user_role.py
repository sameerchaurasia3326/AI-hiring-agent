import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import User
from sqlalchemy import select

async def run():
    async with AsyncSessionLocal() as session:
        # Check user by email
        result = await session.execute(select(User).where(User.email == "projectsmtp64@gmail.com"))
        user = result.scalars().first()
        if user:
            print(f"USER: {user.email}, ROLE: {user.role}")
        else:
            print("USER NOT FOUND")

if __name__ == "__main__":
    asyncio.run(run())
