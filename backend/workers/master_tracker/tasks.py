"""
Celery tasks — Master Tracker Worker.

Tasks:
  - ingest_quarterly_result_task: process new quarterly result
  - scan_all_alerts_task: nightly alert scan across all tracked stocks
  - update_technical_snapshots_task: daily price / technical indicator update
  - recalculate_all_scores_task: nightly risk-reward recalculation
  - seed_from_research_worker_task: pull thesis / scenarios from Company Research worker
  - auto_set_targets_task: AI-driven pre-result target setting
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import select, text

from database import get_async_session_context
from .service import (
    add_or_update_stock,
    get_alerts,
    get_master_dashboard,
    ingest_quarterly_actual,
    recalculate_scores,
    set_quarterly_target,
    update_technical_snapshot,
)
from .models import TrackedStock, ThesisAlert
from .comparison_engine import compute_technical_score

log = logging.getLogger(__name__)


# ─── Ingest quarterly actual ──────────────────────────────────────────────────
@shared_task(
    name="tracker.ingest_quarterly_result",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="tracker_high",
)
def ingest_quarterly_result_task(
    self,
    isin: str,
    fiscal_year: int,
    quarter: str,
    **result_fields: Any,
) -> dict:
    """
    Process a new quarterly result for a tracked stock.
    Computes GREEN/YELLOW/RED signals, generates alerts, updates scores.
    """
    try:
        return asyncio.run(_ingest(isin, fiscal_year, quarter, **result_fields))
    except Exception as exc:
        log.exception("ingest_quarterly_result_task failed for %s: %s", isin, exc)
        raise self.retry(exc=exc)


async def _ingest(isin: str, fy: int, q: str, **fields: Any) -> dict:
    async with get_async_session_context() as db:
        result = await ingest_quarterly_actual(db, isin, fy, q, **fields)
        await recalculate_scores(db, isin)
        return result


# ─── Set quarterly target (pre-result AI estimation) ─────────────────────────
@shared_task(
    name="tracker.set_quarterly_target",
    bind=True,
    queue="tracker_normal",
)
def set_quarterly_target_task(
    self,
    isin: str,
    fiscal_year: int,
    quarter: str,
    **target_fields: Any,
) -> dict:
    try:
        return asyncio.run(_set_target(isin, fiscal_year, quarter, **target_fields))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _set_target(isin: str, fy: int, q: str, **fields: Any) -> dict:
    async with get_async_session_context() as db:
        await set_quarterly_target(db, isin, fy, q, **fields)
    return {"status": "ok", "isin": isin, "quarter": q}


# ─── Auto-set targets from AI before result season ────────────────────────────
@shared_task(
    name="tracker.auto_set_targets",
    queue="tracker_normal",
    time_limit=3600,
)
def auto_set_targets_task(fiscal_year: int, quarter: str) -> dict:
    """
    For each tracked stock without a target for the upcoming quarter,
    derive a target from the previous actuals + growth thesis.
    """
    return asyncio.run(_auto_set_all_targets(fiscal_year, quarter))


async def _auto_set_all_targets(fy: int, q: str) -> dict:
    async with get_async_session_context() as db:
        # Get all active stocks
        result = await db.execute(
            select(TrackedStock).where(TrackedStock.tracking_status == "ACTIVE")
        )
        stocks = result.scalars().all()

        set_count = 0
        for stock in stocks:
            # Check if target already set
            existing = await db.execute(text("""
            SELECT 1 FROM mt_quarterly_targets
            WHERE isin = :isin AND fiscal_year = :fy AND quarter = :q
            """), {"isin": stock.isin, "fy": fy, "q": q})
            if existing.fetchone():
                continue

            # Get last actual as baseline
            last_actual = await db.execute(text("""
            SELECT * FROM mt_quarterly_actuals
            WHERE isin = :isin
            ORDER BY fiscal_year DESC, quarter DESC
            LIMIT 1
            """), {"isin": stock.isin})
            la = last_actual.fetchone()
            if not la:
                continue

            # Apply expected growth from thesis
            growth_rate = (stock.expected_cagr_3y or 15) / 100 / 4  # quarterly

            await set_quarterly_target(
                db, stock.isin, fy, q,
                expected_revenue_cr=float(la.revenue_cr) * (1 + growth_rate) if la.revenue_cr else None,
                expected_ebitda_cr=float(la.ebitda_cr) * (1 + growth_rate) if la.ebitda_cr else None,
                expected_ebitda_margin=la.ebitda_margin,
                expected_pat_cr=float(la.pat_cr) * (1 + growth_rate) if la.pat_cr else None,
                expected_order_book_cr=float(la.order_book_cr) if la.order_book_cr else None,
                set_by="AI_AUTO",
                confidence=0.6,
                notes=f"Auto-derived from {la.quarter} FY{la.fiscal_year} actuals + {growth_rate*400:.0f}% quarterly growth assumption",
            )
            set_count += 1

        return {"status": "ok", "targets_set": set_count, "quarter": q}


# ─── Daily technical snapshot update ─────────────────────────────────────────
@shared_task(
    name="tracker.update_technical_snapshots",
    queue="tracker_normal",
    time_limit=3600,
)
def update_technical_snapshots_task(isins: list[str] | None = None) -> dict:
    """
    Pull latest price + technical indicators for all tracked stocks.
    In production: integrate with NSE/BSE WebSocket or a market data vendor.
    """
    return asyncio.run(_update_all_technicals(isins))


async def _update_all_technicals(isins: list[str] | None) -> dict:
    async with get_async_session_context() as db:
        if isins is None:
            result = await db.execute(
                select(TrackedStock.isin).where(TrackedStock.tracking_status == "ACTIVE")
            )
            isins = [r.isin for r in result.fetchall()]

        today = date.today()
        updated = 0
        for isin in isins:
            try:
                # In production, fetch from market data API here
                # Here we use a placeholder that reads from the last known snapshot
                last = await db.execute(text("""
                SELECT close_price, sma_50, sma_200, rsi_14
                FROM mt_technical_snapshots
                WHERE isin = :isin ORDER BY snapshot_date DESC LIMIT 1
                """), {"isin": isin})
                snap = last.fetchone()
                if not snap:
                    continue

                await update_technical_snapshot(
                    db, isin, today,
                    close_price=snap.close_price,
                    sma_50=snap.sma_50,
                    sma_200=snap.sma_200,
                    rsi_14=snap.rsi_14,
                    above_sma_50=snap.close_price > snap.sma_50 if snap.sma_50 else None,
                    above_sma_200=snap.close_price > snap.sma_200 if snap.sma_200 else None,
                )
                updated += 1
            except Exception as e:
                log.warning("Technical update failed for %s: %s", isin, e)

    return {"status": "ok", "updated": updated}


# ─── Nightly alert scan ───────────────────────────────────────────────────────
@shared_task(
    name="tracker.scan_alerts",
    queue="tracker_normal",
)
def scan_alerts_task() -> dict:
    """
    Nightly pass: check for technical breakdowns, valuation extremes,
    consecutive misses that haven't triggered alerts yet.
    """
    return asyncio.run(_scan_all())


async def _scan_all() -> dict:
    async with get_async_session_context() as db:
        result = await db.execute(
            select(TrackedStock).where(
                TrackedStock.tracking_status == "ACTIVE",
                TrackedStock.consecutive_red >= 2,
            )
        )
        at_risk = result.scalars().all()
        alerts_created = 0

        for stock in at_risk:
            # Check if we already have an unread THESIS_DETERIORATING alert
            existing = await db.execute(text("""
            SELECT 1 FROM mt_alerts
            WHERE isin = :isin AND alert_type = 'THESIS_DETERIORATING'
              AND is_read = false
              AND triggered_at > NOW() - INTERVAL '30 days'
            """), {"isin": stock.isin})
            if existing.fetchone():
                continue

            db.add(ThesisAlert(
                isin=stock.isin,
                company_name=stock.company_name,
                alert_type="THESIS_DETERIORATING",
                severity="HIGH",
                title=f"⚠ {stock.company_name} — {stock.consecutive_red} Consecutive Red Quarters",
                description=(
                    f"Nightly scan: {stock.company_name} has {stock.consecutive_red} consecutive red quarters. "
                    f"Consider reviewing the investment thesis."
                ),
                data_snapshot={"consecutive_red": stock.consecutive_red, "signal": stock.overall_signal},
            ))
            alerts_created += 1

        await db.commit()
    return {"status": "ok", "alerts_created": alerts_created}


# ─── Recalculate all risk-reward scores ──────────────────────────────────────
@shared_task(
    name="tracker.recalculate_all_scores",
    queue="tracker_normal",
)
def recalculate_all_scores_task() -> dict:
    return asyncio.run(_recalc_all())


async def _recalc_all() -> dict:
    async with get_async_session_context() as db:
        result = await db.execute(
            select(TrackedStock.isin).where(TrackedStock.tracking_status == "ACTIVE")
        )
        isins = [r.isin for r in result.fetchall()]
        for isin in isins:
            await recalculate_scores(db, isin)
    return {"status": "ok", "recalculated": len(isins)}


# ─── Seed tracker from Company Research worker ────────────────────────────────
@shared_task(
    name="tracker.seed_from_research",
    queue="tracker_normal",
)
def seed_from_research_task(isins: list[str] | None = None) -> dict:
    """
    Pull investment thesis, scenarios, targets from Company Research worker tables
    into master tracker tables for tracked stocks.
    """
    return asyncio.run(_seed_from_research(isins))


async def _seed_from_research(isins: list[str] | None) -> dict:
    async with get_async_session_context() as db:
        if isins is None:
            result = await db.execute(
                select(TrackedStock.isin).where(TrackedStock.tracking_status == "ACTIVE")
            )
            isins = [r.isin for r in result.fetchall()]

        seeded = 0
        for isin in isins:
            # Pull latest thesis from company research
            r = await db.execute(text("""
            SELECT it.*, c.expected_cagr_3y, c.target_price_12m, c.fair_value_mid,
                   c.rating, c.confidence_score
            FROM investment_theses it
            JOIN companies c ON c.isin = it.isin
            WHERE it.isin = :isin AND it.is_current = true
            LIMIT 1
            """), {"isin": isin})
            row = r.fetchone()
            if not row:
                continue

            # Update tracked stock with research data
            await db.execute(text("""
            UPDATE mt_stocks SET
                thesis_summary = :summary,
                expected_cagr_3y = :cagr,
                target_price_12m = :tp,
                fair_value = :fv,
                rating = :rating,
                conviction_score = :confidence,
                thesis_updated_at = NOW(),
                updated_at = NOW()
            WHERE isin = :isin
            """), {
                "isin": isin,
                "summary": (row.one_liner_thesis or "")[:500] if hasattr(row, 'one_liner_thesis') else None,
                "cagr": row.expected_cagr_3y,
                "tp": row.target_price_12m,
                "fv": row.fair_value_mid,
                "rating": row.rating,
                "confidence": row.confidence_score,
            })
            seeded += 1

        await db.commit()
    return {"status": "ok", "seeded": seeded}


# ─── Celery Beat schedule ─────────────────────────────────────────────────────
CELERYBEAT_SCHEDULE = {
    "tracker-daily-technicals": {
        "task": "tracker.update_technical_snapshots",
        "schedule": "30 18 * * 1-5",  # 6:30 PM after market close, Mon–Fri
    },
    "tracker-nightly-alert-scan": {
        "task": "tracker.scan_alerts",
        "schedule": "0 20 * * 1-5",   # 8 PM nightly
    },
    "tracker-nightly-recalc": {
        "task": "tracker.recalculate_all_scores",
        "schedule": "30 20 * * 1-5",  # 8:30 PM
    },
    "tracker-nightly-seed": {
        "task": "tracker.seed_from_research",
        "schedule": "0 21 * * *",     # 9 PM daily
    },
}
