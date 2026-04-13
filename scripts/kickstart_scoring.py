
import asyncio
import os
import sys
import uuid
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from src.graph.pipeline import get_pipeline
from src.state.schema import HiringState

async def kickstart():
    job_id = "d5f14ddc-d933-403b-8d0f-6b481cc6fae9"
    thread_id = f"job-{job_id}"
    
    # ── [NEW] Use purified get_pipeline (Step 015 hardening) ──
    pipeline = await get_pipeline()
    config = {"configurable": {"thread_id": thread_id}, "callbacks": []}

    print(f"🚀 Kickstarting scoring for job: {job_id}")
    print(f"🧵 Thread ID: {thread_id}")

    try:
        # We pass an empty input to resume from current checkpoint
        # This will trigger the next node in the graph (score_resumes)
        # because the state values are already in the checkpoint.
        # We use ainvoke with explicit config to avoid get_config errors.
        await pipeline.ainvoke(None, config)
        print("✅ Kickstart successful! Check your server logs for the LLM scoring output.")
    except Exception as e:
        print(f"❌ Failed to kickstart: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(kickstart())
