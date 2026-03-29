"""
sync_schema.py
──────────────
Force-synchronizes the PostgreSQL schema with the SQLAlchemy models.
Adds missing columns (created_at, OAuth tokens, etc.) across all tables.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.engine import reflection
from sqlalchemy.ext.asyncio import create_async_engine
from src.config import settings

async def sync_table(conn, table_name, required_columns):
    """Check for missing columns and add them via ALTER TABLE."""
    def get_columns(connection):
        insp = reflection.Inspector.from_engine(connection)
        return [c["name"] for c in insp.get_columns(table_name)]

    existing_columns = await conn.run_sync(get_columns)
    
    for col_name, col_type in required_columns:
        if col_name not in existing_columns:
            print(f"🔧 Adding column '{col_name}' to table '{table_name}'...")
            await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
        else:
            print(f"✅ Column '{col_name}' already exists in table '{table_name}'.")

async def main():
    engine = create_async_engine(settings.database_url)
    
    schema_map = {
        "users": [
            ("google_access_token", "TEXT"),
            ("google_refresh_token", "TEXT"),
            ("google_token_expiry", "TIMESTAMP WITH TIME ZONE"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
        ],
        "jobs": [
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("posted_at", "TIMESTAMP WITH TIME ZONE"),
            ("closed_at", "TIMESTAMP WITH TIME ZONE"),
            ("is_cancelled", "BOOLEAN DEFAULT FALSE")
        ],
        "job_stages": [
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
        ],
        "candidates": [
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("rejected_at", "TIMESTAMP WITH TIME ZONE")
        ],
        "applications": [
            ("applied_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("interview_slot", "TIMESTAMP WITH TIME ZONE"),
            ("invite_sent", "BOOLEAN DEFAULT FALSE")
        ],
        "activities": [
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
        ],
        "interview_feedback": [
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
        ]
    }
    
    async with engine.begin() as conn:
        for table_name, columns in schema_map.items():
            try:
                await sync_table(conn, table_name, columns)
            except Exception as e:
                print(f"❌ Error syncing table '{table_name}': {e}")
                
    await engine.dispose()
    print("\n🚀 Schema synchronization complete!")

if __name__ == "__main__":
    asyncio.run(main())
