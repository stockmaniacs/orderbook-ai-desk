"""
FastAPI router — Technical Analysis AI Worker.

Prefix: /api/v1/technical

Endpoints:
  GET  /dashboard                  — ranked universe table
  GET  /leaders                    — elite leaders only (quick filter)
  GET  /stock/{isin}               — full detail view
  GET  /stock/{isin}/snapshots     — OHLCV + indicator history
  GET  /stock/{isin}/patterns      — all detected patterns
  GET  /stock/{isin}/alerts        — stock alerts
  GET  /stock/{isin}/signals       — signal history + performance
  GET  /stock/{isin}/levels        — current breakout levels
  GET  /alerts                     — all unread alerts (cross-stock)
  PATCH /alerts/{alert_id}         — mark read/actioned
  GET  /breadth                    — latest market breadth
  GET  /breadth/history            — breadth time series
  GET  /sectors                    — sector RS rankings
  POST /admin/score/{isin}         — trigger re-score for one stock
  POST /admin/score-universe       — queue full universe re-score
  POST /admin/pattern-scan         — queue pattern scan
  POST /admin/rs-ratings           — queue RS rating computation
  POST /universe/add               — add stock to universe
  GET  /signals/performance        — model accuracy metrics
  GET  /signals/win-rate           — win rate by classification/pattern
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_session
from .models import (
    BreakoutLevel, DailySnapshot, MarketBreadth, PatternDetection,
    RelativeStrength, SignalHistory, TechnicalAlert, TechnicalProfile,
)
from .schemas import (
    AddUniverseStockIn, AlertMarkIn, BreakoutLevelOut, DailySnapshotOut,
    IngestSnapshotIn, JobResultOut, MarketBreadthOut, PatternOut,
    RelativeStrengthOut, ScanFilterIn, SignalHistoryOut, StockDetailOut,
    TechnicalAlertOut, TechnicalDashboardOut, TechnicalProfileOut,
)
from .service import (
    compute_market_breadth, compute_rs_ratings,
    get_dashboard, get_stock_detail, ingest_daily_snapshot,
    update_market_leader_ranks, update_signal_outcomes,
)
from .tasks import (
    compute_rs_ratings_task, market_breadth_task, pattern_scan_task,
    score_stock_task, score_universe_task, update_ranks_task,
    update_signal_outcomes_task,
)

router = APIRouter(prefix="/api/v1/technical", tags=["technical"])
log = logging.getLogger(__name__)


# ─── Dashboard ────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_model=TechnicalDashboardOut)
async def dashboard(
    classification: str | None = None,
    signal: str | None = None,
    sector: str | None = None,
    stage: int | None = None,
    min_rs_rating: int | None = Query(None, ge=1, le=99),
    min_tech_score: float | None = Query(None, ge=0, le=100),
    has_pattern: bool | None = None,
    sort_by: str = "conviction_score",
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
):
    filters = ScanFilterIn(
        classification=classification,
        signal=signal,
        sector=sector,
        stage=stage,
        min_rs_rating=min_rs_rating,
        min_tech_score=min_tech_score,
        has_pattern=has_pattern,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return await get_dashboard(db, filters)


@router.get("/leaders", response_model=TechnicalDashboardOut)
async def get_leaders(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_async_session),
):
    """Quick endpoint: top stocks by conviction score in ELITE_LEADER + STRONG_STRUCTURE."""
    filters = ScanFilterIn(sort_by="conviction_score", limit=limit)
    return await get_dashboard(db, filters)


# ─── Stock Detail ─────────────────────────────────────────────────────────────
@router.get("/stock/{isin}", response_model=StockDetailOut)
async def get_stock(isin: str, db: AsyncSession = Depends(get_async_session)):
    detail = await get_stock_detail(db, isin)
    if not detail:
        raise HTTPException(404, f"Stock {isin} not found in universe")
    return detail


@router.get("/stock/{isin}/profile", response_model=TechnicalProfileOut)
async def get_profile(isin: str, db: AsyncSession = Depends(get_async_session)):
    q = await db.execute(select(TechnicalProfile).where(TechnicalProfile.isin == isin))
    profile = q.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Not found")
    return TechnicalProfileOut.model_validate(profile)


@router.get("/stock/{isin}/snapshots", response_model=list[DailySnapshotOut])
async def get_snapshots(
    isin: str,
    days: int = Query(60, le=500),
    db: AsyncSession = Depends(get_async_session),
):
    q = await db.execute(
        select(DailySnapshot).where(DailySnapshot.isin == isin)
        .order_by(DailySnapshot.snap_date.desc()).limit(days)
    )
    snaps = list(reversed(q.scalars().all()))
    return [DailySnapshotOut.model_validate(s) for s in snaps]


@router.get("/stock/{isin}/patterns", response_model=list[PatternOut])
async def get_patterns(
    isin: str,
    status: str | None = None,
    db: AsyncSession = Depends(get_async_session),
):
    q = select(PatternDetection).where(PatternDetection.isin == isin)
    if status:
        q = q.where(PatternDetection.status == status)
    q = q.order_by(PatternDetection.detected_date.desc()).limit(20)
    result = await db.execute(q)
    return [PatternOut.model_validate(p) for p in result.scalars().all()]


@router.get("/stock/{isin}/levels", response_model=BreakoutLevelOut | None)
async def get_levels(isin: str, db: AsyncSession = Depends(get_async_session)):
    q = await db.execute(
        select(BreakoutLevel).where(BreakoutLevel.isin == isin, BreakoutLevel.is_current == True)
        .order_by(BreakoutLevel.calc_date.desc()).limit(1)
    )
    level = q.scalar_one_or_none()
    return BreakoutLevelOut.model_validate(level) if level else None


@router.get("/stock/{isin}/alerts", response_model=list[TechnicalAlertOut])
async def get_stock_alerts(
    isin: str,
    unread_only: bool = False,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_async_session),
):
    q = select(TechnicalAlert).where(TechnicalAlert.isin == isin)
    if unread_only:
        q = q.where(TechnicalAlert.is_read == False)
    q = q.order_by(TechnicalAlert.triggered_at.desc()).limit(limit)
    result = await db.execute(q)
    return [TechnicalAlertOut.model_validate(a) for a in result.scalars().all()]


@router.get("/stock/{isin}/signals", response_model=list[SignalHistoryOut])
async def get_signal_history(
    isin: str,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_async_session),
):
    q = await db.execute(
        select(SignalHistory).where(SignalHistory.isin == isin)
        .order_by(SignalHistory.signal_date.desc()).limit(limit)
    )
    return [SignalHistoryOut.model_validate(s) for s in q.scalars().all()]


@router.get("/stock/{isin}/rs", response_model=RelativeStrengthOut | None)
async def get_rs(isin: str, db: AsyncSession = Depends(get_async_session)):
    q = await db.execute(
        select(RelativeStrength).where(RelativeStrength.isin == isin)
        .order_by(RelativeStrength.rs_date.desc()).limit(1)
    )
    rs = q.scalar_one_or_none()
    return RelativeStrengthOut.model_validate(rs) if rs else None


# ─── Alerts (cross-stock) ────────────────────────────────────────────────────
@router.get("/alerts", response_model=list[TechnicalAlertOut])
async def get_all_alerts(
    unread_only: bool = True,
    severity: str | None = None,
    alert_type: str | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_async_session),
):
    q = select(TechnicalAlert)
    if unread_only:
        q = q.where(TechnicalAlert.is_read == False)
    if severity:
        q = q.where(TechnicalAlert.severity == severity)
    if alert_type:
        q = q.where(TechnicalAlert.alert_type == alert_type)
    q = q.order_by(TechnicalAlert.triggered_at.desc()).limit(limit)
    result = await db.execute(q)
    return [TechnicalAlertOut.model_validate(a) for a in result.scalars().all()]


@router.patch("/alerts/{alert_id}", response_model=TechnicalAlertOut)
async def mark_alert(
    alert_id: UUID,
    body: AlertMarkIn,
    db: AsyncSession = Depends(get_async_session),
):
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    await db.execute(
        update(TechnicalAlert).where(TechnicalAlert.id == alert_id).values(**updates)
    )
    await db.commit()
    q = await db.execute(select(TechnicalAlert).where(TechnicalAlert.id == alert_id))
    return TechnicalAlertOut.model_validate(q.scalar_one())


# ─── Market Breadth ───────────────────────────────────────────────────────────
@router.get("/breadth", response_model=MarketBreadthOut | None)
async def get_breadth(db: AsyncSession = Depends(get_async_session)):
    q = await db.execute(
        select(MarketBreadth).order_by(MarketBreadth.breadth_date.desc()).limit(1)
    )
    breadth = q.scalar_one_or_none()
    return MarketBreadthOut.model_validate(breadth) if breadth else None


@router.get("/breadth/history", response_model=list[MarketBreadthOut])
async def get_breadth_history(
    days: int = Query(30, le=252),
    db: AsyncSession = Depends(get_async_session),
):
    q = await db.execute(
        select(MarketBreadth).order_by(MarketBreadth.breadth_date.desc()).limit(days)
    )
    return [MarketBreadthOut.model_validate(b) for b in reversed(q.scalars().all())]


# ─── Sectors ──────────────────────────────────────────────────────────────────
@router.get("/sectors")
async def get_sector_rankings(db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(text("""
        SELECT sector,
               AVG(technical_score)  as avg_tech_score,
               AVG(conviction_score) as avg_conviction,
               AVG(rs_rating)        as avg_rs_rating,
               COUNT(*)              as stock_count,
               SUM(CASE WHEN classification = 'ELITE_LEADER'    THEN 1 ELSE 0 END) as elite_count,
               SUM(CASE WHEN classification = 'STRONG_STRUCTURE' THEN 1 ELSE 0 END) as strong_count,
               SUM(CASE WHEN signal IN ('STRONG_BUY','BUY')      THEN 1 ELSE 0 END) as buy_signals,
               ROW_NUMBER() OVER (ORDER BY AVG(technical_score) DESC NULLS LAST) as sector_rank
        FROM ta_profiles
        WHERE sector IS NOT NULL AND technical_score IS NOT NULL
        GROUP BY sector
        ORDER BY avg_tech_score DESC
    """))
    rows = result.fetchall()
    return [
        {
            "sector": r.sector,
            "sector_rank": r.sector_rank,
            "avg_tech_score": round(r.avg_tech_score or 0, 1),
            "avg_conviction": round(r.avg_conviction or 0, 1),
            "avg_rs_rating": round(r.avg_rs_rating or 0, 0),
            "stock_count": r.stock_count,
            "elite_count": r.elite_count,
            "strong_count": r.strong_count,
            "buy_signals": r.buy_signals,
        }
        for r in rows
    ]


# ─── Signal Performance ───────────────────────────────────────────────────────
@router.get("/signals/performance")
async def signal_performance(db: AsyncSession = Depends(get_async_session)):
    """Aggregated win rates, avg returns by signal/classification for model monitoring."""
    result = await db.execute(text("""
        SELECT
            signal,
            classification,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'WIN'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
            AVG(return_30d) as avg_return_30d,
            AVG(return_60d) as avg_return_60d,
            AVG(return_90d) as avg_return_90d,
            AVG(max_gain_pct) as avg_max_gain,
            AVG(max_loss_pct) as avg_max_loss,
            SUM(CASE WHEN hit_target THEN 1 ELSE 0 END) as target_hits,
            SUM(CASE WHEN hit_stop   THEN 1 ELSE 0 END) as stop_hits
        FROM ta_signal_history
        WHERE outcome IS NOT NULL
        GROUP BY signal, classification
        ORDER BY signal, classification
    """))
    rows = result.fetchall()

    return [
        {
            "signal": r.signal,
            "classification": r.classification,
            "total": r.total,
            "win_rate": round(r.wins / r.total * 100, 1) if r.total > 0 else None,
            "avg_return_30d": round(r.avg_return_30d or 0, 1),
            "avg_return_60d": round(r.avg_return_60d or 0, 1),
            "avg_return_90d": round(r.avg_return_90d or 0, 1),
            "avg_max_gain": round(r.avg_max_gain or 0, 1),
            "avg_max_loss": round(r.avg_max_loss or 0, 1),
            "target_hit_rate": round(r.target_hits / r.total * 100, 1) if r.total > 0 else None,
            "stop_hit_rate": round(r.stop_hits / r.total * 100, 1) if r.total > 0 else None,
        }
        for r in rows
    ]


@router.get("/signals/win-rate")
async def win_rate_by_pattern(db: AsyncSession = Depends(get_async_session)):
    """Win rate sliced by pattern type and minimum RS rating."""
    result = await db.execute(text("""
        SELECT
            pattern_type,
            COUNT(*) as total,
            AVG(CASE WHEN outcome = 'WIN' THEN 100.0 ELSE 0 END) as win_rate_pct,
            AVG(return_30d) as avg_30d,
            AVG(return_90d) as avg_90d,
            AVG(risk_reward_ratio) as avg_rr
        FROM ta_signal_history
        WHERE outcome IS NOT NULL AND pattern_type IS NOT NULL
        GROUP BY pattern_type
        ORDER BY win_rate_pct DESC
    """))
    rows = result.fetchall()
    return [
        {
            "pattern_type": r.pattern_type,
            "total": r.total,
            "win_rate_pct": round(r.win_rate_pct or 0, 1),
            "avg_30d_return": round(r.avg_30d or 0, 1),
            "avg_90d_return": round(r.avg_90d or 0, 1),
            "avg_rr": round(r.avg_rr or 0, 1),
        }
        for r in rows
    ]


# ─── Universe Management ──────────────────────────────────────────────────────
@router.post("/universe/add", response_model=TechnicalProfileOut)
async def add_to_universe(
    body: AddUniverseStockIn,
    db: AsyncSession = Depends(get_async_session),
):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(TechnicalProfile).values(
        isin=body.isin,
        symbol_nse=body.symbol_nse,
        symbol_bse=body.symbol_bse,
        company_name=body.company_name,
        sector=body.sector,
        industry=body.industry,
        market_cap_cr=body.market_cap_cr,
        market_cap_cat=body.market_cap_cat,
    ).on_conflict_do_update(
        index_elements=["isin"],
        set_={
            "symbol_nse": body.symbol_nse,
            "company_name": body.company_name,
            "sector": body.sector,
            "market_cap_cr": body.market_cap_cr,
        }
    ).returning(TechnicalProfile)
    result = await db.execute(stmt)
    await db.commit()
    q = await db.execute(select(TechnicalProfile).where(TechnicalProfile.isin == body.isin))
    return TechnicalProfileOut.model_validate(q.scalar_one())


@router.post("/universe/ingest", response_model=JobResultOut)
async def ingest_snapshot(
    body: IngestSnapshotIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session),
):
    """Manually push OHLCV data for a stock."""
    ohlcv = {"open": body.open, "high": body.high, "low": body.low,
              "close": body.close, "volume": body.volume, "delivery_pct": body.delivery_pct}
    task = score_stock_task.apply_async(args=[body.isin, str(body.snap_date)], queue="technical_high")
    await ingest_daily_snapshot(db, body.isin, body.snap_date, ohlcv)
    return JobResultOut(status="queued", task_id=task.id, message=f"Snapshot ingested for {body.isin}")


# ─── Admin ────────────────────────────────────────────────────────────────────
@router.post("/admin/score/{isin}", response_model=JobResultOut)
async def admin_score_stock(isin: str, snap_date: str | None = None):
    task = score_stock_task.apply_async(args=[isin, snap_date], queue="technical_high")
    return JobResultOut(status="queued", task_id=task.id)


@router.post("/admin/score-universe", response_model=JobResultOut)
async def admin_score_universe(snap_date: str | None = None):
    task = score_universe_task.apply_async(kwargs={"snap_date": snap_date}, queue="technical_high")
    return JobResultOut(status="queued", task_id=task.id)


@router.post("/admin/pattern-scan", response_model=JobResultOut)
async def admin_pattern_scan():
    task = pattern_scan_task.apply_async(queue="technical_normal")
    return JobResultOut(status="queued", task_id=task.id)


@router.post("/admin/rs-ratings", response_model=JobResultOut)
async def admin_rs_ratings(rs_date: str | None = None):
    task = compute_rs_ratings_task.apply_async(kwargs={"rs_date": rs_date}, queue="technical_normal")
    return JobResultOut(status="queued", task_id=task.id)


@router.post("/admin/breadth", response_model=JobResultOut)
async def admin_breadth(breadth_date: str | None = None):
    task = market_breadth_task.apply_async(kwargs={"breadth_date": breadth_date}, queue="technical_normal")
    return JobResultOut(status="queued", task_id=task.id)


@router.post("/admin/update-outcomes", response_model=JobResultOut)
async def admin_update_outcomes():
    task = update_signal_outcomes_task.apply_async(queue="technical_normal")
    return JobResultOut(status="queued", task_id=task.id)
