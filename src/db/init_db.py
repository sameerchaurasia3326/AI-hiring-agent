"""
src/db/init_db.py
──────────────────
Standalone script to initialize the Postgres database:
1. Create application tables (Jobs, Candidates, Applications)
2. Create LangGraph checkpointer tables
"""
import asyncio
from loguru import logger
from sqlalchemy import text

from src.db.database import Base, engine
from src.graph.pipeline import get_pipeline
from src.db.models import Job, Candidate, Application, Activity, JobStage, InterviewFeedback # Ensure models are registered with Base

async def init_db():
    logger.info("🐘 Initializing Postgres Database...")

    # 1. Create Core Application Tables
    async with engine.begin() as conn:
        logger.info("🛠️  Creating SQLAlchemy tables (Jobs, Candidates, Applications, JobStages)...")
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration: add is_cancelled column to existing jobs table if it doesn't exist
        await conn.execute(
            text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN DEFAULT FALSE NOT NULL")
        )
        # Safe migration: add current_stage_id and status to candidates table
        await conn.execute(
            text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS current_stage_id UUID REFERENCES job_stages(id) ON DELETE SET NULL")
        )
        await conn.execute(
            text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'processing'")
        )
        await conn.execute(
            text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS rejection_email_sent BOOLEAN DEFAULT FALSE NOT NULL")
        )
        await conn.execute(
            text("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP WITH TIME ZONE")
        )
    
    # 2. Setup LangGraph Checkpointer (creates its own tables)
    logger.info("🧠 Setting up LangGraph Postgres Checkpointer tables...")
    pipeline = await get_pipeline()
    # The setup() is called inside get_pipeline() -> PostgresSaver.from_conn_string
    # but we'll call it explicitly if needed or just let get_pipeline do its thing.
    
    logger.success("✅ Database initialization complete!")

if __name__ == "__main__":
    asyncio.run(init_db())
