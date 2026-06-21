"""
Celery tasks — Company Research Worker.
All tasks are async-wrapped via asyncio.run().
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from celery import Celery
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Import celery app from main config (adjust import path as needed)
try:
    from workers.celery_app import celery_app
except ImportError:
    celery_app = Celery("company_research", broker="redis://localhost:6379/0")


def _get_db_session():
    """Create async DB session (import lazily to avoid circular imports)."""
    from database import async_session_factory
    return async_session_factory()


# ─── Task 1: Fetch & process documents for a single company ──────────────────
@celery_app.task(
    name="company_research.run_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=900,
)
def run_research_pipeline_task(self, isin: str, force_full: bool = False):
    """
    Full research pipeline for one company:
    fetch docs → extract fields → update thesis → build report.
    """
    from .service import run_research_pipeline

    async def _run():
        async with _get_db_session() as db:
            return await run_research_pipeline(db, isin, force_full=force_full)

    try:
        result = asyncio.run(_run())
        logger.info("Research pipeline complete for %s: %s", isin, result)
        return result
    except Exception as exc:
        logger.error("Research pipeline failed for %s: %s", isin, exc)
        raise self.retry(exc=exc)


# ─── Task 2: Nightly batch — process all priority companies ──────────────────
@celery_app.task(
    name="company_research.batch_nightly",
    soft_time_limit=3600 * 4,
)
def batch_nightly_research():
    """
    Each night: identify companies due for refresh and queue individual tasks.
    Priority 1 (HIGH) companies: daily.
    Priority 2 (MED): weekly.
    Priority 3 (LOW): monthly.
    """
    from .models import Company

    async def _get_due_companies():
        async with _get_db_session() as db:
            now = datetime.utcnow()
            result = await db.execute(
                select(Company.isin, Company.research_priority)
                .where(
                    Company.is_active == True,
                    (Company.next_research_due == None) | (Company.next_research_due <= now),
                )
                .order_by(Company.research_priority.asc())
                .limit(500)
            )
            return result.all()

    due = asyncio.run(_get_due_companies())
    logger.info("Batch research: %d companies due", len(due))

    queued = 0
    for isin, priority in due:
        run_research_pipeline_task.apply_async(
            args=[isin],
            kwargs={"force_full": False},
            priority=priority,  # Celery priority: 1 = high
            countdown=queued * 5,  # stagger by 5s to avoid rate limits
        )
        queued += 1

    return {"queued": queued}


# ─── Task 3: Process a specific new document ─────────────────────────────────
@celery_app.task(
    name="company_research.process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def process_document_task(self, isin: str, doc_meta: dict):
    """
    Process a single newly discovered document:
    ingest → extract fields → update thesis → rebuild report.
    Triggered when a new BSE announcement is detected for a tracked company.
    """
    import httpx
    from .service import (
        ingest_document, update_research_fields,
        update_thesis, build_and_save_report,
    )
    from .models import Company, CompanyFinancials
    from sqlalchemy import select

    async def _run():
        async with _get_db_session() as db:
            company = await db.scalar(
                select(Company).where(Company.isin == isin)
            )
            if not company:
                return {"error": f"{isin} not found"}

            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
                doc, is_new = await ingest_document(db, doc_meta, http)

            if not doc or not is_new:
                return {"skipped": True, "reason": "duplicate"}

            from .models import DocumentChunk
            chunks_result = await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.chunk_index)
            )
            doc_text = "\n\n".join(c.text for c in chunks_result.scalars().all())

            changed_fields = await update_research_fields(
                db, isin, company.company_name, doc, doc_text
            )

            if not changed_fields:
                return {"new_doc": str(doc.id), "changed_fields": []}

            fin = await db.scalar(
                select(CompanyFinancials)
                .where(CompanyFinancials.isin == isin, CompanyFinancials.is_consolidated == True)
                .order_by(CompanyFinancials.fiscal_year.desc()).limit(1)
            )
            fin_dict = {}
            if fin:
                fin_dict = {
                    "revenue": float(fin.revenue or 0),
                    "ebitda_margin": float(fin.ebitda_margin or 0),
                    "net_debt": float(fin.net_debt or 0),
                    "debt_equity": float(fin.debt_equity or 0),
                    "roce": float(fin.roce or 0),
                }

            thesis = await update_thesis(db, company, changed_fields, fin_dict)
            trigger = f"{doc.doc_type} ({doc.quarter or doc.fiscal_year or doc.published_date})"
            report = await build_and_save_report(db, company, thesis, changed_fields, trigger)

            return {
                "isin": isin,
                "doc_id": str(doc.id),
                "changed_fields": changed_fields,
                "report_version": report.report_version,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("process_document_task failed for %s: %s", isin, exc)
        raise self.retry(exc=exc)


# ─── Task 4: Seed company universe from NSE/BSE master ───────────────────────
@celery_app.task(name="company_research.seed_universe")
def seed_universe_task():
    """
    Populate research_companies from markethub's NSE constituents API.
    Fetches NIFTY 500 + NIFTY MIDCAP 150 for broad coverage.
    Subsequent runs are idempotent (INSERT ... ON CONFLICT DO NOTHING).
    """
    import httpx
    from .models import Company
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    MARKETHUB_URL = "http://localhost:8000/api/v1/nse/constituents"
    INDICES = ["NIFTY 500", "NIFTY MIDCAP150"]

    async def _run():
        companies: dict[str, dict] = {}  # isin → row

        async with httpx.AsyncClient(timeout=30) as client:
            for index in INDICES:
                try:
                    r = await client.get(MARKETHUB_URL, params={"index": index})
                    r.raise_for_status()
                    payload = r.json()
                    items = payload.get("data", payload) if isinstance(payload, dict) else payload
                    for item in items:
                        isin = item.get("isin")
                        if isin and isin not in companies:
                            companies[isin] = item
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("Failed to fetch %s: %s", index, exc)

        if not companies:
            return {"inserted": 0, "error": "No data from markethub API"}

        async with _get_db_session() as db:
            inserted = 0
            for isin, item in companies.items():
                ticker = item.get("ticker", "")
                stmt = pg_insert(Company).values(
                    isin=isin,
                    symbol_nse=ticker,
                    symbol_bse=None,
                    bse_code=None,
                    company_name=item.get("company_name", ticker),
                    sector=None,
                    industry=item.get("industry"),
                    market_cap_cr=None,
                    market_cap_cat=None,
                ).on_conflict_do_nothing(index_elements=["isin"])
                await db.execute(stmt)
                inserted += 1
            await db.commit()
            return {"inserted": inserted}

    return asyncio.run(_run())


# ─── Task 5: Mark stale fields after N months ────────────────────────────────
@celery_app.task(name="company_research.mark_stale_fields")
def mark_stale_fields_task(stale_months: int = 6):
    """
    Weekly: mark fields as stale if their source doc is older than stale_months.
    Stale fields will be re-extracted on the next pipeline run.
    """
    from .models import ResearchField

    async def _run():
        async with _get_db_session() as db:
            cutoff = datetime.utcnow() - timedelta(days=stale_months * 30)
            result = await db.execute(
                select(ResearchField)
                .where(ResearchField.last_updated < cutoff, ResearchField.is_stale == False)
            )
            fields = result.scalars().all()
            for f in fields:
                f.is_stale = True
            await db.commit()
            return {"marked_stale": len(fields)}

    return asyncio.run(_run())


# ─── Beat schedule ────────────────────────────────────────────────────────────
CELERYBEAT_SCHEDULE = {
    "company-research-nightly": {
        "task": "company_research.batch_nightly",
        "schedule": {"hour": 1, "minute": 0},  # 1 AM IST daily
    },
    "company-research-mark-stale": {
        "task": "company_research.mark_stale_fields",
        "schedule": {"day_of_week": "sunday", "hour": 2, "minute": 0},
    },
}
