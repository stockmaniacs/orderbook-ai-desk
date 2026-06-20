"""
Order Tracking Worker — Service Layer
Business logic: metric computation, scenario building, chart data assembly.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    OrderAISummary,
    OrderAnnouncement,
    OrderBookMetrics,
    OrderBookSnapshot,
)
from .schemas import (
    ChartsData,
    OrderBookHistory,
    OrderTrackingDashboard,
    QuarterlyChartPoint,
    RollingChartPoint,
    SnapshotPoint,
    YoYChartPoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
LARGE_ORDER_THRESHOLD_CR = 250  # ₹250 Cr+ = large order

def _fiscal_quarter(d: date) -> tuple[str, int, int]:
    """Return (quarter_label, fiscal_year, quarter_num) for a calendar date."""
    # Indian FY: Apr–Mar
    if d.month >= 4:
        fy = d.year + 1
    else:
        fy = d.year

    month_to_q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2,
                  10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}
    q_num = month_to_q[d.month]
    label = f"Q{q_num}FY{str(fy)[2:]}"
    return label, fy, q_num


def _cagr(begin: float, end: float, years: float) -> Optional[float]:
    if begin <= 0 or years <= 0:
        return None
    return round((math.pow(end / begin, 1 / years) - 1) * 100, 2)


def _pct_change(old: float, new: float) -> Optional[float]:
    if old == 0:
        return None
    return round((new - old) / old * 100, 2)


# ---------------------------------------------------------------------------
# Order announcement helpers
# ---------------------------------------------------------------------------
async def get_order_announcements(
    db: AsyncSession,
    isin: str,
    limit: int = 50,
    offset: int = 0,
) -> list[OrderAnnouncement]:
    result = await db.execute(
        select(OrderAnnouncement)
        .where(OrderAnnouncement.isin == isin)
        .order_by(desc(OrderAnnouncement.announced_date))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_recent_orders_all(
    db: AsyncSession,
    limit: int = 50,
    sector: Optional[str] = None,
    min_amount_cr: Optional[float] = None,
) -> list[OrderAnnouncement]:
    q = (
        select(OrderAnnouncement)
        .where(OrderAnnouncement.processing_status == "DONE")
        .order_by(desc(OrderAnnouncement.announced_date))
    )
    if sector:
        q = q.where(OrderAnnouncement.sector == sector)
    if min_amount_cr:
        q = q.where(OrderAnnouncement.order_amount_cr >= min_amount_cr)
    result = await db.execute(q.limit(limit))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Snapshot management
# ---------------------------------------------------------------------------
async def upsert_quarterly_snapshot(
    db: AsyncSession,
    isin: str,
    company_name: str,
    quarter: str,
    fiscal_year: int,
    quarter_num: int,
    snapshot_date: date,
    new_orders_cr: float,
    quarterly_revenue_cr: Optional[float] = None,
) -> OrderBookSnapshot:
    """
    Build or refresh the closing order book for a given quarter.
    closing_OB = previous_closing + new_orders - executed (proxied by revenue)
    """
    # Get previous quarter snapshot
    result = await db.execute(
        select(OrderBookSnapshot)
        .where(
            OrderBookSnapshot.isin == isin,
            OrderBookSnapshot.fiscal_year == fiscal_year,
            OrderBookSnapshot.quarter_num == quarter_num - 1 if quarter_num > 1 else 4,
        )
        .order_by(desc(OrderBookSnapshot.snapshot_date))
        .limit(1)
    )
    prev = result.scalar_one_or_none()
    opening = prev.closing_order_book_cr if prev else 0.0

    # Revenue executed from order book ≈ quarterly_revenue (conservative proxy)
    executed = quarterly_revenue_cr or 0.0
    closing = (opening or 0.0) + new_orders_cr - executed

    # Upsert
    result = await db.execute(
        select(OrderBookSnapshot).where(
            OrderBookSnapshot.isin == isin,
            OrderBookSnapshot.quarter == quarter,
        )
    )
    snap = result.scalar_one_or_none()
    if snap is None:
        snap = OrderBookSnapshot(
            isin=isin,
            company_name=company_name,
            quarter=quarter,
            fiscal_year=fiscal_year,
            quarter_num=quarter_num,
            snapshot_date=snapshot_date,
        )
        db.add(snap)

    snap.opening_order_book_cr = opening
    snap.new_orders_cr = (snap.new_orders_cr or 0.0) + new_orders_cr
    snap.revenue_executed_cr = executed
    snap.closing_order_book_cr = max(closing, 0.0)
    snap.quarterly_revenue_cr = quarterly_revenue_cr
    snap.updated_at = datetime.utcnow()

    await db.flush()
    return snap


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
async def compute_metrics(db: AsyncSession, isin: str) -> OrderBookMetrics:
    """
    Recompute all derived metrics for a company from snapshots + announcements.
    """
    # ── Fetch all snapshots sorted by date ───────────────────────────────────
    result = await db.execute(
        select(OrderBookSnapshot)
        .where(OrderBookSnapshot.isin == isin)
        .order_by(OrderBookSnapshot.fiscal_year, OrderBookSnapshot.quarter_num)
    )
    snaps: list[OrderBookSnapshot] = result.scalars().all()

    # ── Fetch all announcements ──────────────────────────────────────────────
    result2 = await db.execute(
        select(OrderAnnouncement).where(
            OrderAnnouncement.isin == isin,
            OrderAnnouncement.processing_status == "DONE",
            OrderAnnouncement.order_amount_cr.isnot(None),
        )
    )
    orders: list[OrderAnnouncement] = result2.scalars().all()

    if not snaps and not orders:
        return await _get_or_create_metrics(db, isin, "")

    # ── TTM orders won ───────────────────────────────────────────────────────
    cutoff = date.today() - timedelta(days=365)
    ttm_orders = [o for o in orders if o.announced_date and o.announced_date >= cutoff]
    ttm_orders_cr = sum(o.order_amount_cr for o in ttm_orders if o.order_amount_cr)

    # Prior-year TTM for YoY
    cutoff2 = cutoff - timedelta(days=365)
    prev_ttm = [o for o in orders if o.announced_date and cutoff2 <= o.announced_date < cutoff]
    prev_ttm_cr = sum(o.order_amount_cr for o in prev_ttm if o.order_amount_cr)

    inflow_growth_yoy = _pct_change(prev_ttm_cr, ttm_orders_cr)

    # ── Order book (latest closing snapshot) ────────────────────────────────
    latest_snap = snaps[-1] if snaps else None
    prev_year_snap = None
    if latest_snap:
        for s in snaps:
            if s.fiscal_year == latest_snap.fiscal_year - 1 and s.quarter_num == latest_snap.quarter_num:
                prev_year_snap = s
                break

    current_ob = latest_snap.closing_order_book_cr if latest_snap else ttm_orders_cr
    prev_ob = prev_year_snap.closing_order_book_cr if prev_year_snap else None
    ob_growth_yoy = _pct_change(prev_ob, current_ob) if prev_ob else None

    # ── CAGR ─────────────────────────────────────────────────────────────────
    snap_3y = next((s for s in reversed(snaps) if s.fiscal_year == (latest_snap.fiscal_year - 3 if latest_snap else 0)), None)
    snap_5y = next((s for s in reversed(snaps) if s.fiscal_year == (latest_snap.fiscal_year - 5 if latest_snap else 0)), None)
    cagr_3y = _cagr(snap_3y.closing_order_book_cr, current_ob, 3) if snap_3y and snap_3y.closing_order_book_cr else None
    cagr_5y = _cagr(snap_5y.closing_order_book_cr, current_ob, 5) if snap_5y and snap_5y.closing_order_book_cr else None

    # ── Ratios ───────────────────────────────────────────────────────────────
    ttm_revenue = latest_snap.annual_revenue_ttm_cr if latest_snap else None
    ob_to_sales = round(current_ob / ttm_revenue, 2) if ttm_revenue and ttm_revenue > 0 else None
    prev_ob_to_sales = round(prev_ob / ttm_revenue, 2) if prev_ob and ttm_revenue and ttm_revenue > 0 else None
    bill_to_book = round(ttm_orders_cr / ttm_revenue, 2) if ttm_revenue and ttm_revenue > 0 else None

    if ob_to_sales and prev_ob_to_sales:
        if ob_to_sales > prev_ob_to_sales * 1.05:
            ob_sales_trend = "IMPROVING"
        elif ob_to_sales < prev_ob_to_sales * 0.95:
            ob_sales_trend = "DETERIORATING"
        else:
            ob_sales_trend = "STABLE"
    else:
        ob_sales_trend = "STABLE"

    # ── Acceleration score (0–100) ───────────────────────────────────────────
    score = _compute_acceleration_score(
        inflow_growth_yoy=inflow_growth_yoy or 0,
        ob_growth_yoy=ob_growth_yoy or 0,
        ob_to_sales=ob_to_sales or 0,
        bill_to_book=bill_to_book or 0,
        snaps=snaps,
    )
    if score >= 65:
        momentum = "ACCELERATING"
    elif score <= 35:
        momentum = "DECELERATING"
    else:
        momentum = "STABLE"

    # ── Mix ──────────────────────────────────────────────────────────────────
    total_amt = sum(o.order_amount_cr for o in ttm_orders if o.order_amount_cr) or 1
    domestic_amt = sum(
        o.order_amount_cr for o in ttm_orders
        if o.order_amount_cr and o.order_type in ("DOMESTIC", None)
    )
    export_amt = sum(
        o.order_amount_cr for o in ttm_orders
        if o.order_amount_cr and o.order_type == "EXPORT"
    )
    domestic_pct = round(domestic_amt / total_amt * 100, 1) if total_amt else None
    export_pct = round(export_amt / total_amt * 100, 1) if total_amt else None

    # Sector breakdown
    sector_map: dict[str, float] = {}
    for o in ttm_orders:
        cat = o.sector_category or "OTHER"
        sector_map[cat] = sector_map.get(cat, 0) + (o.order_amount_cr or 0)
    sector_pcts = {k: round(v / total_amt * 100, 1) for k, v in sector_map.items()}

    # Customer concentration (top 5)
    cust_map: dict[str, float] = {}
    for o in ttm_orders:
        name = o.customer_name or "UNDISCLOSED"
        cust_map[name] = cust_map.get(name, 0) + (o.order_amount_cr or 0)
    top_customers = sorted(cust_map.items(), key=lambda x: x[1], reverse=True)[:5]
    customer_conc = [{"name": k, "amount_cr": round(v, 1), "pct": round(v / total_amt * 100, 1)}
                     for k, v in top_customers]

    # ── Scenarios ────────────────────────────────────────────────────────────
    bull, base, bear, assumptions = _build_scenarios(
        current_ob=current_ob,
        ttm_revenue=ttm_revenue,
        avg_inflow_qtrly=ttm_orders_cr / 4 if ttm_orders_cr else 0,
        inflow_growth_yoy=inflow_growth_yoy or 0,
    )

    # ── Persist ──────────────────────────────────────────────────────────────
    m = await _get_or_create_metrics(
        db, isin, orders[0].company_name if orders else ""
    )
    m.current_order_book_cr = current_ob
    m.last_order_date = max(o.announced_date for o in orders) if orders else None
    m.total_orders_count = len(orders)
    m.ttm_orders_won_cr = ttm_orders_cr
    m.order_inflow_growth_yoy_pct = inflow_growth_yoy
    m.order_book_growth_yoy_pct = ob_growth_yoy
    m.order_book_cagr_3y = cagr_3y
    m.order_book_cagr_5y = cagr_5y
    m.order_book_to_sales = ob_to_sales
    m.order_book_to_sales_prev = prev_ob_to_sales
    m.bill_to_book_ratio = bill_to_book
    m.order_to_sales_trend = ob_sales_trend
    m.order_acceleration_score = score
    m.order_momentum = momentum
    m.bull_case_ob_cr = bull
    m.base_case_ob_cr = base
    m.bear_case_ob_cr = bear
    m.scenario_assumptions = assumptions
    m.domestic_pct = domestic_pct
    m.export_pct = export_pct
    m.sector_breakdown = sector_pcts
    m.customer_concentration = customer_conc
    m.updated_at = datetime.utcnow()

    await db.flush()
    return m


def _compute_acceleration_score(
    inflow_growth_yoy: float,
    ob_growth_yoy: float,
    ob_to_sales: float,
    bill_to_book: float,
    snaps: list[OrderBookSnapshot],
) -> float:
    """
    Composite 0–100 score.
    40 pts: inflow growth cadence (QoQ acceleration in last 4 quarters)
    30 pts: bill-to-book > 1.0
    20 pts: OB/Sales improvement
    10 pts: YoY order book growth
    """
    score = 0.0

    # Inflow growth (40 pts)
    if inflow_growth_yoy >= 30:
        score += 40
    elif inflow_growth_yoy >= 15:
        score += 30
    elif inflow_growth_yoy >= 0:
        score += 20
    elif inflow_growth_yoy >= -10:
        score += 10

    # Bill-to-book (30 pts)
    if bill_to_book >= 1.5:
        score += 30
    elif bill_to_book >= 1.2:
        score += 22
    elif bill_to_book >= 1.0:
        score += 15
    elif bill_to_book >= 0.8:
        score += 7

    # OB/Sales (20 pts) — higher is better up to a point
    if ob_to_sales >= 3.0:
        score += 20
    elif ob_to_sales >= 2.0:
        score += 15
    elif ob_to_sales >= 1.5:
        score += 10
    elif ob_to_sales >= 1.0:
        score += 5

    # YoY OB growth (10 pts)
    if ob_growth_yoy >= 20:
        score += 10
    elif ob_growth_yoy >= 10:
        score += 6
    elif ob_growth_yoy >= 0:
        score += 3

    return round(min(score, 100), 1)


def _build_scenarios(
    current_ob: float,
    ttm_revenue: Optional[float],
    avg_inflow_qtrly: float,
    inflow_growth_yoy: float,
    horizon_quarters: int = 4,
) -> tuple[float, float, float, dict]:
    """Project order book 4 quarters out under 3 scenarios."""
    revenue_per_q = ttm_revenue / 4 if ttm_revenue else avg_inflow_qtrly * 0.7

    # Growth rates: bull assumes acceleration, base flat, bear slowdown
    bull_growth_q = max(inflow_growth_yoy * 1.5, 20) / 100 / 4   # quarterly equivalent
    base_growth_q = max(inflow_growth_yoy * 0.8, 5) / 100 / 4
    bear_growth_q = min(inflow_growth_yoy * 0.3, -5) / 100 / 4

    def project(qtrly_growth: float) -> float:
        ob = current_ob
        inflow = avg_inflow_qtrly
        for _ in range(horizon_quarters):
            inflow *= (1 + qtrly_growth)
            ob = ob + inflow - revenue_per_q
        return round(max(ob, 0), 1)

    bull = project(bull_growth_q)
    base = project(base_growth_q)
    bear = project(bear_growth_q)

    assumptions = {
        "bull": {
            "quarterly_inflow_growth_pct": round(bull_growth_q * 100, 1),
            "key_driver": "Strong macro order cycle; new geographies",
            "win_rate_assumption": "Above historical average",
        },
        "base": {
            "quarterly_inflow_growth_pct": round(base_growth_q * 100, 1),
            "key_driver": "Steady state; existing pipeline conversion",
            "win_rate_assumption": "Historical average maintained",
        },
        "bear": {
            "quarterly_inflow_growth_pct": round(bear_growth_q * 100, 1),
            "key_driver": "Demand slowdown; increased competition",
            "win_rate_assumption": "Below average; pricing pressure",
        },
    }
    return bull, base, bear, assumptions


async def _get_or_create_metrics(
    db: AsyncSession, isin: str, company_name: str
) -> OrderBookMetrics:
    result = await db.execute(
        select(OrderBookMetrics).where(OrderBookMetrics.isin == isin)
    )
    m = result.scalar_one_or_none()
    if m is None:
        m = OrderBookMetrics(isin=isin, company_name=company_name)
        db.add(m)
        await db.flush()
    return m


# ---------------------------------------------------------------------------
# Chart data assembly
# ---------------------------------------------------------------------------
async def build_charts_data(db: AsyncSession, isin: str) -> ChartsData:
    # Quarterly
    result = await db.execute(
        select(OrderBookSnapshot)
        .where(OrderBookSnapshot.isin == isin)
        .order_by(OrderBookSnapshot.fiscal_year, OrderBookSnapshot.quarter_num)
    )
    snaps = result.scalars().all()

    quarterly = [
        QuarterlyChartPoint(
            quarter=s.quarter,
            order_book_cr=float(s.closing_order_book_cr) if s.closing_order_book_cr else None,
            new_orders_cr=float(s.new_orders_cr) if s.new_orders_cr else None,
            executed_cr=float(s.revenue_executed_cr) if s.revenue_executed_cr else None,
            ob_to_sales=(
                round(float(s.closing_order_book_cr) / float(s.annual_revenue_ttm_cr), 2)
                if s.closing_order_book_cr and s.annual_revenue_ttm_cr
                else None
            ),
        )
        for s in snaps
    ]

    # YoY — group by fiscal year
    fy_map: dict[int, float] = {}
    for s in snaps:
        fy_map[s.fiscal_year] = fy_map.get(s.fiscal_year, 0) + float(s.new_orders_cr or 0)

    yoy_points = []
    prev_val = None
    for fy in sorted(fy_map):
        val = fy_map[fy]
        growth = _pct_change(prev_val, val) if prev_val else None
        yoy_points.append(
            YoYChartPoint(
                fiscal_year=fy,
                ttm_orders_cr=round(val, 1),
                yoy_growth_pct=growth,
            )
        )
        prev_val = val

    # Rolling 4-quarter order inflows
    result2 = await db.execute(
        select(OrderAnnouncement)
        .where(
            OrderAnnouncement.isin == isin,
            OrderAnnouncement.processing_status == "DONE",
            OrderAnnouncement.order_amount_cr.isnot(None),
        )
        .order_by(OrderAnnouncement.announced_date)
    )
    orders = result2.scalars().all()

    rolling: list[RollingChartPoint] = []
    if orders:
        # Monthly rolling sum over 12 months
        months = []
        if orders:
            start = orders[0].announced_date.replace(day=1)
            end = date.today()
            cur = start
            while cur <= end:
                months.append(cur)
                # next month
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1)
                else:
                    cur = cur.replace(month=cur.month + 1)

        window_days = 365
        for m in months:
            cutoff_start = m - timedelta(days=window_days)
            total = sum(
                float(o.order_amount_cr)
                for o in orders
                if o.announced_date and cutoff_start <= o.announced_date <= m
            )
            rolling.append(
                RollingChartPoint(
                    date=m.isoformat(),
                    rolling_4q_cr=round(total, 1),
                )
            )

    return ChartsData(quarterly=quarterly, yoy_growth=yoy_points, rolling=rolling)


# ---------------------------------------------------------------------------
# Full dashboard assembly
# ---------------------------------------------------------------------------
async def get_dashboard(db: AsyncSession, isin: str) -> Optional[OrderTrackingDashboard]:
    # Metrics
    res_m = await db.execute(
        select(OrderBookMetrics).where(OrderBookMetrics.isin == isin)
    )
    metrics = res_m.scalar_one_or_none()

    # History
    res_s = await db.execute(
        select(OrderBookSnapshot)
        .where(OrderBookSnapshot.isin == isin)
        .order_by(OrderBookSnapshot.fiscal_year, OrderBookSnapshot.quarter_num)
    )
    snaps = res_s.scalars().all()

    if not snaps and not metrics:
        return None

    company_name = (metrics.company_name if metrics else None) or (snaps[0].company_name if snaps else isin)

    history = OrderBookHistory(
        isin=isin,
        company_name=company_name,
        snapshots=[SnapshotPoint.model_validate(s) for s in snaps],
    )

    # Recent orders
    res_o = await db.execute(
        select(OrderAnnouncement)
        .where(
            OrderAnnouncement.isin == isin,
            OrderAnnouncement.processing_status == "DONE",
        )
        .order_by(desc(OrderAnnouncement.announced_date))
        .limit(10)
    )
    recent = res_o.scalars().all()

    # Latest AI summary
    res_ai = await db.execute(
        select(OrderAISummary)
        .where(OrderAISummary.isin == isin)
        .order_by(desc(OrderAISummary.generated_at))
        .limit(1)
    )
    ai_sum = res_ai.scalar_one_or_none()

    from .schemas import (
        OrderAISummaryOut,
        OrderAnnouncementOut,
        OrderBookMetricsOut,
    )

    return OrderTrackingDashboard(
        isin=isin,
        company_name=company_name,
        sector=recent[0].sector if recent else None,
        metrics=OrderBookMetricsOut.model_validate(metrics) if metrics else None,
        history=history,
        recent_orders=[OrderAnnouncementOut.model_validate(o) for o in recent],
        ai_summary=OrderAISummaryOut.model_validate(ai_sum) if ai_sum else None,
    )
