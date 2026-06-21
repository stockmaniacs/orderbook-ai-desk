"""
Order Tracking Worker — Celery Tasks
All background jobs: scraping, extraction, metric computation, AI analysis.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime
from typing import Optional

from celery import shared_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1: Scrape BSE announcements for order wins
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.scrape_bse",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    acks_late=True,
)
def scrape_bse_orders(self, days_back: int = 1) -> dict:
    """Fetch BSE corporate announcements and queue AI extraction for order-related ones."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _scrape_bse_async(days_back)
    )


async def _scrape_bse_async(days_back: int) -> dict:
    from database import get_async_session_context
    from .scrapers.bse_scraper import BSEOrderScraper

    async with BSEOrderScraper() as scraper:
        announcements = await scraper.fetch_recent_announcements(days_back=days_back)

    logger.info("BSE: fetched %d order-related announcements", len(announcements))
    queued = 0

    async with get_async_session_context() as db:
        for ann in announcements:
            if not ann.get("isin"):
                continue
            # Enqueue PDF download + extraction
            extract_order_from_announcement.delay(ann)
            queued += 1

    return {"source": "BSE", "fetched": len(announcements), "queued": queued}


# ---------------------------------------------------------------------------
# Task 2: Scrape NSE filings
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.scrape_nse",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    acks_late=True,
)
def scrape_nse_orders(self, days_back: int = 1) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _scrape_nse_async(days_back)
    )


async def _scrape_nse_async(days_back: int) -> dict:
    from .scrapers.nse_scraper import NSEOrderScraper

    async with NSEOrderScraper() as scraper:
        filings = await scraper.fetch_recent_filings(days_back=days_back)

    logger.info("NSE: fetched %d order-related filings", len(filings))

    for filing in filings:
        if filing.get("isin"):
            extract_order_from_announcement.delay(filing)

    return {"source": "NSE", "fetched": len(filings), "queued": len(filings)}


# ---------------------------------------------------------------------------
# Task 3: Extract order details from a single announcement
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.extract_order",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def extract_order_from_announcement(self, ann: dict) -> Optional[str]:
    """
    1. Download PDF and extract text
    2. Send to Gemini for structured extraction
    3. Persist OrderAnnouncement record
    4. Queue metric recompute
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _extract_async(ann)
    )


async def _extract_async(ann: dict) -> Optional[str]:
    import httpx
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from database import get_async_session_context
    from .models import OrderAnnouncement
    from .scrapers.pdf_parser import extract_text_from_url
    from .ai.extractor import extract_order_details, is_valid_order_extraction
    from .service import _fiscal_quarter

    isin = ann.get("isin", "")
    content_hash = ann.get("content_hash", "")

    async with get_async_session_context() as db:
        # Dedup check
        existing = await db.execute(
            select(OrderAnnouncement).where(
                OrderAnnouncement.content_hash == content_hash
            )
        )
        if existing.scalar_one_or_none():
            logger.debug("Order already processed: %s", content_hash)
            return None

        # Download PDF text
        raw_text = ann.get("raw_text", "")
        pdf_url = ann.get("pdf_url")
        if pdf_url:
            async with httpx.AsyncClient(timeout=60) as client:
                pdf_text = await extract_text_from_url(client, pdf_url)
                if pdf_text:
                    raw_text = pdf_text[:8000]

        if not raw_text:
            logger.warning("No text for %s — skipping", ann.get("source_id"))
            return None

        # AI extraction
        extracted = await extract_order_details(raw_text)

        if not is_valid_order_extraction(extracted):
            logger.info("Low-confidence extraction for %s — stored as failed", ann.get("source_id"))
            processing_status = "FAILED"
        else:
            processing_status = "DONE"

        # Fiscal quarter
        announced_date_str = ann.get("announced_date", date.today().isoformat())
        try:
            announced_date = date.fromisoformat(announced_date_str)
        except Exception:
            announced_date = date.today()

        quarter_label, fy, q_num = _fiscal_quarter(announced_date)

        # Build record
        record = OrderAnnouncement(
            source=ann["source"],
            source_id=ann["source_id"],
            source_url=ann.get("source_url"),
            isin=isin,
            company_name=extracted.get("company_name") or ann.get("company_name", ""),
            symbol_nse=ann.get("symbol_nse"),
            symbol_bse=ann.get("symbol_bse"),
            customer_name=extracted.get("customer_name"),
            order_amount_cr=extracted.get("order_amount_cr"),
            order_amount_raw=extracted.get("order_amount_raw"),
            order_currency=extracted.get("order_currency", "INR"),
            order_type=extracted.get("order_type"),
            project_description=extracted.get("project_description"),
            announced_date=announced_date,
            execution_start=(
                date.fromisoformat(extracted["execution_start"])
                if extracted.get("execution_start") else None
            ),
            execution_end=(
                date.fromisoformat(extracted["execution_end"])
                if extracted.get("execution_end") else None
            ),
            duration_months=extracted.get("duration_months"),
            sector_category=extracted.get("sector_category"),
            project_type=extracted.get("project_type"),
            is_repeat_order=extracted.get("is_repeat_order", False),
            is_framework_contract=extracted.get("is_framework_contract", False),
            fiscal_year=fy,
            quarter=quarter_label,
            raw_text=raw_text[:10000],
            extraction_confidence=extracted.get("extraction_confidence"),
            extraction_model=extracted.get("extraction_model"),
            extraction_notes=extracted.get("extraction_notes"),
            processing_status=processing_status,
            content_hash=content_hash,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        order_id = str(record.id)

    # Trigger metric recompute if order is valid
    if processing_status == "DONE" and isin:
        recompute_metrics.delay(isin)

    return order_id


# ---------------------------------------------------------------------------
# Task 4: Recompute all metrics for a company
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.recompute_metrics",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def recompute_metrics(self, isin: str) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _recompute_async(isin)
    )


async def _recompute_async(isin: str) -> dict:
    from database import get_async_session_context
    from .service import compute_metrics

    async with get_async_session_context() as db:
        metrics = await compute_metrics(db, isin)
        await db.commit()

    # Publish event to Redis stream
    try:
        import os
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"))
        await r.xadd(
            "stream:order_book_updated",
            {"isin": isin, "timestamp": datetime.utcnow().isoformat()},
        )
        await r.aclose()
    except Exception as exc:
        logger.warning("Redis publish failed: %s", exc)

    # Queue AI analysis refresh
    generate_ai_analysis.delay(isin)

    return {"isin": isin, "score": float(metrics.order_acceleration_score or 0)}


# ---------------------------------------------------------------------------
# Task 5: Generate AI analysis summary
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.generate_ai_analysis",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    acks_late=True,
)
def generate_ai_analysis(self, isin: str) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        _ai_analysis_async(isin)
    )


async def _ai_analysis_async(isin: str) -> dict:
    from sqlalchemy import select, desc
    from database import get_async_session_context
    from .models import OrderAISummary, OrderBookMetrics, OrderAnnouncement, OrderBookSnapshot
    from .ai.analyzer import generate_analysis

    async with get_async_session_context() as db:
        # Fetch metrics
        res = await db.execute(
            select(OrderBookMetrics).where(OrderBookMetrics.isin == isin)
        )
        metrics = res.scalar_one_or_none()
        if not metrics:
            return {"status": "skipped", "reason": "no metrics"}

        # Fetch recent orders
        res2 = await db.execute(
            select(OrderAnnouncement)
            .where(
                OrderAnnouncement.isin == isin,
                OrderAnnouncement.processing_status == "DONE",
            )
            .order_by(desc(OrderAnnouncement.announced_date))
            .limit(15)
        )
        orders = res2.scalars().all()

        # Fetch quarterly snapshots
        res3 = await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.isin == isin)
            .order_by(OrderBookSnapshot.fiscal_year, OrderBookSnapshot.quarter_num)
            .limit(8)
        )
        snaps = res3.scalars().all()

        metrics_dict = {
            c.name: getattr(metrics, c.name)
            for c in metrics.__table__.columns
        }
        orders_list = [
            {c.name: getattr(o, c.name) for c in o.__table__.columns}
            for o in orders
        ]
        snaps_list = [
            {c.name: getattr(s, c.name) for c in s.__table__.columns}
            for s in snaps
        ]

        sector = orders[0].sector_category if orders else "Industrial"

        analysis = await generate_analysis(
            isin=isin,
            company_name=metrics.company_name or isin,
            sector=sector,
            metrics=metrics_dict,
            recent_orders=orders_list,
            quarterly_snapshots=snaps_list,
        )

        # Persist
        summary = OrderAISummary(
            isin=isin,
            trend=analysis.get("trend"),
            trend_confidence=analysis.get("trend_confidence"),
            executive_summary=analysis.get("executive_summary"),
            pipeline_analysis=analysis.get("pipeline_analysis"),
            customer_concentration_note=analysis.get("customer_concentration_note"),
            geographic_mix_note=analysis.get("geographic_mix_note"),
            risk_factors=analysis.get("risk_factors"),
            positive_signals=analysis.get("positive_signals"),
            bull_narrative=analysis.get("bull_narrative"),
            base_narrative=analysis.get("base_narrative"),
            bear_narrative=analysis.get("bear_narrative"),
            ai_verdict=analysis.get("ai_verdict"),
            model_version=analysis.get("model_version"),
        )
        db.add(summary)
        await db.commit()

    return {"isin": isin, "trend": analysis.get("trend")}


# ---------------------------------------------------------------------------
# Task 6: Build quarterly snapshot for all active ISINs
# ---------------------------------------------------------------------------
@shared_task(
    name="order_tracking.build_quarterly_snapshots",
    bind=True,
    max_retries=1,
)
def build_quarterly_snapshots(self) -> dict:
    """End-of-quarter job: rebuild all snapshots and recompute metrics."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_snapshots_async())


async def _snapshots_async() -> dict:
    from sqlalchemy import select, func
    from database import get_async_session_context
    from .models import OrderAnnouncement
    from .service import upsert_quarterly_snapshot, _fiscal_quarter

    async with get_async_session_context() as db:
        # Get all distinct ISINs with orders
        res = await db.execute(
            select(OrderAnnouncement.isin)
            .where(OrderAnnouncement.processing_status == "DONE")
            .distinct()
        )
        isins = [row[0] for row in res.all()]

    for isin in isins:
        recompute_metrics.delay(isin)

    return {"isins_processed": len(isins)}


# ---------------------------------------------------------------------------
# Celery Beat schedule
# ---------------------------------------------------------------------------
CELERYBEAT_SCHEDULE = {
    "scrape-bse-orders-every-5min": {
        "task": "order_tracking.scrape_bse",
        "schedule": 300,  # 5 minutes
        "options": {"queue": "order_tracking"},
        "kwargs": {"days_back": 1},
    },
    "scrape-nse-orders-every-5min": {
        "task": "order_tracking.scrape_nse",
        "schedule": 300,
        "options": {"queue": "order_tracking"},
        "kwargs": {"days_back": 1},
    },
    "quarterly-snapshot-rebuild": {
        "task": "order_tracking.build_quarterly_snapshots",
        "schedule": 86400,  # daily
        "options": {"queue": "order_tracking"},
    },
}
