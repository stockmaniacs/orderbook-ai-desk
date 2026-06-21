"""
FastAPI router — Master Tracker Worker.

Prefix: /api/v1/tracker

Endpoints:
  GET  /dashboard                   — master dashboard (all stocks)
  GET  /alerts                      — alert feed
  PATCH /alerts/{id}                — mark read / actioned

  GET  /{isin}                      — company detail (thesis + quarterly history)
  POST /{isin}/target               — set quarterly expectations
  POST /{isin}/actual               — ingest quarterly actual → triggers comparison
  GET  /{isin}/history              — quarterly history (targets + actuals + signals)
  GET  /{isin}/thesis               — investment thesis
  PUT  /{isin}/thesis               — update thesis
  GET  /{isin}/scenarios            — bull/base/bear scenarios
  GET  /{isin}/technical            — technical snapshot history
  GET  /{isin}/promoters            — promoter shareholding history
  GET  /{isin}/alerts               — alerts for one company

  POST /stocks                      — add stock to tracker
  DELETE /stocks/{isin}             — remove stock (set EXITED)
  POST /admin/seed-from-research    — pull thesis from Company Research worker
  POST /admin/recalculate-scores    — recalculate all risk-reward scores
  POST /admin/auto-set-targets      — AI-generate targets for upcoming quarter
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from .models import (
    ExpectationComparison,
    MasterThesis,
    QuarterlyActual,
    QuarterlyTarget,
    StockScenario,
    TechnicalSnapshot,
    ThesisAlert,
    TrackedStock,
)
from .schemas import (
    AddStockIn,
    AlertMarkIn,
    CompanyDetailOut,
    IngestActualIn,
    JobResultOut,
    MasterDashboardOut,
    QuarterlyTargetOut,
    SetTargetIn,
    ThesisAlertOut,
    UpdateThesisIn,
)
from .service import (
    add_or_update_stock,
    get_alerts,
    get_company_detail,
    get_master_dashboard,
    ingest_quarterly_actual,
    mark_alert,
    recalculate_scores,
    set_quarterly_target,
    update_technical_snapshot,
)
from .tasks import (
    auto_set_targets_task,
    recalculate_all_scores_task,
    seed_from_research_task,
)

router = APIRouter(tags=["Master Tracker"])


# ─── Master dashboard ─────────────────────────────────────────────────────────
@router.get("/dashboard")
async def master_dashboard(
    sort_by: str = Query("risk_reward_score", enum=[
        "risk_reward_score", "expected_cagr_3y", "technical_score",
        "market_cap_cr", "upside_pct", "consecutive_red", "sector",
    ]),
    sector: str | None = Query(None),
    signal: str | None = Query(None, enum=["GREEN", "YELLOW", "RED"]),
    market_cap_cat: str | None = Query(None, enum=["LARGE", "MID", "SMALL", "MICRO"]),
    rating: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_master_dashboard(
        db, sort_by=sort_by, sector=sector, signal=signal,
        market_cap_cat=market_cap_cat, rating=rating, limit=limit, offset=offset,
    )


# ─── Alert feed ───────────────────────────────────────────────────────────────
@router.get("/alerts")
async def list_alerts(
    severity: str | None = Query(None, enum=["HIGH", "MEDIUM", "LOW"]),
    unread_only: bool = Query(False),
    isin: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    alerts = await get_alerts(db, isin=isin, severity=severity, unread_only=unread_only, limit=limit)
    return [
        {
            "id": str(a.id),
            "isin": a.isin,
            "company_name": a.company_name,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "data_snapshot": a.data_snapshot,
            "fiscal_year": a.fiscal_year,
            "quarter": a.quarter,
            "is_read": a.is_read,
            "is_actioned": a.is_actioned,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        }
        for a in alerts
    ]


@router.patch("/alerts/{alert_id}", response_model=JobResultOut)
async def mark_alert_endpoint(
    alert_id: UUID,
    body: AlertMarkIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await mark_alert(db, str(alert_id), body.is_read, body.is_actioned)
    return {"status": "ok"}


# ─── Add stock ────────────────────────────────────────────────────────────────
@router.post("/stocks", response_model=JobResultOut)
async def add_stock(
    body: AddStockIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await add_or_update_stock(
        db, body.isin, body.company_name,
        symbol_nse=body.symbol_nse,
        sector=body.sector,
        market_cap_cat=body.market_cap_cat,
        tracking_priority=body.tracking_priority,
        tags=body.tags,
    )
    return {"status": "ok", "message": f"{body.company_name} added to tracker"}


@router.delete("/stocks/{isin}", response_model=JobResultOut)
async def remove_stock(isin: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(TrackedStock).where(TrackedStock.isin == isin).values(tracking_status="EXITED")
    )
    await db.commit()
    return {"status": "ok", "message": f"{isin} marked as EXITED"}


# ─── Company detail ───────────────────────────────────────────────────────────
@router.get("/{isin}")
async def company_detail(isin: str, db: AsyncSession = Depends(get_db)) -> dict:
    data = await get_company_detail(db, isin)
    if not data:
        raise HTTPException(status_code=404, detail=f"{isin} not found in tracker")

    stock = data["stock"]
    thesis = data["thesis"]
    scenarios = data["scenarios"]
    quarters = data["quarterly_history"]
    alerts = data["recent_alerts"]
    tech = data["latest_technical"]
    promoters = data["promoter_history"]

    def _f(v): return float(v) if v is not None else None

    return {
        "stock": {
            "isin": stock.isin,
            "symbol_nse": stock.symbol_nse,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "market_cap_cr": _f(stock.market_cap_cr),
            "market_cap_cat": stock.market_cap_cat,
            "cmp": _f(stock.cmp),
            "target_price_12m": _f(stock.target_price_12m),
            "upside_pct": stock.upside_pct,
            "expected_cagr_3y": stock.expected_cagr_3y,
            "fair_value": _f(stock.fair_value),
            "rating": stock.rating,
            "overall_signal": stock.overall_signal,
            "thesis_quality": stock.thesis_quality,
            "risk_reward_score": stock.risk_reward_score,
            "conviction_score": stock.conviction_score,
            "technical_trend": stock.technical_trend,
            "technical_score": stock.technical_score,
            "consecutive_red": stock.consecutive_red or 0,
            "tags": stock.tags,
        },
        "thesis": {
            "thesis_text": thesis.thesis_text if thesis else None,
            "growth_drivers": thesis.growth_drivers if thesis else [],
            "key_risks": thesis.key_risks if thesis else [],
            "moat": thesis.moat if thesis else None,
            "management_quality": thesis.management_quality if thesis else None,
            "expected_revenue_cagr_3y": thesis.expected_revenue_cagr_3y if thesis else None,
            "expected_ebitda_margin": thesis.expected_ebitda_margin if thesis else None,
            "expected_pat_cagr_3y": thesis.expected_pat_cagr_3y if thesis else None,
            "expected_pe_exit": thesis.expected_pe_exit if thesis else None,
            "bull_case": thesis.bull_case if thesis else None,
            "base_case": thesis.base_case if thesis else None,
            "bear_case": thesis.bear_case if thesis else None,
        } if thesis else None,
        "scenarios": [
            {
                "scenario_type": s.scenario_type,
                "target_price": _f(s.target_price),
                "expected_cagr": s.expected_cagr,
                "probability": s.probability,
                "exit_pe": s.exit_pe,
                "description": s.description,
                "key_triggers": s.key_triggers,
            }
            for s in scenarios
        ],
        "quarterly_history": [
            {
                "fiscal_year": q["fiscal_year"],
                "quarter": q["quarter"],
                "target": _serialize_target(q["target"]),
                "actual": _serialize_actual(q["actual"]),
                "comparison": _serialize_comparison(q["comparison"]),
            }
            for q in quarters
        ],
        "recent_alerts": [
            {
                "id": str(a.id),
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "description": a.description,
                "is_read": a.is_read,
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            }
            for a in alerts
        ],
        "latest_technical": {
            "close_price": _f(tech.close_price),
            "sma_50": tech.sma_50,
            "sma_200": tech.sma_200,
            "rsi_14": tech.rsi_14,
            "trend": tech.trend,
            "technical_score": tech.technical_score,
            "above_sma_50": tech.above_sma_50,
            "above_sma_200": tech.above_sma_200,
            "pct_from_52w_high": tech.pct_from_52w_high,
        } if tech else None,
        "promoter_history": [
            {
                "fiscal_year": p.fiscal_year,
                "quarter": p.quarter,
                "promoter_holding_pct": p.promoter_holding_pct,
                "promoter_pledged_pct": p.promoter_pledged_pct,
                "promoter_change_pct": p.promoter_change_pct,
                "pledged_change_pct": p.pledged_change_pct,
                "signal": p.signal,
            }
            for p in promoters
        ],
    }


# ─── Set quarterly target ─────────────────────────────────────────────────────
@router.post("/{isin}/target", response_model=JobResultOut)
async def set_target(
    isin: str,
    body: SetTargetIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await set_quarterly_target(
        db, isin,
        fiscal_year=body.fiscal_year,
        quarter=body.quarter,
        expected_revenue_cr=body.expected_revenue_cr,
        expected_ebitda_cr=body.expected_ebitda_cr,
        expected_ebitda_margin=body.expected_ebitda_margin,
        expected_pat_cr=body.expected_pat_cr,
        expected_order_book_cr=body.expected_order_book_cr,
        expected_capex_cr=body.expected_capex_cr,
        mgmt_revenue_guidance=body.mgmt_revenue_guidance,
        mgmt_margin_guidance=body.mgmt_margin_guidance,
        guidance_notes=body.guidance_notes,
        confidence=body.confidence,
    )
    return {"status": "ok", "message": f"Target set for {isin} {body.quarter} FY{body.fiscal_year}"}


# ─── Ingest quarterly actual ──────────────────────────────────────────────────
@router.post("/{isin}/actual")
async def ingest_actual(
    isin: str,
    body: IngestActualIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ingest quarterly actual results.
    Automatically computes GREEN/YELLOW/RED signals and generates alerts.
    """
    result = await ingest_quarterly_actual(
        db, isin,
        fiscal_year=body.fiscal_year,
        quarter=body.quarter,
        result_date=body.result_date,
        revenue_cr=body.revenue_cr,
        ebitda_cr=body.ebitda_cr,
        ebitda_margin=body.ebitda_margin,
        pat_cr=body.pat_cr,
        eps=body.eps,
        revenue_yoy_pct=body.revenue_yoy_pct,
        pat_yoy_pct=body.pat_yoy_pct,
        order_book_cr=body.order_book_cr,
        capex_cr=body.capex_cr,
        debt_cr=body.debt_cr,
        cash_cr=body.cash_cr,
        promoter_holding_pct=body.promoter_holding_pct,
        promoter_pledged_pct=body.promoter_pledged_pct,
        fii_holding_pct=body.fii_holding_pct,
        mgmt_guidance_revenue=body.mgmt_guidance_revenue,
        mgmt_guidance_margin=body.mgmt_guidance_margin,
        mgmt_commentary=body.mgmt_commentary,
        guidance_revised=body.guidance_revised,
        guidance_revision_pct=body.guidance_revision_pct,
    )
    await recalculate_scores(db, isin)
    return result


# ─── Thesis ───────────────────────────────────────────────────────────────────
@router.get("/{isin}/thesis")
async def get_thesis(isin: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(MasterThesis)
        .where(MasterThesis.isin == isin, MasterThesis.is_current.is_(True))
        .limit(1)
    )
    thesis = result.scalar_one_or_none()
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis found")
    return {
        "isin": isin, "version": thesis.version,
        "thesis_text": thesis.thesis_text,
        "growth_drivers": thesis.growth_drivers,
        "key_risks": thesis.key_risks,
        "moat": thesis.moat,
        "management_quality": thesis.management_quality,
        "expected_revenue_cagr_3y": thesis.expected_revenue_cagr_3y,
        "expected_ebitda_margin": thesis.expected_ebitda_margin,
        "expected_pat_cagr_3y": thesis.expected_pat_cagr_3y,
        "expected_pe_entry": thesis.expected_pe_entry,
        "expected_pe_exit": thesis.expected_pe_exit,
        "bull_case": thesis.bull_case, "base_case": thesis.base_case, "bear_case": thesis.bear_case,
        "authored_at": thesis.authored_at.isoformat() if thesis.authored_at else None,
    }


@router.put("/{isin}/thesis", response_model=JobResultOut)
async def update_thesis(
    isin: str,
    body: UpdateThesisIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Invalidate current thesis
    await db.execute(
        update(MasterThesis)
        .where(MasterThesis.isin == isin, MasterThesis.is_current.is_(True))
        .values(is_current=False)
    )
    # Get next version number
    result = await db.execute(
        select(MasterThesis.version)
        .where(MasterThesis.isin == isin)
        .order_by(MasterThesis.version.desc()).limit(1)
    )
    last_v = result.scalar() or 0
    db.add(MasterThesis(
        isin=isin,
        version=last_v + 1,
        is_current=True,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    ))
    await db.commit()
    return {"status": "ok", "message": f"Thesis v{last_v+1} saved for {isin}"}


# ─── Quarterly history ────────────────────────────────────────────────────────
@router.get("/{isin}/history")
async def quarterly_history(isin: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    from .service import _get_quarterly_history
    quarters = await _get_quarterly_history(db, isin, limit=12)
    return [
        {
            "fiscal_year": q["fiscal_year"],
            "quarter": q["quarter"],
            "target": _serialize_target(q["target"]),
            "actual": _serialize_actual(q["actual"]),
            "comparison": _serialize_comparison(q["comparison"]),
        }
        for q in quarters
    ]


# ─── Technical history ────────────────────────────────────────────────────────
@router.get("/{isin}/technical")
async def technical_history(
    isin: str,
    limit: int = Query(30),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(TechnicalSnapshot)
        .where(TechnicalSnapshot.isin == isin)
        .order_by(TechnicalSnapshot.snapshot_date.desc())
        .limit(limit)
    )
    snaps = result.scalars().all()
    return [
        {
            "snapshot_date": s.snapshot_date.isoformat(),
            "close_price": float(s.close_price) if s.close_price else None,
            "sma_50": s.sma_50, "sma_200": s.sma_200,
            "rsi_14": s.rsi_14, "trend": s.trend,
            "technical_score": s.technical_score,
            "above_sma_50": s.above_sma_50, "above_sma_200": s.above_sma_200,
            "pct_from_52w_high": s.pct_from_52w_high,
        }
        for s in snaps
    ]


# ─── Company alerts ───────────────────────────────────────────────────────────
@router.get("/{isin}/alerts")
async def company_alerts(
    isin: str,
    unread_only: bool = Query(False),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    alerts = await get_alerts(db, isin=isin, unread_only=unread_only, limit=limit)
    return [
        {
            "id": str(a.id), "alert_type": a.alert_type, "severity": a.severity,
            "title": a.title, "description": a.description, "data_snapshot": a.data_snapshot,
            "is_read": a.is_read, "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        }
        for a in alerts
    ]


# ─── Admin ────────────────────────────────────────────────────────────────────
@router.post("/admin/seed-from-research", response_model=JobResultOut)
async def admin_seed(isins: list[str] | None = None) -> dict:
    task = seed_from_research_task.apply_async(kwargs={"isins": isins}, queue="tracker_normal")
    return {"status": "queued", "task_id": task.id}


@router.post("/admin/recalculate-scores", response_model=JobResultOut)
async def admin_recalc() -> dict:
    task = recalculate_all_scores_task.apply_async(queue="tracker_normal")
    return {"status": "queued", "task_id": task.id}


@router.post("/admin/auto-set-targets", response_model=JobResultOut)
async def admin_auto_targets(fiscal_year: int, quarter: str) -> dict:
    task = auto_set_targets_task.apply_async(
        kwargs={"fiscal_year": fiscal_year, "quarter": quarter},
        queue="tracker_normal",
    )
    return {"status": "queued", "task_id": task.id, "message": f"Auto-targeting {quarter} FY{fiscal_year}"}


# ─── Serialization helpers ────────────────────────────────────────────────────
def _f(v): return float(v) if v is not None else None


def _serialize_target(t: QuarterlyTarget | None) -> dict | None:
    if not t: return None
    return {
        "expected_revenue_cr": _f(t.expected_revenue_cr),
        "expected_ebitda_cr": _f(t.expected_ebitda_cr),
        "expected_ebitda_margin": t.expected_ebitda_margin,
        "expected_pat_cr": _f(t.expected_pat_cr),
        "expected_order_book_cr": _f(t.expected_order_book_cr),
        "expected_capex_cr": _f(t.expected_capex_cr),
        "mgmt_revenue_guidance": _f(t.mgmt_revenue_guidance),
        "mgmt_margin_guidance": t.mgmt_margin_guidance,
        "guidance_notes": t.guidance_notes,
        "confidence": t.confidence,
    }


def _serialize_actual(a: QuarterlyActual | None) -> dict | None:
    if not a: return None
    return {
        "result_date": a.result_date.isoformat() if a.result_date else None,
        "revenue_cr": _f(a.revenue_cr),
        "ebitda_cr": _f(a.ebitda_cr),
        "ebitda_margin": a.ebitda_margin,
        "pat_cr": _f(a.pat_cr),
        "eps": a.eps,
        "revenue_yoy_pct": a.revenue_yoy_pct,
        "pat_yoy_pct": a.pat_yoy_pct,
        "order_book_cr": _f(a.order_book_cr),
        "capex_cr": _f(a.capex_cr),
        "debt_cr": _f(a.debt_cr),
        "promoter_holding_pct": a.promoter_holding_pct,
        "promoter_pledged_pct": a.promoter_pledged_pct,
        "mgmt_commentary": a.mgmt_commentary,
        "guidance_revised": a.guidance_revised,
        "guidance_revision_pct": a.guidance_revision_pct,
    }


def _serialize_comparison(c: ExpectationComparison | None) -> dict | None:
    if not c: return None
    return {
        "revenue_signal": c.revenue_signal,
        "ebitda_signal": c.ebitda_signal,
        "margin_signal": c.margin_signal,
        "pat_signal": c.pat_signal,
        "order_book_signal": c.order_book_signal,
        "capex_signal": c.capex_signal,
        "guidance_signal": c.guidance_signal,
        "promoter_signal": c.promoter_signal,
        "overall_signal": c.overall_signal,
        "revenue_beat_pct": c.revenue_beat_pct,
        "ebitda_beat_pct": c.ebitda_beat_pct,
        "margin_delta_bps": c.margin_delta_bps,
        "pat_beat_pct": c.pat_beat_pct,
        "beat_count": c.beat_count,
        "miss_count": c.miss_count,
        "verdict": c.verdict,
        "ai_summary": c.ai_summary,
    }
