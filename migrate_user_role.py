import asyncio
from sqlalchemy import text
from src.db.database import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        try:
            # Drop the old default
            await session.execute(text("ALTER TABLE users ALTER COLUMN role DROP DEFAULT;"))
            
            # Change the column type to VARCHAR(50) (if it isn't already)
            await session.execute(text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(50);"))
            
            # Set default backward-compatible to 'candidate'
            await session.execute(text("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'candidate';"))
            
            # Update any out-of-bounds roles or empty roles
            await session.execute(text("UPDATE users SET role = 'candidate' WHERE role IS NULL OR role NOT IN ('admin', 'interviewer', 'candidate');"))
            
            # Since native_enum=False in SQLAlchemy creates a CHECK constraint named 'user_role_enum_chk' or similar
            # Let's add the check constraint explicitly at the DB level, dropping existing if any
            try:
                await session.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;"))
                await session.execute(text("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('candidate', 'interviewer', 'admin'));"))
            except Exception as e:
                print(f"Constraint notice: {e}")
                
            await session.commit()
            print("Migration successful: Updated users.role to Enum with default 'candidate'")
        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
