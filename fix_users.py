import asyncio
import sys
import os

# Add the current directory to sys.path so we can import src
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import User, UserRole
from sqlalchemy import select

async def fix_role(email, target_role):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if user:
            print(f"Current USER: {user.email}, ROLE: {user.role}")
            user.role = target_role
            await session.commit()
            print(f"Updated {email} to: {target_role}")
        else:
            print(f"USER {email} NOT FOUND")

async def main():
    # Fix the accounts that were accidentally promoted to admin
    await fix_role("projectsmtp64@gmail.com", UserRole.interviewer)
    await fix_role("test@gmail.com", UserRole.interviewer)

if __name__ == "__main__":
    asyncio.run(main())
