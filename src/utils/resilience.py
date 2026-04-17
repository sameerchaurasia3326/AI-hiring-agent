from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Any, TypeVar
from loguru import logger
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import AsyncSessionLocal
from src.db.models import CircuitBreakerState, CircuitBreakerStatus

T = TypeVar("T")

class DistributedCircuitBreaker:
    """
    PostgreSQL-backed Distributed Circuit Breaker.
    Protects services (like Ollama/OpenAI) across multiple Celery/API workers.
    """

    def __init__(self, service_name: str, 
                 failure_threshold: int = 3, 
                 recovery_timeout_seconds: int = 60,
                 probe_lease_seconds: int = 300):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.probe_lease = probe_lease_seconds

    async def _get_or_create_state(self, session: AsyncSession) -> CircuitBreakerState:
        """Ensures the service row exists in the DB."""
        stmt = select(CircuitBreakerState).where(CircuitBreakerState.service_name == self.service_name)
        result = await session.execute(stmt)
        state = result.scalar_one_or_none()

        if not state:
            state = CircuitBreakerState(
                service_name=self.service_name,
                status=CircuitBreakerStatus.CLOSED,
                consecutive_failures=0
            )
            session.add(state)
            await session.commit()
            await session.refresh(state)
        return state

    async def is_available(self) -> bool:
        """
        Main entry point for workers.
        Returns:
            - True if CLOSED
            - True if it just successfully transitioned from OPEN/ZOMBIE to HALF_OPEN (Probe slot granted)
            - False if OPEN or another worker is already probing.
        """
        async with AsyncSessionLocal() as session:
            state = await self._get_or_create_state(session)

            if state.status == CircuitBreakerStatus.CLOSED:
                return True

            # If OPEN, check if recovery timeout has passed
            now = datetime.now(timezone.utc)
            
            # Atomic transition logic: OPEN -> HALF_OPEN or ZOMBIE_HALF_OPEN -> HALF_OPEN (reset)
            recovery_cutoff = now - timedelta(seconds=self.recovery_timeout)
            lease_cutoff = now - timedelta(seconds=self.probe_lease)

            stmt = (
                update(CircuitBreakerState)
                .where(
                    and_(
                        CircuitBreakerState.service_name == self.service_name,
                        or_(
                            and_(CircuitBreakerState.status == CircuitBreakerStatus.OPEN, 
                                 CircuitBreakerState.last_failure_at < recovery_cutoff),
                            and_(CircuitBreakerState.status == CircuitBreakerStatus.HALF_OPEN,
                                 CircuitBreakerState.probe_started_at < lease_cutoff)
                        )
                    )
                )
                .values(
                    status=CircuitBreakerStatus.HALF_OPEN,
                    probe_started_at=now,
                    error_message="Probe started"
                )
                .returning(CircuitBreakerState)
            )

            result = await session.execute(stmt)
            updated_state = result.scalar_one_or_none()

            if updated_state:
                logger.warning("🛡️ [CB:{}] Granted HALF_OPEN probe slot (recovery or zombie-rescue)", self.service_name)
                await session.commit()
                return True

            return False

    async def record_success(self):
        """Service worked. Reclose the circuit."""
        async with AsyncSessionLocal() as session:
            stmt = (
                update(CircuitBreakerState)
                .where(CircuitBreakerState.service_name == self.service_name)
                .values(
                    status=CircuitBreakerStatus.CLOSED,
                    consecutive_failures=0,
                    error_message=None,
                    probe_started_at=None
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.info("✅ [CB:{}] Circuit CLOSED (Recovered)", self.service_name)

    async def record_failure(self, error: str):
        """Service failed. Increment failures and potentially open circuit."""
        async with AsyncSessionLocal() as session:
            # 1. Increment failures
            state = await self._get_or_create_state(session)
            new_failures = state.consecutive_failures + 1
            now = datetime.now(timezone.utc)

            new_status = state.status
            if new_failures >= self.failure_threshold:
                new_status = CircuitBreakerStatus.OPEN
                logger.error("🚨 [CB:{}] Threshold reached. Opening circuit for {}s", self.service_name, self.recovery_timeout)

            stmt = (
                update(CircuitBreakerState)
                .where(CircuitBreakerState.service_name == self.service_name)
                .values(
                    status=new_status,
                    consecutive_failures=new_failures,
                    last_failure_at=now,
                    error_message=str(error)[:500],
                    probe_started_at=None # Reset probe on failure
                )
            )
            await session.execute(stmt)
            await session.commit()

async def with_resilience(service_name: str, 
                          func: Callable[..., Any], 
                          max_retries: int = 3,
                          base_delay: float = 2.0,
                          *args, **kwargs) -> Any:
    """
    Wrapper to execute a function with the distributed circuit breaker 
    AND jittered retries (Unified standard).
    """
    from src.utils.production_safety import retry_with_jitter

    async def _wrapped_call(*wrapped_args, **wrapped_kwargs):
        cb = DistributedCircuitBreaker(service_name)
        
        if not await cb.is_available():
            logger.warning("⛔ [CB:{}] Circuit is OPEN - skipping execution", service_name)
            raise RuntimeError(f"Circuit breaker for {service_name} is OPEN")

        try:
            # Phase 15 & Request: Enforce strict 60s timeout for all external calls
            if asyncio.iscoroutinefunction(func):
                res = await asyncio.wait_for(func(*wrapped_args, **wrapped_kwargs), timeout=60)
            else:
                # For sync functions, we wrap in a thread or just call (timeout is less effective for sync)
                # But most external tools here are async (LLM.ainvoke, etc.)
                res = func(*wrapped_args, **wrapped_kwargs)
                
            # SUCCESS!
            await cb.record_success()
            return res
        except asyncio.TimeoutError:
            logger.error("🚨 [CB:{}] EXTERNAL_CALL_TIMEOUT after 60s", service_name)
            await cb.record_failure(f"TimeoutError: {service_name} hung for > 60s")
            raise
        except Exception as e:
            # FAILURE!
            await cb.record_failure(str(e))
            raise e


    # Execute with unified jittered backoff
    return await retry_with_jitter(
        _wrapped_call,
        max_retries=max_retries,
        base_delay=base_delay,
        *args,
        **kwargs
    )

