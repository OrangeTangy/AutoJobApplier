from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery = Celery(
    "autojobapplier",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.poll_ingestion_source": {"queue": "ingestion"},
        "app.workers.tasks.prepare_application_draft": {"queue": "generation"},
        "app.workers.tasks.run_submission_task": {"queue": "submission"},
    },
    beat_schedule={
        "poll-all-sources-every-hour": {
            "task": "app.workers.tasks.poll_all_sources",
            "schedule": crontab(minute=0),          # top of every hour
        },
        "cleanup-stale-drafts-daily": {
            "task": "app.workers.tasks.cleanup_stale_drafts",
            "schedule": crontab(hour=3, minute=0),  # 3 AM UTC
        },
    },
)
