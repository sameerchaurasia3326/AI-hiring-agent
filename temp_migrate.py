
import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        print("🔍 Checking and adding missing columns to 'users' table...")
        
        # Check if column exists first (optional but safer)
        # For now we'll just try to add them and catch the error if they exist
        try:
            await session.execute(text("ALTER TABLE users ADD COLUMN google_access_token TEXT;"))
            print("✅ Added google_access_token")
        except Exception as e:
            print(f"ℹ️ google_access_token: {e}")

        try:
            await session.execute(text("ALTER TABLE users ADD COLUMN google_refresh_token TEXT;"))
            print("✅ Added google_refresh_token")
        except Exception as e:
            print(f"ℹ️ google_refresh_token: {e}")

        try:
            await session.execute(text("ALTER TABLE users ADD COLUMN google_token_expiry TIMESTAMP WITH TIME ZONE;"))
            print("✅ Added google_token_expiry")
        except Exception as e:
            print(f"ℹ️ google_token_expiry: {e}")

        await session.commit()
        print("🚀 Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
