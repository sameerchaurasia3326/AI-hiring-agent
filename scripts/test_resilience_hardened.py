import asyncio
import uuid
from loguru import logger
from src.utils.resilience import DistributedCircuitBreaker, with_resilience
from src.state.validator import validate_node
from src.db.database import AsyncSessionLocal
from src.db.models import CircuitBreakerState, CircuitBreakerStatus
from sqlalchemy import delete

async def simulate_failure():
    raise RuntimeError("Simulated service outage (Ollama is down)")

async def simulate_success():
    return {"status": "ok", "data": "processed"}

@validate_node
async def mock_crashing_node(state):
    raise ValueError("Something went terribly wrong in this node")

@validate_node
async def mock_malformed_node(state):
    # Returning an invalid job_id format (not a UUID)
    return {"job_id": "not-a-uuid-123", "pipeline_status": "INVALID_STATE"}

async def run_verification():
    logger.info("🧪 Starting Resilience & Safety Verification Suite")
    
    # 0. Clean slate
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CircuitBreakerState))
        await session.commit()

    # 1. Test Circuit Breaker Tripping
    logger.info("📡 Testing Circuit Breaker tripping...")
    cb = DistributedCircuitBreaker("test_service", failure_threshold=2, recovery_timeout_seconds=2)
    
    # First failure
    try: await with_resilience("test_service", simulate_failure)
    except: pass
    
    # Second failure -> should TRIP
    try: await with_resilience("test_service", simulate_failure)
    except: pass
    
    # Third call -> should be BLOCKED immediately
    try:
        await with_resilience("test_service", simulate_success)
    except RuntimeError as e:
        if "is OPEN" in str(e):
            logger.success("✅ Circuit successfully TRIPPED and blocked call")
        else:
            logger.error(f"❌ Unexpected error during trip check: {e}")

    # 2. Test Recovery & Probing
    logger.info("⏳ Waiting for recovery timeout (2s)...")
    await asyncio.sleep(2.1)
    
    # Attempt call -> should grant probe slot
    res = await with_resilience("test_service", simulate_success)
    if res["status"] == "ok":
        logger.success("✅ Circuit successfully recovered to CLOSED after successful probe")

    # 3. Test Node Validation & Crash Protection
    logger.info("🛡️ Testing Node Validation Shield...")
    
    # Test Crash recovery
    state = {"job_id": str(uuid.uuid4())}
    result = await mock_crashing_node(state)
    if result["pipeline_status"] == "FAILED" and "Runtime error" in result["error_log"][0]:
        logger.success("✅ Node crash caught and converted to safe FAILED state")

    # Test Malformed data cleaning
    result = await mock_malformed_node(state)
    if result.get("job_id") is None and "Validation error" in result.get("error_log", [[""]])[0]:
        logger.success("✅ Malformed node data caught and sanitized by decorator")

    logger.info("🏁 Verification Suite Complete.")

if __name__ == "__main__":
    asyncio.run(run_verification())
