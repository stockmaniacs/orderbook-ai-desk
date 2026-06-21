"""
Celery tasks — Technical Analysis AI Worker.

Schedule (IST):
  3:45 PM Mon–Fri  — ingest_daily_snapshots_task  (after NSE close)
  4:00 PM          — run_scoring_universe_task      (score all stocks)
  4:30 PM          — compute_rs_ratings_task
  4:45 PM          — update_market_leader_ranks_task
  5:00 PM          — compute_market_breadth_task
  5:30 PM          — update_signal_outcomes_task    (fill forward returns)
  Sat 6 AM         — weekly_pattern_scan_task
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import select, text

from database import get_async_session_context
from .models import TechnicalProfile, DailySnapshot
from .service import (
    compute_market_breadth,
    compute_rs_ratings,
    get_stock_detail,
    ingest_daily_snapshot,
    persist_patterns,
    run_full_score,
    update_market_leader_ranks,
    update_signal_outcomes,
)
from .scoring import PriceData

log = logging.getLogger(__name__)


# ─── Helper: build PriceData from latest snapshot ────────────────────────────
async def _build_price_data(db, isin: str, snap_date: date) -> PriceData | None:
    """Construct PriceData from stored snapshot + profile data."""
    snap_q = await db.execute(
        select(DailySnapshot)
        .where(DailySnapshot.isin == isin, DailySnapshot.snap_date == snap_date)
    )
    snap = snap_q.scalar_one_or_none()
    if not snap or not snap.close:
        return None

    profile_q = await db.execute(
        select(TechnicalProfile).where(TechnicalProfile.isin == isin)
    )
    profile = profile_q.scalar_one_or_none()

    # Get prev snapshot for MACD hist expanding check
    prev_q = await db.execute(text("""
        SELECT macd_hist FROM ta_daily_snapshots
        WHERE isin = :isin AND snap_date < :d
        ORDER BY snap_date DESC LIMIT 1
    """), {"isin": isin, "d": snap_date})
    prev = prev_q.fetchone()

    # Get RS data
    rs_q = await db.execute(text("""
        SELECT rs_rating, rs_vs_nifty500_3m, rs_vs_nifty500_6m, rs_trend, rs_breakout, rs_new_high
        FROM ta_relative_strength
        WHERE isin = :isin ORDER BY rs_date DESC LIMIT 1
    """), {"isin": isin})
    rs = rs_q.fetchone()

    # Get active pattern
    pat_q = await db.execute(text("""
        SELECT pattern_type, quality_score, pivot_price,
               CASE WHEN status = 'BREAKOUT' THEN 100
                    WHEN status = 'COMPLETE' THEN 90
                    ELSE 70 END as maturity
        FROM ta_patterns
        WHERE isin = :isin AND status IN ('FORMING','COMPLETE','BREAKOUT')
        ORDER BY quality_score DESC LIMIT 1
    """), {"isin": isin})
    pat = pat_q.fetchone()

    return PriceData(
        isin=isin,
        close=snap.close,
        high=snap.high or snap.close,
        low=snap.low or snap.close,
        volume=snap.volume or 0,
        sma_10=snap.sma_10,
        sma_20=snap.sma_20,
        sma_50=snap.sma_50,
        sma_150=snap.sma_150,
        sma_200=snap.sma_200,
        ema_20=snap.ema_20,
        high_52w=snap.high_52w,
        low_52w=snap.low_52w,
        rsi_14=snap.rsi_14,
        rsi_weekly=snap.rsi_weekly,
        adx_14=snap.adx_14,
        di_plus=snap.di_plus,
        di_minus=snap.di_minus,
        macd=snap.macd,
        macd_signal=snap.macd_signal,
        macd_hist=snap.macd_hist,
        macd_hist_prev=prev.macd_hist if prev else None,
        roc_10=snap.roc_10,
        roc_20=snap.roc_20,
        roc_60=snap.roc_60,
        vol_sma_20=snap.vol_sma_20,
        vol_sma_50=snap.vol_sma_50,
        up_vol_ratio=snap.up_vol_ratio,
        delivery_pct=snap.delivery_pct,
        accum_dist=snap.accum_dist,
        obv=snap.obv,
        is_pocket_pivot=snap.is_pocket_pivot or False,
        distribution_days_20=snap.distribution_days_20 or 0,
        tight_action_5d=snap.tight_action_5d or False,
        atr_14=snap.atr_14,
        volatility_20d=snap.volatility_20d,
        rs_rating=rs.rs_rating if rs else None,
        rs_vs_nifty500_3m=rs.rs_vs_nifty500_3m if rs else None,
        rs_vs_nifty500_6m=rs.rs_vs_nifty500_6m if rs else None,
        rs_trend=rs.rs_trend if rs else None,
        rs_breakout=bool(rs.rs_breakout) if rs else False,
        rs_new_high=bool(rs.rs_new_high) if rs else False,
        active_pattern=pat.pattern_type if pat else None,
        pattern_maturity=float(pat.maturity) if pat else None,
        pattern_quality=float(pat.quality_score) if pat else None,
        prev_technical_score=profile.technical_score if profile else None,
        prev_signal=profile.signal if profile else None,
    )


# ─── 1. Ingest daily snapshots ────────────────────────────────────────────────
@shared_task(
    name="technical.ingest_daily_snapshots",
    queue="technical_high",
    time_limit=7200,
)
def ingest_daily_snapshots_task(isins: list[str] | None = None, snap_date: str | None = None) -> dict:
    """
    Ingest OHLCV data for all or specified stocks.
    In production: integrate with NSE/BSE data vendor.
    """
    return asyncio.run(_ingest_all(isins, snap_date))


async def _ingest_all(isins: list[str] | None, snap_date_str: str | None) -> dict:
    sd = date.fromisoformat(snap_date_str) if snap_date_str else date.today()
    async with get_async_session_context() as db:
        if isins is None:
            result = await db.execute(select(TechnicalProfile.isin))
            isins = [r.isin for r in result.fetchall()]

        ingested = 0
        for isin in isins:
            try:
                # Production: fetch from NSE API / data vendor here
                # Placeholder: read last known snapshot
                last_q = await db.execute(text("""
                    SELECT open, high, low, close, volume, delivery_pct
                    FROM ta_daily_snapshots WHERE isin = :isin ORDER BY snap_date DESC LIMIT 1
                """), {"isin": isin})
                row = last_q.fetchone()
                if not row:
                    continue
                ohlcv = {"open": row.open, "high": row.high, "low": row.low,
                         "close": row.close, "volume": row.volume,
                         "delivery_pct": row.delivery_pct}
                await ingest_daily_snapshot(db, isin, sd, ohlcv)
                ingested += 1
            except Exception as e:
                log.warning("Snapshot ingest failed for %s: %s", isin, e)

    return {"status": "ok", "date": str(sd), "ingested": ingested}


# ─── 2. Score universe ────────────────────────────────────────────────────────
@shared_task(
    name="technical.score_universe",
    queue="technical_high",
    time_limit=7200,
)
def score_universe_task(snap_date: str | None = None, isins: list[str] | None = None) -> dict:
    return asyncio.run(_score_all(snap_date, isins))


async def _score_all(snap_date_str: str | None, isins: list[str] | None) -> dict:
    sd = date.fromisoformat(snap_date_str) if snap_date_str else date.today()
    scored, failed = 0, 0
    async with get_async_session_context() as db:
        if isins is None:
            result = await db.execute(select(TechnicalProfile.isin))
            isins = [r.isin for r in result.fetchall()]

        for isin in isins:
            try:
                price_data = await _build_price_data(db, isin, sd)
                if price_data:
                    await run_full_score(db, isin, price_data, sd)
                    scored += 1
            except Exception as e:
                log.warning("Scoring failed for %s: %s", isin, e)
                failed += 1

    return {"status": "ok", "date": str(sd), "scored": scored, "failed": failed}


# ─── 3. Score single stock ────────────────────────────────────────────────────
@shared_task(
    name="technical.score_stock",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="technical_high",
)
def score_stock_task(self, isin: str, snap_date: str | None = None) -> dict:
    try:
        return asyncio.run(_score_one(isin, snap_date))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _score_one(isin: str, snap_date_str: str | None) -> dict:
    sd = date.fromisoformat(snap_date_str) if snap_date_str else date.today()
    async with get_async_session_context() as db:
        price_data = await _build_price_data(db, isin, sd)
        if not price_data:
            return {"status": "no_data", "isin": isin}
        result = await run_full_score(db, isin, price_data, sd)
        return {
            "status": "ok",
            "isin": isin,
            "classification": result.classification,
            "signal": result.signal,
            "technical_score": result.technical_score,
            "conviction_score": result.conviction_score,
        }


# ─── 4. Pattern scan ─────────────────────────────────────────────────────────
@shared_task(
    name="technical.pattern_scan",
    queue="technical_normal",
    time_limit=3600,
)
def pattern_scan_task(isins: list[str] | None = None) -> dict:
    return asyncio.run(_scan_patterns(isins))


async def _scan_patterns(isins: list[str] | None) -> dict:
    today = date.today()
    found_total = 0
    async with get_async_session_context() as db:
        if isins is None:
            # Only scan stocks with sufficient data
            result = await db.execute(text("""
                SELECT DISTINCT isin FROM ta_daily_snapshots
                WHERE snap_date >= :cutoff
            """), {"cutoff": today - timedelta(days=30)})
            isins = [r.isin for r in result.fetchall()]

        for isin in isins:
            try:
                bars_q = await db.execute(text("""
                    SELECT snap_date, open, high, low, close, volume
                    FROM ta_daily_snapshots WHERE isin = :isin
                    ORDER BY snap_date DESC LIMIT 65
                """), {"isin": isin})
                raw_bars = [
                    {"date": r.snap_date, "open": r.open or r.close, "high": r.high or r.close,
                     "low": r.low or r.close, "close": r.close, "volume": r.volume or 0}
                    for r in reversed(bars_q.fetchall())
                ]
                if len(raw_bars) < 10:
                    continue
                patterns = await persist_patterns(db, isin, raw_bars, today)
                if patterns:
                    found_total += len(patterns)
                    # Update active_pattern on profile
                    best = patterns[0]
                    await db.execute(text("""
                        UPDATE ta_profiles SET active_pattern = :pat WHERE isin = :isin
                    """), {"pat": best["pattern_type"], "isin": isin})
            except Exception as e:
                log.warning("Pattern scan failed for %s: %s", isin, e)

        await db.commit()
    return {"status": "ok", "patterns_found": found_total}


# ─── 5. RS Ratings ───────────────────────────────────────────────────────────
@shared_task(
    name="technical.compute_rs_ratings",
    queue="technical_normal",
)
def compute_rs_ratings_task(rs_date: str | None = None) -> dict:
    d = date.fromisoformat(rs_date) if rs_date else date.today()
    async def run():
        async with get_async_session_context() as db:
            n = await compute_rs_ratings(db, d)
            return {"status": "ok", "date": str(d), "stocks_rated": n}
    return asyncio.run(run())


# ─── 6. Market leader ranks ───────────────────────────────────────────────────
@shared_task(
    name="technical.update_ranks",
    queue="technical_normal",
)
def update_ranks_task() -> dict:
    async def run():
        async with get_async_session_context() as db:
            n = await update_market_leader_ranks(db)
            return {"status": "ok", "stocks_ranked": n}
    return asyncio.run(run())


# ─── 7. Market breadth ───────────────────────────────────────────────────────
@shared_task(
    name="technical.market_breadth",
    queue="technical_normal",
)
def market_breadth_task(breadth_date: str | None = None) -> dict:
    d = date.fromisoformat(breadth_date) if breadth_date else date.today()
    async def run():
        async with get_async_session_context() as db:
            return await compute_market_breadth(db, d)
    return asyncio.run(run())


# ─── 8. Signal outcomes ───────────────────────────────────────────────────────
@shared_task(
    name="technical.update_signal_outcomes",
    queue="technical_normal",
)
def update_signal_outcomes_task() -> dict:
    async def run():
        async with get_async_session_context() as db:
            n = await update_signal_outcomes(db)
            return {"status": "ok", "signals_updated": n}
    return asyncio.run(run())


# ─── 9. Scan for new elite leaders ───────────────────────────────────────────
@shared_task(
    name="technical.scan_elite",
    queue="technical_high",
)
def scan_elite_task() -> dict:
    """
    Find stocks that became ELITE_LEADER or STRONG_STRUCTURE today
    and generate a HIGH priority alert.
    """
    async def run():
        today = date.today()
        async with get_async_session_context() as db:
            result = await db.execute(text("""
                SELECT isin, company_name, classification, signal,
                       technical_score, conviction_score, rs_rating
                FROM ta_profiles
                WHERE classification IN ('ELITE_LEADER','STRONG_STRUCTURE')
                  AND scores_updated_at::date = :today
            """), {"today": today})
            leaders = result.fetchall()

            from .models import TechnicalAlert
            for r in leaders:
                existing = await db.execute(text("""
                    SELECT 1 FROM ta_alerts
                    WHERE isin = :isin AND alert_type = 'ELITE_LEADER_NEW'
                      AND alert_date >= :since
                """), {"isin": r.isin, "since": today - timedelta(days=7)})
                if existing.fetchone():
                    continue
                db.add(TechnicalAlert(
                    isin=r.isin,
                    company_name=r.company_name,
                    alert_date=today,
                    alert_type="ELITE_LEADER_NEW" if r.classification == "ELITE_LEADER" else "STRONG_STRUCTURE_NEW",
                    severity="HIGH",
                    title=f"🏆 {r.company_name} — {r.classification.replace('_',' ')}",
                    description=f"Upgraded to {r.classification.replace('_',' ')}. Tech score: {r.technical_score:.0f}/100, RS Rating: {r.rs_rating}, Conviction: {r.conviction_score:.0f}/100.",
                    data_snapshot={"classification": r.classification, "signal": r.signal,
                                   "tech_score": r.technical_score, "rs_rating": r.rs_rating},
                ))
            await db.commit()
            return {"status": "ok", "leaders_found": len(leaders)}
    return asyncio.run(run())


# ─── Celery Beat Schedule ─────────────────────────────────────────────────────
CELERYBEAT_SCHEDULE = {
    # After market close pipeline
    "ta-ingest-snapshots": {
        "task": "technical.ingest_daily_snapshots",
        "schedule": "45 15 * * 1-5",   # 3:45 PM Mon–Fri
    },
    "ta-score-universe": {
        "task": "technical.score_universe",
        "schedule": "0 16 * * 1-5",    # 4:00 PM
    },
    "ta-rs-ratings": {
        "task": "technical.compute_rs_ratings",
        "schedule": "30 16 * * 1-5",   # 4:30 PM
    },
    "ta-ranks": {
        "task": "technical.update_ranks",
        "schedule": "45 16 * * 1-5",   # 4:45 PM
    },
    "ta-breadth": {
        "task": "technical.market_breadth",
        "schedule": "0 17 * * 1-5",    # 5:00 PM
    },
    "ta-outcomes": {
        "task": "technical.update_signal_outcomes",
        "schedule": "30 17 * * 1-5",   # 5:30 PM
    },
    "ta-elite-scan": {
        "task": "technical.scan_elite",
        "schedule": "15 17 * * 1-5",   # 5:15 PM
    },
    "ta-pattern-scan": {
        "task": "technical.pattern_scan",
        "schedule": "0 6 * * 6",       # Saturday 6 AM — weekly pattern review
    },
}
