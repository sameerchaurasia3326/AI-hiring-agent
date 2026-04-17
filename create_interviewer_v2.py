import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import User, UserRole
from src.api.auth import hash_password
import uuid

async def create_test_interviewer():
    async with AsyncSessionLocal() as session:
        # Link to the primary organization (hiring_ai default)
        org_id = uuid.UUID('6705065f-28e0-4d67-9caf-55318586c918')
        
        # Check if user already exists
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.email == 'test@gmail.com'))
        if res.scalar_one_or_none():
            print("ℹ️ User test@gmail.com already exists. Skipping.")
            return

        user = User(
            id=uuid.uuid4(),
            email='test@gmail.com',
            hashed_password=hash_password('password123'),
            role=UserRole.interviewer,
            organization_id=org_id,
            full_name='Test Interviewer',
            is_active=True,
            is_verified=True
        )
        session.add(user)
        try:
            await session.commit()
            print("✅ Successfully seeded interviewer account:")
            print("   - Email: test@gmail.com")
            print("   - Pass:  password123")
        except Exception as e:
            await session.rollback()
            print(f"❌ Failed to seed user: {e}")

if __name__ == "__main__":
    asyncio.run(create_test_interviewer())
