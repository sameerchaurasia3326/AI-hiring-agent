from __future__ import annotations

import asyncio
import functools
import random
import uuid
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional, TypeVar, Union, List
from loguru import logger
from contextvars import ContextVar


# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import select, update, insert, text
from src.db.database import AsyncSessionLocal

T = TypeVar("T")

# ── Global Rate Limiting Guards (Phase 5) ──────────────────────
# Per-process semaphore as requested in Phase 5
llm_semaphore = asyncio.Semaphore(2)
USE_GLOBAL_RATE_LIMIT = False # Structure for future Redis-based limiter


# ── Structured Logging (Phase 14 & 8) ──────────────────────────
# Global async-safe context for trace_id propagation
trace_context: ContextVar[str] = ContextVar("trace_id", default="system")

def set_trace_id(tid: str):
    """Set the global trace context ID."""
    if tid:
        trace_context.set(str(tid))

def get_trace_id() -> str:
    """Retrieve the current trace context ID or generate a new one if missing."""
    tid = trace_context.get()
    if tid == "system":
        # Check if we should generate a fresh one or stay as system
        return "system"
    return tid

def generate_trace_id() -> str:
    """Generate a unique trace sequence ID."""
    return str(uuid.uuid4())


class StructuredLogger:
    """Standardized logging format for production observability."""
    def __init__(self, trace_id: str = None, job_id: str = None):
        # Phase 15 & Request: Automatic discovery from context if not provided
        self.trace_id = trace_id or get_trace_id()
        self.job_id = str(job_id) if job_id else "system"


    def _log(self, level: str, event: str, status: str, metadata: Dict[str, Any] = None):
        payload = {
            "trace_id": self.trace_id,
            "job_id": self.job_id,
            "event": event,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {}
        }
        # Output as single-line JSON string for ELK/Datadog ingestion
        msg = json.dumps(payload)
        if level == "info": logger.info(msg)
        elif level == "error": logger.error(msg)
        elif level == "warning": logger.warning(msg)
        elif level == "success": logger.success(msg)

    def info(self, event: str, metadata: Dict[str, Any] = None):
        self._log("info", event, "PROCESSING", metadata)

    def warning(self, event: str, metadata: Dict[str, Any] = None):
        self._log("warning", event, "WARNING", metadata)

    def debug(self, event: str, metadata: Dict[str, Any] = None):
        # We map debug to info level in production logs
        self._log("info", event, "DEBUG", metadata)

    def success(self, event: str, metadata: Dict[str, Any] = None):
        self._log("success", event, "SUCCESS", metadata)

    def error(self, event: str, reason: str, metadata: Dict[str, Any] = None):
        meta = metadata or {}
        meta["reason"] = reason
        self._log("error", event, "FAILURE", meta)


def is_retryable_error(e: Exception) -> bool:
    """
    Phase 15: Retry Classification.
    Returns True for transient network/timeout issues.
    Returns False for permanent data/logic issues (ValueError, TypeError, etc.).
    """
    # Transient errors (Worth retrying)
    if isinstance(e, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    
    # Check for specific network-related string patterns in exceptions
    msg = str(e).lower()
    if any(p in msg for p in ["timeout", "connection reset", "broken pipe", "temporary failure"]):
        return True

    # Permanent errors (Do NOT retry)
    if isinstance(e, (ValueError, TypeError, KeyError, AttributeError, SyntaxError)):
        return False
        
    # Default to True for unknown exceptions to be safe, but log the choice
    return True

# ── Reliability & Timeout Guards (Phase 15) ────────────────────
async def replay_dlq(job_id: str) -> int:
    """
    Phase 15: Manual DLQ Replay Utility.
    Migrates all failed records for a job ID back to the Outbox for reprocessing.
    Atomic transaction with UPSERT (ON CONFLICT DO UPDATE).
    """
    from src.db.models import Outbox, DeadLetterQueue
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import uuid

    async with AsyncSessionLocal() as session:
        # 1. Fetch from DLQ
        stmt = select(DeadLetterQueue).where(DeadLetterQueue.job_id == uuid.UUID(job_id))
        res = await db_timeout(session.execute(stmt))
        items = res.scalars().all()
        
        if not items:
            logger.info(f"ℹ️ No items found in DLQ for job_id={job_id}")
            return 0
            
        count = 0
        for item in items:
            # 2. Re-insert into Outbox with UPSERT logic (ON CONFLICT DO UPDATE)
            # This handles cases where an Outbox record might still exist 
            # (e.g. if we failed to delete it during move to DLQ)
            insert_stmt = pg_insert(Outbox).values(
                job_id=item.job_id,
                type=item.type,
                version=getattr(item, "version", 1),
                payload=item.payload,
                status="PENDING",
                retry_count=0,
                created_at=datetime.now(timezone.utc)
            )
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["job_id", "type", "version"],
                set_={
                    "status": "PENDING",
                    "retry_count": 0,
                    "payload": item.payload,
                    "created_at": datetime.now(timezone.utc)
                }
            )
            await db_timeout(session.execute(upsert_stmt))
            
            # 3. Remove from Dead Letter Queue
            await session.delete(item)
            count += 1
            
        await session.commit()
        logger.success(f"✅ Replayed {count} failing items from DLQ for job_id={job_id}")
        return count


async def db_timeout(coro, timeout: float = 60.0):
    """
    Wraps an async database operation with a strict timeout.
    Classifies TimeoutError as retryable.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("🚨 [DB] Timeout reached after {}s", timeout)
        raise

# ── Safety Wrappers (Phase 10 & 7) ─────────────────────────────
async def retry_with_jitter(
    func: Callable[..., T], 
    max_retries: int = 3, 
    base_delay: float = 2.0,
    *args, 
    **kwargs
) -> T:
    """
    Standard Exponential Backoff with Randomized Jitter (Phase 15 & 7).
    Formula: wait = base * (2 ** attempt) + random.uniform(0, 1)
    Ensures distributed workers don't synchronize during retry storms.
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Phase 15 & Request: Integrated Classification
            if not is_retryable_error(e):
                logger.error(f"❌ Non-retryable error detected: {e}. Failing immediately.")
                raise e

            last_exception = e
            # Phase 7 & Request: Standardized formula
            wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"⚠️ Attempt {attempt+1} failed: {e}. Jittered retry in {wait:.2f}s...")
            await asyncio.sleep(wait)

    raise last_exception


async def safe_tool_call(func: Callable[..., Any], *args, **kwargs) -> Any:
    """
    Wrap all external calls to prevent pipeline crashes (Phase 10).
    Support both synchronous and asynchronous tools with automatic thread offloading.
    """
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # For sync functions, run in a separate thread to keep the event loop responsive
            return await asyncio.to_thread(func, *args, **kwargs)
    except Exception as e:
        logger.error(f"🛑 Safe tool call failed for {func.__name__ if hasattr(func, '__name__') else 'anonymous'}: {e}")
        return None


def validate_semantics(data: Any, state: Dict[str, Any]) -> bool:
    """
    Phase 15: Semantic Safety Guard.
    Validates that the LLM's scoring output is logically consistent with the job.
    """
    try:
        if not data or not isinstance(data, dict):
            return False
            
        # 1. Basic structure check
        if "score" not in data or "reasoning" not in data:
            return False
            
        # 2. Bound check (0-100)
        score = float(data.get("score", 0))
        if score < 0 or score > 100:
            return False
            
        return True
    except Exception as e:
        logger.error(f"⚠️ Semantic validation failure: {e}")
        return False



# ── Event Store Helper (Phase 1 & 4) ───────────────────────────
async def log_event(job_id: str, event_type: str, payload: Dict[str, Any] = None):
    """Source of Truth: Log a critical milestone to the EventStore."""
    from src.db.models import EventStore
    try:
        async with AsyncSessionLocal() as session:
            event = EventStore(
                job_id=job_id,
                event_type=event_type,
                payload=payload or {}
            )
            session.add(event)
            await session.commit()
    except Exception as e:
        logger.error(f"❌ Failed to log event {event_type} for job {job_id}: {e}")

# ── Lease-Based Job Locking (Phase 1 & 11) ─────────────────────

class JobLease:
    """Distributed coordination for job processing using PostgreSQL leases."""
    @staticmethod
    async def acquire(job_id: str, worker_id: str) -> bool:
        """
        Atomic lease acquisition:
        - Takes lock if nobody owns it OR if existing lease is > 5 mins old.
        """
        from src.db.models import Job
        from sqlalchemy import update, or_, and_, text
        
        try:
            async with AsyncSessionLocal() as session:
                # Phase 1 & 11: Lease logic
                from datetime import timedelta
                expire_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

                stmt = (
                    update(Job)
                    .where(Job.id == job_id)
                    .where(
                        or_(
                            Job.locked_by == None,
                            Job.locked_at < expire_threshold
                        )
                    )
                    .values(
                        locked_by=worker_id,
                        locked_at=datetime.now(timezone.utc)
                    )
                )

                
                # We need to execute and check if any rows were affected
                result = await session.execute(stmt)
                await session.commit()
                
                success = result.rowcount > 0
                if success:
                    logger.info(f"🔑 Lease ACQUIRED for job {job_id} by worker {worker_id}")
                else:
                    logger.warning(f"🔒 Lease DENIED for job {job_id}: Already locked by another worker")
                return success
        except Exception as e:
            logger.error(f"❌ Lease acquisition failure for job {job_id}: {e}")
            return False

    @staticmethod
    async def release(job_id: str, worker_id: str):
        """Release the lease only if this worker is the current owner."""
        from src.db.models import Job
        from sqlalchemy import update
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    update(Job)
                    .where(Job.id == job_id)
                    .where(Job.locked_by == worker_id)
                    .values(locked_by=None, locked_at=None)
                )
                await session.execute(stmt)
                await session.commit()
                logger.debug(f"🔓 Lease RELEASED for job {job_id} by worker {worker_id}")
        except Exception as e:
            logger.error(f"❌ Lease release failure for job {job_id}: {e}")

    @staticmethod
    async def refresh(job_id: str, worker_id: str):
        """Phase 1.5: Atomic lease heartbeat refresh."""
        from src.db.models import Job
        from sqlalchemy import update
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    update(Job)
                    .where(Job.id == job_id)
                    .where(Job.locked_by == worker_id)
                    .values(locked_at=datetime.now(timezone.utc))
                )
                await session.execute(stmt)
                await session.commit()
                # Internal log level low to prevent noise
                logger.debug(f"💓 Heartbeat REFRESHED for job {job_id}")
        except Exception as e:
            logger.warning(f"⚠️ Heartbeat failed for job {job_id}: {e}")

async def _heartbeat_worker(job_id: str, worker_id: str, stop_event: asyncio.Event):
    """Resilient background task that refreshes the job lease every 30s."""
    while not stop_event.is_set():
        try:
            # Wait for 30s or until stopped
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
                break # If we stop_event.wait() finishes, it means we stop
            except asyncio.TimeoutError:
                # Cycle reached, perform refresh
                await JobLease.refresh(job_id, worker_id)
        except Exception as e:
            logger.error(f"💀 Critical failure in heartbeat loop for {job_id}: {e}")
            await asyncio.sleep(5) # Prevent tight loop on error


def lease_guard(func):
    """
    Decorator to ensure a worker owns the job lease before executing a node.
    Phase 1.3: If lock not acquired -> EXIT safely.
    """
    @functools.wraps(func)
    async def wrapper(state: Dict[str, Any], *args, **kwargs):
        job_id = state.get("job_id")
        
        # Phase 1: Every distributed worker needs a unique UUID identity
        # We use a stable UUID per process/loop context
        worker_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"worker-{id(asyncio.get_event_loop())}")
        
        if not job_id:

            return await func(state, *args, **kwargs)

        # Attempt to acquire lease (Phase 1.2 logic)
        acquired = await JobLease.acquire(job_id, worker_id)
        if not acquired:
            # Phase 1.3: Exit safely if another worker is busy here
            logger.warning(f"⏩ Skipping node {func.__name__}: Job {job_id} is locked by another worker")
            return state

        # ── Start Heartbeat ──────────────────────────────────────
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _heartbeat_worker(job_id, worker_id, stop_heartbeat)
        )

        try:
            # Execute node
            result = await func(state, *args, **kwargs)
            return result
        finally:
            # ── Stop Heartbeat ───────────────────────────────────
            stop_heartbeat.set()
            try:
                # Wait briefly for worker to see event
                await asyncio.wait_for(heartbeat_task, timeout=1.0)
            except (asyncio.TimeoutError, Exception):
                heartbeat_task.cancel()

            # Phase 1.4: Release lock on completion
            await JobLease.release(job_id, worker_id)

            
    return wrapper


