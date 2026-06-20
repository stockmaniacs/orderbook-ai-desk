"""
Master Tracker Service.

Orchestrates: ingestion → comparison → alert generation → dashboard assembly.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ExpectationComparison,
    MasterThesis,
    PromoterTracking,
    QuarterlyActual,
    QuarterlyTarget,
    StockScenario,
    TechnicalSnapshot,
    ThesisAlert,
    TrackedStock,
)
from .comparison_engine import (
    Alert,
    compute_comparison,
    compute_risk_reward,
    compute_technical_score,
    generate_alerts,
)

log = logging.getLogger(__name__)


# ─── Add / update stock ───────────────────────────────────────────────────────
async def add_or_update_stock(
    db: AsyncSession,
    isin: str,
    company_name: str,
    **kwargs: Any,
) -> TrackedStock:
    stmt = pg_insert(TrackedStock).values(
        isin=isin,
        company_name=company_name,
        added_date=date.today(),
        **kwargs,
    ).on_conflict_do_update(
        index_elements=["isin"],
        set_={
            "company_name": company_name,
            "updated_at": datetime.utcnow(),
            **{k: v for k, v in kwargs.items() if v is not None},
        },
    ).returning(TrackedStock)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


# ─── Set quarterly target ─────────────────────────────────────────────────────
async def set_quarterly_target(
    db: AsyncSession,
    isin: str,
    fiscal_year: int,
    quarter: str,
    **fields: Any,
) -> QuarterlyTarget:
    stmt = pg_insert(QuarterlyTarget).values(
        isin=isin, fiscal_year=fiscal_year, quarter=quarter, **fields,
    ).on_conflict_do_update(
        constraint="uq_qt_period",
        set_={k: v for k, v in fields.items()},
    ).returning(QuarterlyTarget)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


# ─── Ingest quarterly actuals + run comparison ────────────────────────────────
async def ingest_quarterly_actual(
    db: AsyncSession,
    isin: str,
    fiscal_year: int,
    quarter: str,
    **fields: Any,
) -> dict:
    """
    1. Upsert QuarterlyActual
    2. Compute comparison vs QuarterlyTarget
    3. Persist ExpectationComparison
    4. Generate + persist ThesisAlerts
    5. Update TrackedStock overall_signal + consecutive_red
    Returns {"comparison": ..., "alerts_generated": n}
    """
    # 1. Upsert actual
    stmt = pg_insert(QuarterlyActual).values(
        isin=isin, fiscal_year=fiscal_year, quarter=quarter, **fields,
    ).on_conflict_do_update(
        constraint="uq_qa_period",
        set_={k: v for k, v in fields.items()},
    ).returning(QuarterlyActual)
    result = await db.execute(stmt)
    actual = result.scalar_one()

    # 2. Load target
    tgt_result = await db.execute(
        select(QuarterlyTarget).where(
            QuarterlyTarget.isin == isin,
            QuarterlyTarget.fiscal_year == fiscal_year,
            QuarterlyTarget.quarter == quarter,
        )
    )
    target = tgt_result.scalar_one_or_none()

    # 3. Run comparison engine
    comp = compute_comparison(
        actual_revenue=_f(actual.revenue_cr),
        actual_ebitda=_f(actual.ebitda_cr),
        actual_ebitda_margin=actual.ebitda_margin,
        actual_pat=_f(actual.pat_cr),
        actual_order_book=_f(actual.order_book_cr),
        actual_capex=_f(actual.capex_cr),
        exp_revenue=_f(target.expected_revenue_cr) if target else None,
        exp_ebitda=_f(target.expected_ebitda_cr) if target else None,
        exp_ebitda_margin=target.expected_ebitda_margin if target else None,
        exp_pat=_f(target.expected_pat_cr) if target else None,
        exp_order_book=_f(target.expected_order_book_cr) if target else None,
        exp_capex=_f(target.expected_capex_cr) if target else None,
        guidance_revised=actual.guidance_revised or False,
        guidance_delta_pct=actual.guidance_revision_pct,
    )

    # 4. Persist comparison
    comp_stmt = pg_insert(ExpectationComparison).values(
        isin=isin, fiscal_year=fiscal_year, quarter=quarter,
        revenue_signal=comp.revenue_signal,
        ebitda_signal=comp.ebitda_signal,
        margin_signal=comp.margin_signal,
        pat_signal=comp.pat_signal,
        order_book_signal=comp.order_book_signal,
        capex_signal=comp.capex_signal,
        guidance_signal=comp.guidance_signal,
        overall_signal=comp.overall_signal,
        revenue_beat_pct=comp.revenue_beat_pct,
        ebitda_beat_pct=comp.ebitda_beat_pct,
        margin_delta_bps=comp.margin_delta_bps,
        pat_beat_pct=comp.pat_beat_pct,
        order_book_beat_pct=comp.order_book_beat_pct,
        beat_count=comp.beat_count,
        miss_count=comp.miss_count,
        in_line_count=comp.in_line_count,
        verdict=comp.verdict,
        computed_at=datetime.utcnow(),
    ).on_conflict_do_update(
        constraint="uq_comp_period",
        set_={
            "revenue_signal": comp.revenue_signal,
            "ebitda_signal": comp.ebitda_signal,
            "margin_signal": comp.margin_signal,
            "pat_signal": comp.pat_signal,
            "order_book_signal": comp.order_book_signal,
            "overall_signal": comp.overall_signal,
            "beat_count": comp.beat_count,
            "miss_count": comp.miss_count,
            "verdict": comp.verdict,
            "computed_at": datetime.utcnow(),
        },
    )
    await db.execute(comp_stmt)

    # 5. Update TrackedStock signal + consecutive_red
    stock_result = await db.execute(
        select(TrackedStock).where(TrackedStock.isin == isin)
    )
    stock = stock_result.scalar_one_or_none()
    if stock:
        new_consec = (stock.consecutive_red + 1) if comp.overall_signal == "RED" else 0
        await db.execute(
            update(TrackedStock)
            .where(TrackedStock.isin == isin)
            .values(
                overall_signal=comp.overall_signal,
                consecutive_red=new_consec,
                last_updated_at=datetime.utcnow(),
            )
        )
        consecutive_red = new_consec
        company_name = stock.company_name
    else:
        consecutive_red = 0
        company_name = isin

    # 6. Promoter tracking if data present
    if fields.get("promoter_holding_pct") is not None:
        await _update_promoter(
            db, isin, fiscal_year, quarter,
            holding=fields.get("promoter_holding_pct"),
            pledged=fields.get("promoter_pledged_pct"),
            fii=fields.get("fii_holding_pct"),
        )

    # 7. Generate alerts
    alerts = generate_alerts(
        isin=isin,
        company_name=company_name,
        comparison=comp,
        consecutive_red=consecutive_red,
        fiscal_year=fiscal_year,
        quarter=quarter,
        guidance_revised=actual.guidance_revised or False,
        guidance_delta_pct=actual.guidance_revision_pct,
        margin_delta_bps=comp.margin_delta_bps,
        order_book_beat_pct=comp.order_book_beat_pct,
    )
    for alert in alerts:
        db.add(ThesisAlert(
            isin=isin,
            company_name=company_name,
            alert_type=alert.alert_type,
            severity=alert.severity,
            title=alert.title,
            description=alert.description,
            data_snapshot=alert.data_snapshot,
            fiscal_year=fiscal_year,
            quarter=quarter,
        ))

    await db.commit()
    log.info(
        "Ingested %s %s Q%s FY%s | verdict=%s | alerts=%d",
        company_name, isin, quarter, fiscal_year, comp.verdict, len(alerts),
    )

    return {
        "isin": isin, "quarter": quarter, "fiscal_year": fiscal_year,
        "verdict": comp.verdict, "overall_signal": comp.overall_signal,
        "beat_count": comp.beat_count, "miss_count": comp.miss_count,
        "alerts_generated": len(alerts),
    }


# ─── Update technical snapshot ────────────────────────────────────────────────
async def update_technical_snapshot(
    db: AsyncSession,
    isin: str,
    snapshot_date: date,
    **fields: Any,
) -> TechnicalSnapshot:
    score, trend = compute_technical_score(
        above_sma_50=fields.get("above_sma_50"),
        above_sma_200=fields.get("above_sma_200"),
        golden_cross=fields.get("golden_cross"),
        death_cross=fields.get("death_cross"),
        rsi_14=fields.get("rsi_14"),
        macd_histogram=fields.get("macd_histogram"),
        pct_from_52w_high=fields.get("pct_from_52w_high"),
    )

    stmt = pg_insert(TechnicalSnapshot).values(
        isin=isin, snapshot_date=snapshot_date,
        trend=trend, technical_score=score, **fields,
    ).on_conflict_do_update(
        constraint="uq_tech_date",
        set_={"trend": trend, "technical_score": score, **fields},
    ).returning(TechnicalSnapshot)
    result = await db.execute(stmt)
    snap = result.scalar_one()

    # Propagate to TrackedStock
    await db.execute(
        update(TrackedStock)
        .where(TrackedStock.isin == isin)
        .values(
            technical_trend=trend,
            technical_score=score,
            cmp=fields.get("close_price"),
            price_updated_at=datetime.utcnow(),
        )
    )
    await db.commit()
    return snap


# ─── Master dashboard ─────────────────────────────────────────────────────────
async def get_master_dashboard(
    db: AsyncSession,
    sort_by: str = "risk_reward_score",
    sector: str | None = None,
    signal: str | None = None,
    market_cap_cat: str | None = None,
    rating: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    q = select(TrackedStock).where(TrackedStock.tracking_status == "ACTIVE")
    if sector:        q = q.where(TrackedStock.sector.ilike(f"%{sector}%"))
    if signal:        q = q.where(TrackedStock.overall_signal == signal)
    if market_cap_cat: q = q.where(TrackedStock.market_cap_cat == market_cap_cat)
    if rating:        q = q.where(TrackedStock.rating == rating)

    # Sort
    sort_col = {
        "risk_reward_score": TrackedStock.risk_reward_score.desc().nullslast(),
        "expected_cagr_3y":  TrackedStock.expected_cagr_3y.desc().nullslast(),
        "technical_score":   TrackedStock.technical_score.desc().nullslast(),
        "market_cap_cr":     TrackedStock.market_cap_cr.desc().nullslast(),
        "upside_pct":        TrackedStock.upside_pct.desc().nullslast(),
        "consecutive_red":   TrackedStock.consecutive_red.asc(),
        "sector":            TrackedStock.sector.asc().nullslast(),
    }.get(sort_by, TrackedStock.risk_reward_score.desc().nullslast())

    count_result = await db.execute(
        select(func.count()).select_from(TrackedStock).where(TrackedStock.tracking_status == "ACTIVE")
    )
    total = count_result.scalar()

    q = q.order_by(sort_col).limit(limit).offset(offset)
    result = await db.execute(q)
    stocks = result.scalars().all()

    # Get unread alert counts + last verdict per stock
    alert_counts = await _get_alert_counts(db, [s.isin for s in stocks])
    last_verdicts = await _get_last_verdicts(db, [s.isin for s in stocks])

    items = []
    for s in stocks:
        items.append({
            "isin": s.isin,
            "symbol_nse": s.symbol_nse,
            "company_name": s.company_name,
            "sector": s.sector,
            "market_cap_cr": float(s.market_cap_cr) if s.market_cap_cr else None,
            "market_cap_cat": s.market_cap_cat,
            "cmp": float(s.cmp) if s.cmp else None,
            "target_price_12m": float(s.target_price_12m) if s.target_price_12m else None,
            "upside_pct": s.upside_pct,
            "expected_cagr_3y": s.expected_cagr_3y,
            "rating": s.rating,
            "overall_signal": s.overall_signal,
            "thesis_quality": s.thesis_quality,
            "risk_reward_score": s.risk_reward_score,
            "conviction_score": s.conviction_score,
            "technical_trend": s.technical_trend,
            "technical_score": s.technical_score,
            "consecutive_red": s.consecutive_red or 0,
            "last_verdict": last_verdicts.get(s.isin, {}).get("verdict"),
            "last_quarter": last_verdicts.get(s.isin, {}).get("quarter"),
            "unread_alert_count": alert_counts.get(s.isin, 0),
        })

    # Total alerts
    alert_total = await db.execute(
        select(func.count()).select_from(ThesisAlert).where(ThesisAlert.is_read.is_(False))
    )
    high_sev = await db.execute(
        select(func.count()).select_from(ThesisAlert)
        .where(ThesisAlert.is_read.is_(False), ThesisAlert.severity == "HIGH")
    )

    return {
        "total": total,
        "items": items,
        "alert_count": alert_total.scalar(),
        "high_severity_count": high_sev.scalar(),
    }


# ─── Company detail ───────────────────────────────────────────────────────────
async def get_company_detail(db: AsyncSession, isin: str) -> dict | None:
    stock_r = await db.execute(select(TrackedStock).where(TrackedStock.isin == isin))
    stock = stock_r.scalar_one_or_none()
    if not stock:
        return None

    thesis_r = await db.execute(
        select(MasterThesis)
        .where(MasterThesis.isin == isin, MasterThesis.is_current.is_(True))
        .limit(1)
    )
    thesis = thesis_r.scalar_one_or_none()

    scenarios_r = await db.execute(
        select(StockScenario)
        .where(StockScenario.isin == isin, StockScenario.is_current.is_(True))
        .order_by(StockScenario.scenario_type)
    )
    scenarios = scenarios_r.scalars().all()

    # Quarterly history (targets + actuals + comparisons) — last 8 quarters
    quarters = await _get_quarterly_history(db, isin, limit=8)

    alerts_r = await db.execute(
        select(ThesisAlert)
        .where(ThesisAlert.isin == isin)
        .order_by(ThesisAlert.triggered_at.desc())
        .limit(10)
    )
    alerts = alerts_r.scalars().all()

    latest_tech_r = await db.execute(
        select(TechnicalSnapshot)
        .where(TechnicalSnapshot.isin == isin)
        .order_by(TechnicalSnapshot.snapshot_date.desc())
        .limit(1)
    )
    latest_tech = latest_tech_r.scalar_one_or_none()

    promoter_r = await db.execute(
        select(PromoterTracking)
        .where(PromoterTracking.isin == isin)
        .order_by(PromoterTracking.fiscal_year.desc(), PromoterTracking.quarter.desc())
        .limit(8)
    )
    promoter_history = promoter_r.scalars().all()

    return {
        "stock": stock,
        "thesis": thesis,
        "scenarios": list(scenarios),
        "quarterly_history": quarters,
        "recent_alerts": list(alerts),
        "latest_technical": latest_tech,
        "promoter_history": list(promoter_history),
    }


# ─── Alert feed ───────────────────────────────────────────────────────────────
async def get_alerts(
    db: AsyncSession,
    isin: str | None = None,
    severity: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> list[ThesisAlert]:
    q = select(ThesisAlert).order_by(ThesisAlert.triggered_at.desc())
    if isin:         q = q.where(ThesisAlert.isin == isin)
    if severity:     q = q.where(ThesisAlert.severity == severity)
    if unread_only:  q = q.where(ThesisAlert.is_read.is_(False))
    q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def mark_alert(db: AsyncSession, alert_id: str, is_read: bool | None, is_actioned: bool | None) -> None:
    vals: dict = {}
    if is_read is not None:     vals["is_read"] = is_read
    if is_actioned is not None: vals["is_actioned"] = is_actioned
    if vals:
        await db.execute(update(ThesisAlert).where(ThesisAlert.id == alert_id).values(**vals))
        await db.commit()


# ─── Recalculate risk-reward for a stock ─────────────────────────────────────
async def recalculate_scores(db: AsyncSession, isin: str) -> None:
    result = await db.execute(select(TrackedStock).where(TrackedStock.isin == isin))
    stock = result.scalar_one_or_none()
    if not stock:
        return

    rr = compute_risk_reward(
        upside_pct=stock.upside_pct,
        expected_cagr_3y=stock.expected_cagr_3y,
        conviction_score=stock.conviction_score,
        consecutive_red=stock.consecutive_red or 0,
        overall_signal=stock.overall_signal or "YELLOW",
        technical_score=stock.technical_score,
    )
    await db.execute(
        update(TrackedStock)
        .where(TrackedStock.isin == isin)
        .values(risk_reward_score=rr, updated_at=datetime.utcnow())
    )
    await db.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _f(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


async def _get_alert_counts(db: AsyncSession, isins: list[str]) -> dict[str, int]:
    if not isins:
        return {}
    result = await db.execute(text("""
    SELECT isin, COUNT(*) AS cnt
    FROM mt_alerts
    WHERE isin = ANY(:isins) AND is_read = false
    GROUP BY isin
    """), {"isins": isins})
    return {r.isin: r.cnt for r in result.fetchall()}


async def _get_last_verdicts(db: AsyncSession, isins: list[str]) -> dict[str, dict]:
    if not isins:
        return {}
    result = await db.execute(text("""
    SELECT DISTINCT ON (isin) isin, fiscal_year, quarter, verdict, overall_signal
    FROM mt_comparisons
    WHERE isin = ANY(:isins)
    ORDER BY isin, fiscal_year DESC, quarter DESC
    """), {"isins": isins})
    return {
        r.isin: {"verdict": r.verdict, "quarter": f"{r.quarter} FY{str(r.fiscal_year)[-2:]}"}
        for r in result.fetchall()
    }


async def _get_quarterly_history(db: AsyncSession, isin: str, limit: int = 8) -> list[dict]:
    targets_r = await db.execute(
        select(QuarterlyTarget)
        .where(QuarterlyTarget.isin == isin)
        .order_by(QuarterlyTarget.fiscal_year.desc(), QuarterlyTarget.quarter.desc())
        .limit(limit)
    )
    targets = {(t.fiscal_year, t.quarter): t for t in targets_r.scalars().all()}

    actuals_r = await db.execute(
        select(QuarterlyActual)
        .where(QuarterlyActual.isin == isin)
        .order_by(QuarterlyActual.fiscal_year.desc(), QuarterlyActual.quarter.desc())
        .limit(limit)
    )
    actuals = {(a.fiscal_year, a.quarter): a for a in actuals_r.scalars().all()}

    comps_r = await db.execute(
        select(ExpectationComparison)
        .where(ExpectationComparison.isin == isin)
        .order_by(ExpectationComparison.fiscal_year.desc(), ExpectationComparison.quarter.desc())
        .limit(limit)
    )
    comps = {(c.fiscal_year, c.quarter): c for c in comps_r.scalars().all()}

    # Merge all known periods
    all_periods = set(targets.keys()) | set(actuals.keys()) | set(comps.keys())
    sorted_periods = sorted(all_periods, reverse=True)[:limit]

    return [
        {
            "fiscal_year": fy,
            "quarter": q,
            "target": targets.get((fy, q)),
            "actual": actuals.get((fy, q)),
            "comparison": comps.get((fy, q)),
        }
        for fy, q in sorted_periods
    ]


async def _update_promoter(
    db: AsyncSession,
    isin: str,
    fiscal_year: int,
    quarter: str,
    holding: float | None,
    pledged: float | None,
    fii: float | None,
) -> None:
    # Get previous quarter's data to compute deltas
    prev_r = await db.execute(
        select(PromoterTracking)
        .where(PromoterTracking.isin == isin)
        .order_by(PromoterTracking.fiscal_year.desc(), PromoterTracking.quarter.desc())
        .limit(1)
    )
    prev = prev_r.scalar_one_or_none()
    promoter_change = (holding - prev.promoter_holding_pct) if prev and prev.promoter_holding_pct and holding else None
    pledged_change  = (pledged - prev.promoter_pledged_pct) if prev and prev.promoter_pledged_pct and pledged else None

    # Signal
    sig = "YELLOW"
    if pledged_change and pledged_change > 2:        sig = "RED"
    elif pledged_change and pledged_change < -2:     sig = "GREEN"
    elif promoter_change and promoter_change > 1:    sig = "GREEN"
    elif promoter_change and promoter_change < -1:   sig = "RED"

    stmt = pg_insert(PromoterTracking).values(
        isin=isin, fiscal_year=fiscal_year, quarter=quarter,
        promoter_holding_pct=holding,
        promoter_pledged_pct=pledged,
        fii_pct=fii,
        promoter_change_pct=promoter_change,
        pledged_change_pct=pledged_change,
        signal=sig,
    ).on_conflict_do_update(
        constraint="uq_prom_period",
        set_={
            "promoter_holding_pct": holding,
            "promoter_pledged_pct": pledged,
            "promoter_change_pct": promoter_change,
            "pledged_change_pct": pledged_change,
            "signal": sig,
        },
    )
    await db.execute(stmt)
