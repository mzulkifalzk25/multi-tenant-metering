"""Celery application factory: broker, backend, and beat schedule."""

from __future__ import annotations

from celery import Celery

from src.frameworks.settings import Settings


def create_celery_app(settings: Settings) -> Celery:
    app = Celery(
        "document_pipeline",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["src.services.celery_tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        beat_schedule={
            "schedule-recovery": {
                "task": "src.services.celery_tasks.schedule_recovery_task",
                "schedule": settings.recovery_scan_interval_seconds,
            },
        },
    )
    return app
