"""
Celery application instance — imported by all task modules and by PM2/CLI.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
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
    task_default_queue="default",
    task_routes={
        "workers.technical_analysis.tasks.*": {"queue": "technical_high"},
        "workers.order_tracking.tasks.*": {"queue": "default"},
        "workers.company_research.tasks.*": {"queue": "default"},
        "workers.subcontract_opportunity.tasks.*": {"queue": "default"},
        "workers.master_tracker.tasks.*": {"queue": "default"},
    },
    beat_schedule={
        # ── All market-data workers fire at 7:00 PM IST (13:30 UTC) Mon–Fri ──
        # Data is complete by 7 PM; last trading day logic handles holidays/weekends.

        # Order scraping (NSE + BSE announcements)
        "scrape-nse-orders-daily": {
            "task": "workers.order_tracking.tasks.scrape_nse",
            "schedule": crontab(hour=13, minute=30, day_of_week="1-5"),
        },
        "scrape-bse-orders-daily": {
            "task": "workers.order_tracking.tasks.scrape_bse",
            "schedule": crontab(hour=13, minute=35, day_of_week="1-5"),
        },

        # Technical analysis (RS ratings, patterns, scores)
        "technical-scan-daily": {
            "task": "workers.technical_analysis.tasks.score_universe",
            "schedule": crontab(hour=13, minute=40, day_of_week="1-5"),
        },

        # Master tracker signals
        "master-tracker-daily": {
            "task": "workers.master_tracker.tasks.run_master_tracker",
            "schedule": crontab(hour=13, minute=50, day_of_week="1-5"),
        },

        # Company research (AI extraction) — daily at 7:30 PM IST (14:00 UTC)
        "run-research-pipeline-daily": {
            "task": "workers.company_research.tasks.run_research_pipeline",
            "schedule": crontab(hour=14, minute=0, day_of_week="1-5"),
        },

        # Subcontract opportunity scan — every Saturday at 8:00 AM IST (02:30 UTC)
        "subcontract-weekly": {
            "task": "workers.subcontract_opportunity.tasks.run_full_scan",
            "schedule": crontab(hour=2, minute=30, day_of_week="6"),
        },
    },
)

# Make `celery_app` importable as `app` for CLI convenience
app = celery_app
