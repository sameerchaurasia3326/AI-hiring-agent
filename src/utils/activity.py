from loguru import logger
from sqlalchemy.future import select
from src.db.database import AsyncSessionLocal
from src.db.models import Activity, Job

async def log_activity(job_id: str, message: str, type: str):
    """
    Logs an activity directly to the DB. Designed to be called from LangGraph nodes.
    Looks up the organization_id from the job_id.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Find the org ID from the job to maintain multi-tenant isolation
            result = await session.execute(select(Job.organization_id).where(Job.id == job_id))
            org_id = result.scalar()
            
            activity = Activity(
                job_id=job_id,
                organization_id=org_id,
                message=message,
                type=type
            )
            session.add(activity)
            await session.commit()
            # [FIX] Safe logging to avoid KeyError if message contains braces
            logger.info("📝 Activity Logged [{}]: {}", type, message)
    except Exception as e:
        logger.error("Failed to log activity: {}", e)
        raise e

def log_activity_sync(job_id: str, message: str, type: str):
    """Synchronous wrapper to call log_activity from synchronous LangGraph nodes."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(log_activity(job_id, message, type))
    except RuntimeError:
        asyncio.run(log_activity(job_id, message, type))

