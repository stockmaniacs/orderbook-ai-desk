"""
FastAPI router — Subcontract Opportunity Worker.

Prefix: /api/v1/subcontract

Endpoints:
  GET  /opportunities                 — paginated feed
  GET  /opportunities/{id}            — full detail with beneficiary table
  POST /opportunities/trigger         — manually trigger analysis for an order

  GET  /companies/{isin}/suppliers    — companies supplying TO this company
  GET  /companies/{isin}/customers    — companies this company supplies TO
  GET  /companies/{isin}/graph        — full graph neighbourhood
  POST /companies/{isin}/rebuild      — trigger supply-chain rebuild for this company

  GET  /themes                        — all sector themes
  GET  /graph/stats                   — graph-wide statistics
  GET  /graph/universe                — all nodes with degree/centrality

  POST /admin/rebuild-graph           — batch rebuild (all companies)
  POST /admin/refresh-metrics         — recompute degrees + centrality
  POST /outcomes/{opp_id}/{isin}      — record a prediction outcome
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from .schemas import (
    BeneficiaryOut,
    CompanyGraphOut,
    GraphStatsOut,
    GraphUniverseOut,
    JobResultOut,
    OpportunityListItem,
    ProcessCompanyIn,
    RebuildGraphIn,
    SectorThemeOut,
    SubcontractOpportunityOut,
    TriggerOpportunityIn,
)
from .service import (
    analyze_order_opportunity,
    get_company_graph,
    get_graph_stats,
    get_graph_universe,
    get_opportunities_feed,
    get_opportunity,
    process_company_supply_chain,
    record_prediction_outcome,
    rebuild_graph,
)
from .tasks import (
    analyze_order_opportunity_task,
    batch_graph_rebuild_task,
    process_company_supply_chain_task,
    refresh_graph_metrics_task,
)
from .models import SectorTheme
from .graph.traversal import find_suppliers, find_customers
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/subcontract", tags=["Subcontract Opportunity"])


# ─── Opportunity feed ─────────────────────────────────────────────────────────
@router.get("/opportunities", response_model=dict)
async def list_opportunities(
    theme: str | None = Query(None),
    prime_isin: str | None = Query(None),
    min_amount_cr: float | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_opportunities_feed(
        db,
        theme=theme,
        prime_isin=prime_isin,
        min_amount_cr=min_amount_cr,
        limit=limit,
        offset=offset,
    )


# ─── Opportunity detail ───────────────────────────────────────────────────────
@router.get("/opportunities/{opp_id}", response_model=dict)
async def get_opportunity_detail(
    opp_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await get_opportunity(db, str(opp_id))
    if not data:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opp = data["opportunity"]
    bens = data["beneficiaries"]

    return {
        "id": str(opp.id),
        "prime_contractor_isin": opp.prime_contractor_isin,
        "prime_contractor_name": opp.prime_contractor_name,
        "order_amount_cr": float(opp.order_amount_cr or 0),
        "order_customer": opp.order_customer,
        "order_sector": opp.order_sector,
        "order_description": opp.order_description,
        "announced_date": opp.announced_date.isoformat() if opp.announced_date else None,
        "theme": opp.theme,
        "sub_themes": opp.sub_themes,
        "estimated_subcontract_cr": float(opp.estimated_subcontract_cr or 0),
        "subcontract_ratio": opp.subcontract_ratio,
        "beneficiary_count": opp.beneficiary_count,
        "status": opp.status,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
        "beneficiaries": [
            {
                "rank": b.rank,
                "beneficiary_isin": b.beneficiary_isin,
                "beneficiary_name": b.beneficiary_name,
                "beneficiary_sector": b.beneficiary_sector,
                "beneficiary_mcap_cr": float(b.beneficiary_mcap_cr or 0),
                "relationship_type": b.relationship_type,
                "product_category": b.product_category,
                "supply_chain_hops": b.supply_chain_hops,
                "probability_score": b.probability_score,
                "revenue_impact_cr": float(b.revenue_impact_cr or 0),
                "revenue_impact_pct": b.revenue_impact_pct,
                "confidence_score": b.confidence_score,
                "overall_score": b.overall_score,
                "investment_action": b.investment_action,
                "rationale": b.rationale,
                "key_catalysts": b.key_catalysts,
                "key_risks": b.key_risks,
                "score_breakdown": b.score_breakdown,
                "relationship_path": b.relationship_path,
            }
            for b in bens
        ],
    }


# ─── Trigger opportunity analysis ─────────────────────────────────────────────
@router.post("/opportunities/trigger", response_model=JobResultOut)
async def trigger_opportunity_analysis(
    body: TriggerOpportunityIn,
    background: bool = Query(True, description="Run as Celery background task"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if background:
        task = analyze_order_opportunity_task.apply_async(
            kwargs={
                "prime_contractor_isin": body.prime_contractor_isin,
                "prime_contractor_name": body.prime_contractor_name,
                "order_amount_cr": body.order_amount_cr,
                "order_customer": body.order_customer,
                "order_sector": body.order_sector,
                "order_description": body.order_description,
                "announced_date": body.announced_date.isoformat() if body.announced_date else None,
                "order_announcement_id": body.order_announcement_id,
            },
            queue="subcontract_high",
        )
        return {"status": "queued", "task_id": task.id}
    else:
        # Synchronous for testing
        opp_id = await analyze_order_opportunity(
            db,
            prime_contractor_isin=body.prime_contractor_isin,
            prime_contractor_name=body.prime_contractor_name,
            order_amount_cr=body.order_amount_cr,
            order_customer=body.order_customer,
            order_sector=body.order_sector,
            order_description=body.order_description,
            announced_date=body.announced_date,
            order_announcement_id=body.order_announcement_id,
        )
        return {"status": "ok", "task_id": None, "message": f"Opportunity {opp_id} created"}


# ─── Company suppliers ────────────────────────────────────────────────────────
@router.get("/companies/{isin}/suppliers")
async def get_suppliers(
    isin: str,
    max_hops: int = Query(2, le=3),
    min_strength: float = Query(0.25),
    db: AsyncSession = Depends(get_db),
) -> dict:
    suppliers = await find_suppliers(db, isin, max_hops=max_hops, min_strength=min_strength)
    return {"isin": isin, "supplier_count": len(suppliers), "suppliers": suppliers}


# ─── Company customers ────────────────────────────────────────────────────────
@router.get("/companies/{isin}/customers")
async def get_company_customers(
    isin: str,
    min_strength: float = Query(0.2),
    db: AsyncSession = Depends(get_db),
) -> dict:
    customers = await find_customers(db, isin, min_strength=min_strength)
    return {"isin": isin, "customer_count": len(customers), "customers": customers}


# ─── Full company graph neighbourhood ────────────────────────────────────────
@router.get("/companies/{isin}/graph")
async def company_graph_view(
    isin: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_company_graph(db, isin)


# ─── Trigger graph rebuild for one company ───────────────────────────────────
@router.post("/companies/{isin}/rebuild", response_model=JobResultOut)
async def rebuild_company_graph(
    isin: str,
    doc_types: list[str] | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = process_company_supply_chain_task.apply_async(
        kwargs={"isin": isin, "doc_types": doc_types},
        queue="subcontract_normal",
    )
    return {"status": "queued", "task_id": task.id, "message": f"Graph rebuild queued for {isin}"}


# ─── Sector themes ────────────────────────────────────────────────────────────
@router.get("/themes")
async def list_themes(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(SectorTheme).order_by(SectorTheme.theme_name))
    themes = result.scalars().all()
    return [
        {
            "theme_name": t.theme_name,
            "description": t.description,
            "typical_subcontract_categories": t.typical_subcontract_categories,
            "typical_subcontract_ratio": t.typical_subcontract_ratio,
            "beneficiary_sectors": t.beneficiary_sectors,
        }
        for t in themes
    ]


# ─── Graph statistics ─────────────────────────────────────────────────────────
@router.get("/graph/stats")
async def graph_stats(db: AsyncSession = Depends(get_db)) -> dict:
    return await get_graph_stats(db)


# ─── Graph universe ───────────────────────────────────────────────────────────
@router.get("/graph/universe")
async def graph_universe(
    sector: str | None = Query(None),
    tier: int | None = Query(None),
    min_degree: int | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_graph_universe(db, sector=sector, tier=tier, min_degree=min_degree, limit=limit, offset=offset)


# ─── Admin: batch graph rebuild ───────────────────────────────────────────────
@router.post("/admin/rebuild-graph", response_model=JobResultOut)
async def admin_rebuild_graph(body: RebuildGraphIn) -> dict:
    task = batch_graph_rebuild_task.apply_async(
        kwargs={"isins": body.isins, "batch_size": body.batch_size},
        queue="subcontract_normal",
    )
    return {"status": "queued", "task_id": task.id, "message": "Full graph rebuild queued"}


# ─── Admin: refresh graph metrics ────────────────────────────────────────────
@router.post("/admin/refresh-metrics", response_model=JobResultOut)
async def admin_refresh_metrics() -> dict:
    task = refresh_graph_metrics_task.apply_async(queue="subcontract_normal")
    return {"status": "queued", "task_id": task.id}


# ─── Record prediction outcome ────────────────────────────────────────────────
@router.post("/outcomes/{opp_id}/{isin}", response_model=JobResultOut)
async def record_outcome(
    opp_id: UUID,
    isin: str,
    was_correct: bool = Query(...),
    actual_rev_impact_cr: float | None = Query(None),
    actual_rev_growth_pct: float | None = Query(None),
    outcome_source: str | None = Query(None),
    notes: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await record_prediction_outcome(
        db,
        opportunity_id=str(opp_id),
        beneficiary_isin=isin,
        was_correct=was_correct,
        actual_rev_impact_cr=actual_rev_impact_cr,
        actual_rev_growth_pct=actual_rev_growth_pct,
        outcome_source=outcome_source or "MANUAL",
        outcome_notes=notes,
    )
    return {"status": "ok", "message": "Outcome recorded"}
