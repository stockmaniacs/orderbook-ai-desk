"""
Celery application instance — imported by all task modules and by PM2/CLI.
"""
from __future__ import annotations

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "orderbook",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    include=[
        "workers.order_tracking.tasks",
        "workers.company_research.tasks",
        "workers.subcontract_opportunity.tasks",
        "workers.master_tracker.tasks",
        "workers.technical_analysis.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_routes={
        "workers.technical_analysis.tasks.*": {"queue": "technical_high"},
        "workers.order_tracking.tasks.*": {"queue": "default"},
        "workers.company_research.tasks.*": {"queue": "default"},
        "workers.subcontract_opportunity.tasks.*": {"queue": "default"},
        "workers.master_tracker.tasks.*": {"queue": "default"},
    },
)

# Make `celery_app` importable as `app` for CLI convenience
app = celery_app
