"""
src/scheduler/celery_app.py
────────────────────────────
Celery application configuration.
Broker: Redis | Backend: Redis
"""
from __future__ import annotations

from celery import Celery
from src.config import settings

celery_app = Celery(
    "hiring_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.scheduler.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry failed tasks up to 3 times
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Beat schedule (optional periodic checks)
    beat_schedule={},
)
