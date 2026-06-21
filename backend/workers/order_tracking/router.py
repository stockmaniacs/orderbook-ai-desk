"""
Order Tracking Worker — FastAPI Router
All REST endpoints for the order tracking feature.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    OrderAISummary,
    OrderAnnouncement,
    OrderBookMetrics,
    OrderBookSnapshot,
)
from .schemas import (
    ChartsData,
    ManualOrderCreate,
    OrderAnnouncementList,
    OrderAnnouncementOut,
    OrderAISummaryOut,
    OrderBookHistory,
    OrderBookMetricsOut,
    OrderSearchParams,
    OrderTrackingDashboard,
    SnapshotPoint,
)
from .service import (
    build_charts_data,
    compute_metrics,
    get_dashboard,
    get_order_announcements,
    get_recent_orders_all,
    upsert_quarterly_snapshot,
    _fiscal_quarter,
)

router = APIRouter(tags=["Order Tracking"])

# Dependency placeholder — replace with your actual DB session factory
async def get_db() -> AsyncSession:  # type: ignore
    from database import async_session_factory
    async with async_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# 1. Dashboard — full scorecard for a stock
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/dashboard",
    response_model=OrderTrackingDashboard,
    summary="Full order tracking dashboard for a stock",
)
async def get_order_dashboard(
    isin: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns metrics, history, recent orders, scenarios and AI summary
    for the given ISIN. This is the primary endpoint for the stock detail page.
    """
    dash = await get_dashboard(db, isin.upper())
    if not dash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No order data found for ISIN {isin}",
        )
    return dash


# ---------------------------------------------------------------------------
# 2. Metrics — computed scores and ratios
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/metrics",
    response_model=OrderBookMetricsOut,
    summary="Computed order book metrics and scenarios",
)
async def get_metrics(
    isin: str,
    refresh: bool = Query(False, description="Recompute metrics before returning"),
    db: AsyncSession = Depends(get_db),
):
    if refresh:
        m = await compute_metrics(db, isin.upper())
        await db.commit()
        return OrderBookMetricsOut.model_validate(m)

    result = await db.execute(
        select(OrderBookMetrics).where(OrderBookMetrics.isin == isin.upper())
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, detail="No metrics found")
    return OrderBookMetricsOut.model_validate(m)


# ---------------------------------------------------------------------------
# 3. Order announcements list
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/orders",
    response_model=OrderAnnouncementList,
    summary="List all order announcements for a stock",
)
async def list_orders(
    isin: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    order_type: Optional[str] = Query(None, description="DOMESTIC | EXPORT | MIXED"),
    min_amount_cr: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    q = (
        select(OrderAnnouncement)
        .where(
            OrderAnnouncement.isin == isin.upper(),
            OrderAnnouncement.processing_status == "DONE",
        )
        .order_by(desc(OrderAnnouncement.announced_date))
    )
    if order_type:
        q = q.where(OrderAnnouncement.order_type == order_type.upper())
    if min_amount_cr:
        q = q.where(OrderAnnouncement.order_amount_cr >= min_amount_cr)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(q.offset(offset).limit(limit))
    items = result.scalars().all()

    return OrderAnnouncementList(
        items=[OrderAnnouncementOut.model_validate(o) for o in items],
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 4. Chart data
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/charts",
    response_model=ChartsData,
    summary="Pre-aggregated chart data (quarterly, YoY, rolling)",
)
async def get_charts(
    isin: str,
    db: AsyncSession = Depends(get_db),
):
    return await build_charts_data(db, isin.upper())


# ---------------------------------------------------------------------------
# 5. Quarterly history
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/history",
    response_model=OrderBookHistory,
    summary="Quarterly order book snapshots",
)
async def get_history(
    isin: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderBookSnapshot)
        .where(OrderBookSnapshot.isin == isin.upper())
        .order_by(OrderBookSnapshot.fiscal_year, OrderBookSnapshot.quarter_num)
    )
    snaps = result.scalars().all()
    company_name = snaps[0].company_name if snaps else isin

    return OrderBookHistory(
        isin=isin.upper(),
        company_name=company_name,
        snapshots=[SnapshotPoint.model_validate(s) for s in snaps],
    )


# ---------------------------------------------------------------------------
# 6. AI Summary
# ---------------------------------------------------------------------------
@router.get(
    "/{isin}/ai-summary",
    response_model=OrderAISummaryOut,
    summary="AI-generated order flow analysis",
)
async def get_ai_summary(
    isin: str,
    regenerate: bool = Query(False, description="Force regenerate AI summary"),
    db: AsyncSession = Depends(get_db),
    background: BackgroundTasks = BackgroundTasks(),
):
    if regenerate:
        from .tasks import generate_ai_analysis
        generate_ai_analysis.delay(isin.upper())
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="AI analysis queued. Refresh in ~30 seconds.",
        )

    result = await db.execute(
        select(OrderAISummary)
        .where(OrderAISummary.isin == isin.upper())
        .order_by(desc(OrderAISummary.generated_at))
        .limit(1)
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(404, detail="No AI summary available yet")
    return OrderAISummaryOut.model_validate(summary)


# ---------------------------------------------------------------------------
# 7. Cross-universe: recent large orders (all companies)
# ---------------------------------------------------------------------------
@router.get(
    "/universe/recent",
    response_model=OrderAnnouncementList,
    summary="Latest large order wins across all tracked companies",
)
async def get_universe_recent_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    min_amount_cr: float = Query(100, description="Minimum order size in ₹ Crore"),
    sector: Optional[str] = Query(None),
    order_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    q = (
        select(OrderAnnouncement)
        .where(
            OrderAnnouncement.processing_status == "DONE",
            OrderAnnouncement.order_amount_cr >= min_amount_cr,
        )
        .order_by(desc(OrderAnnouncement.announced_date))
    )
    if sector:
        q = q.where(OrderAnnouncement.sector_category == sector.upper())
    if order_type:
        q = q.where(OrderAnnouncement.order_type == order_type.upper())
    if from_date:
        q = q.where(OrderAnnouncement.announced_date >= from_date)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(q.offset(offset).limit(limit))
    items = result.scalars().all()

    return OrderAnnouncementList(
        items=[OrderAnnouncementOut.model_validate(o) for o in items],
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 8. Top companies by order acceleration score
# ---------------------------------------------------------------------------
@router.get(
    "/universe/leaderboard",
    summary="Top companies ranked by order acceleration score",
)
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    sector: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(OrderBookMetrics)
        .where(OrderBookMetrics.order_acceleration_score.isnot(None))
        .order_by(desc(OrderBookMetrics.order_acceleration_score))
    )
    result = await db.execute(q.limit(limit))
    items = result.scalars().all()
    return [OrderBookMetricsOut.model_validate(m) for m in items]


# ---------------------------------------------------------------------------
# 9. Manual order entry
# ---------------------------------------------------------------------------
@router.post(
    "/manual",
    response_model=OrderAnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add an order not on exchanges",
)
async def create_manual_order(
    payload: ManualOrderCreate,
    db: AsyncSession = Depends(get_db),
):
    raw = f"MANUAL|{payload.isin}|{payload.announced_date}|{payload.order_amount_cr}"
    content_hash = hashlib.sha256(raw.encode()).hexdigest()

    quarter_label, fy, _ = _fiscal_quarter(payload.announced_date)

    record = OrderAnnouncement(
        source="MANUAL",
        source_id=str(uuid.uuid4()),
        isin=payload.isin.upper(),
        company_name=payload.company_name,
        customer_name=payload.customer_name,
        order_amount_cr=payload.order_amount_cr,
        order_amount_raw=f"₹{payload.order_amount_cr:.0f} Cr",
        order_currency="INR",
        order_type=payload.order_type,
        project_description=payload.project_description,
        announced_date=payload.announced_date,
        execution_start=payload.execution_start,
        execution_end=payload.execution_end,
        sector_category=payload.sector_category,
        project_type=payload.project_type,
        fiscal_year=fy,
        quarter=quarter_label,
        processing_status="DONE",
        extraction_confidence=1.0,
        extraction_model="manual",
        content_hash=content_hash,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Trigger metric recompute
    from .tasks import recompute_metrics
    recompute_metrics.delay(payload.isin.upper())

    return OrderAnnouncementOut.model_validate(record)


# ---------------------------------------------------------------------------
# 10. Trigger scrape (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/admin/trigger-scrape",
    summary="Manually trigger BSE + NSE scrape",
)
async def trigger_scrape(days_back: int = Query(1, ge=1, le=30)):
    from .tasks import scrape_bse_orders, scrape_nse_orders
    scrape_bse_orders.delay(days_back=days_back)
    scrape_nse_orders.delay(days_back=days_back)
    return {"status": "queued", "days_back": days_back}
