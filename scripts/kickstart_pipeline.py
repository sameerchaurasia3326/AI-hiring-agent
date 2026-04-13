import asyncio
import sys
import os
import argparse
import uuid
from loguru import logger

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.db.database import AsyncSessionLocal
from src.db.models import Job
from src.state.schema import HiringState, PipelineStatus
from src.graph.pipeline import get_pipeline
from sqlalchemy import select

async def kickstart_job(job_id: str):
    """Manually triggers LLM generation for an existing job by injecting its state into LangGraph."""
    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch existing job details
            stmt = select(Job).where(Job.id == uuid.UUID(job_id))
            res = await session.execute(stmt)
            job = res.scalar_one_or_none()
            
            if not job:
                print(f"⚠️  Job {job_id} not found.")
                return

            print(f"🚀 Re-launching pipeline for: {job.title}")

            # 2. Reconstruct the 'initial_state' that the API normally sends
            initial_state: HiringState = {
                "job_id":                str(job.id),
                "trace_id":              "recovered-" + str(uuid.uuid4())[:8],
                "organization_id":       job.organization_id,
                "graph_thread_id":       job.graph_thread_id or f"job-{job.id}",
                "job_title":             job.title,
                "jd_draft":              job.jd_draft,
                "pipeline_status":        PipelineStatus.JD_DRAFT.value,
                "required_skills":       job.required_skills or [],
                "preferred_skills":      job.preferred_skills or [],
                "jd_revision_count":     0,
                "repost_attempts":       0,
                "applications":          [],
                "scored_resumes":        [],
                "hr_selected_candidates": [],
                "error_log":             [],
            }

            # 3. Get the pipeline and trigger it
            pipeline = await get_pipeline()
            config = {"configurable": {"thread_id": initial_state["graph_thread_id"]}}
            
            print("🧠 AI Engine engaged. Generating JD...")
            # We use ainvoke here to actually run it
            await pipeline.ainvoke(initial_state, config=config)
            
            print("✅ Generation complete! Check your terminal and dashboard.")

    except Exception as e:
        print(f"❌ Failed to kickstart job: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kickstart a stalled Hiring.AI pipeline.")
    parser.add_argument("--job_id", required=True, help="UUID of the job to re-trigger")
    args = parser.parse_args()
    
    asyncio.run(kickstart_job(args.job_id))
