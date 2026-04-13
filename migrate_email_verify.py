import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        print("🔍 Adding email verification columns...")
        
        # Add columns
        columns_to_add = [
            "ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE users ADD COLUMN email_verification_otp_hash TEXT;",
            "ALTER TABLE users ADD COLUMN email_verification_expires TIMESTAMPTZ;",
            "ALTER TABLE users ADD COLUMN email_verification_attempts INTEGER DEFAULT 0;"
        ]
        
        for stmt in columns_to_add:
            try:
                await session.execute(text(stmt))
                print(f"✅ Executed: {stmt.split('ADD COLUMN ')[1].split()[0]}")
            except Exception as e:
                print(f"ℹ️ Skipping/Error: {stmt.split('ADD COLUMN ')[1].split()[0]} - {e}")

        # Grandfather existing users
        print("🔄 Grandfathering existing users...")
        try:
            # We enforce TRUE for users that already existed before this migration
            await session.execute(text("UPDATE users SET is_email_verified = TRUE WHERE is_email_verified = FALSE;"))
            print("✅ Existing users grandfathered (is_email_verified = TRUE)")
        except Exception as e:
            print(f"❌ Failed to grandfather users: {e}")

        # Create Index
        try:
            await session.execute(text("CREATE INDEX ix_users_is_email_verified ON users (is_email_verified);"))
            print("✅ Index created on is_email_verified")
        except Exception as e:
            print(f"ℹ️ Index creation skipped/error: {e}")

        await session.commit()
        print("🚀 Email verification migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
