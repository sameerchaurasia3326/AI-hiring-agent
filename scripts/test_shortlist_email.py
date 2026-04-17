import asyncio
import json
from src.tools.hiring_tools import send_shortlist_email_tool
from src.config import settings
from loguru import logger

async def test_shortlist_email():
    logger.info("🧪 Testing New Premium Shortlist Email Template...")
    
    # Mock data
    hr_email = settings.hr_email or "your-email@example.com"
    job_title = "Senior Full Stack Engineer"
    job_id = "test-job-uuid-123"
    candidates = [
        {"name": "Alice Smith", "email": "alice@example.com", "score": 92.5, "candidate_id": "cand-1"},
        {"name": "Bob Jones", "email": "bob@example.com", "score": 75.2, "candidate_id": "cand-2"},
        {"name": "Charlie Brown", "email": "charlie@example.com", "score": 45.8, "candidate_id": "cand-3"},
    ]
    
    try:
        result = await send_shortlist_email_tool.ainvoke({
            "hr_email": hr_email,
            "job_title": job_title,
            "job_id": job_id,
            "candidates_json": json.dumps(candidates)
        })
        logger.success(f"✅ Email tool execution result: {result}")
        logger.info(f"📬 Check your inbox ({hr_email}) to see the premium design!")
    except Exception as e:
        logger.error(f"❌ Shortlist Email Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_shortlist_email())
