"""Celery worker configuration with Redis message broker."""
import os
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "document_intelligence",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 min max for large multi-page PDF processing
)
