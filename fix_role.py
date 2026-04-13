import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import User, UserRole
from sqlalchemy import select, update

async def run():
    async with AsyncSessionLocal() as session:
        # Check user by email
        result = await session.execute(select(User).where(User.email == "projectsmtp64@gmail.com"))
        user = result.scalars().first()
        if user:
            print(f"Current USER: {user.email}, ROLE: {user.role}")
            user.role = UserRole.interviewer
            await session.commit()
            print(f"Updated role to: {user.role}")
        else:
            print("USER NOT FOUND")

if __name__ == "__main__":
    asyncio.run(run())
