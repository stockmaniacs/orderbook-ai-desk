"""
FastAPI Router — Company Research Worker.
Prefix: /api/v1/research
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Company, InvestmentThesis, ResearchDocument, ResearchField,
    ResearchFieldHistory, ResearchReport,
)
from .schemas import (
    CompanyListItem, CompanyOut, DocumentOut, FinancialsOut,
    InvestmentThesisOut, ReportMeta, ReportOut, ResearchDashboard,
    ResearchFieldHistoryItem, ResearchFieldOut, TriggerResearchIn, UniverseItem,
)
from .service import get_research_dashboard, get_universe
from .tasks import run_research_pipeline_task

router = APIRouter(prefix="/api/v1/research", tags=["Company Research"])


# Dependency — async DB session
async def get_db() -> AsyncSession:
    from database import async_session_factory
    async with async_session_factory() as session:
        yield session

DB = Annotated[AsyncSession, Depends(get_db)]


# ─── Universe ─────────────────────────────────────────────────────────────────

@router.get("/universe", response_model=list[UniverseItem])
async def list_universe(
    db: DB,
    sector: str | None = Query(None),
    rating: str | None = Query(None),
    min_confidence: float = Query(0, ge=0, le=100),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List all researched companies with ratings, target prices, and upside.
    Filter by sector, rating, or minimum confidence score.
    """
    rows = await get_universe(db, sector=sector, rating=rating,
                               min_confidence=min_confidence, limit=limit, offset=offset)
    return rows


@router.get("/universe/sectors", response_model=list[str])
async def list_sectors(db: DB):
    """List distinct sectors available in the research universe."""
    result = await db.execute(
        select(Company.sector).where(Company.is_active == True, Company.sector != None).distinct()
    )
    return sorted([r[0] for r in result.all()])


# ─── Company ──────────────────────────────────────────────────────────────────

@router.get("/{isin}", response_model=ResearchDashboard)
async def get_company_dashboard(isin: str, db: DB):
    """
    Full research dashboard for a company:
    company info + thesis + all extracted fields + latest report + recent docs.
    """
    data = await get_research_dashboard(db, isin)
    if not data:
        raise HTTPException(status_code=404, detail=f"Company {isin} not found")
    return data


@router.get("/{isin}/thesis", response_model=InvestmentThesisOut)
async def get_thesis(isin: str, db: DB):
    thesis = await db.scalar(
        select(InvestmentThesis).where(InvestmentThesis.isin == isin)
    )
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis yet for this company")
    return thesis


@router.get("/{isin}/fields", response_model=list[ResearchFieldOut])
async def get_fields(
    isin: str,
    db: DB,
    category: str | None = Query(None),
    stale_only: bool = Query(False),
):
    """All extracted research fields for a company."""
    q = select(ResearchField).where(ResearchField.isin == isin)
    if category:
        q = q.where(ResearchField.field_category == category)
    if stale_only:
        q = q.where(ResearchField.is_stale == True)
    result = await db.execute(q.order_by(ResearchField.field_category, ResearchField.field_name))
    return result.scalars().all()


@router.get("/{isin}/fields/{field_name}/history", response_model=list[ResearchFieldHistoryItem])
async def get_field_history(isin: str, field_name: str, db: DB):
    """Version history for a specific research field."""
    field = await db.scalar(
        select(ResearchField).where(ResearchField.isin == isin, ResearchField.field_name == field_name)
    )
    if not field:
        raise HTTPException(status_code=404, detail=f"Field {field_name} not found")
    result = await db.execute(
        select(ResearchFieldHistory)
        .where(ResearchFieldHistory.field_id == field.id)
        .order_by(ResearchFieldHistory.version.desc())
    )
    return result.scalars().all()


@router.get("/{isin}/documents", response_model=list[DocumentOut])
async def get_documents(
    isin: str,
    db: DB,
    doc_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """List all source documents fetched for a company."""
    q = select(ResearchDocument).where(ResearchDocument.isin == isin)
    if doc_type:
        q = q.where(ResearchDocument.doc_type == doc_type)
    q = q.order_by(ResearchDocument.published_date.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{isin}/reports", response_model=list[ReportMeta])
async def list_reports(isin: str, db: DB):
    """List all report versions (metadata only, no full markdown)."""
    result = await db.execute(
        select(ResearchReport)
        .where(ResearchReport.isin == isin)
        .order_by(ResearchReport.report_version.desc())
    )
    return result.scalars().all()


@router.get("/{isin}/reports/current", response_model=ReportOut)
async def get_current_report(isin: str, db: DB):
    """Get the latest current research report (full markdown)."""
    report = await db.scalar(
        select(ResearchReport)
        .where(ResearchReport.isin == isin, ResearchReport.is_current == True)
    )
    if not report:
        raise HTTPException(status_code=404, detail="No report generated yet")
    return report


@router.get("/{isin}/reports/{version}", response_model=ReportOut)
async def get_report_version(isin: str, version: int, db: DB):
    """Get a specific version of the research report."""
    report = await db.scalar(
        select(ResearchReport)
        .where(ResearchReport.isin == isin, ResearchReport.report_version == version)
    )
    if not report:
        raise HTTPException(status_code=404, detail=f"Report version {version} not found")
    return report


# ─── Admin / triggers ─────────────────────────────────────────────────────────

@router.post("/{isin}/trigger", status_code=202)
async def trigger_research(
    isin: str,
    db: DB,
    body: TriggerResearchIn | None = None,
):
    """
    Trigger an immediate research pipeline run for a company.
    Returns 202 Accepted — results available when pipeline completes (~2-10 min).
    """
    company = await db.scalar(select(Company).where(Company.isin == isin))
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {isin} not found")

    force_full = body.force_full_refresh if body else False
    task = run_research_pipeline_task.apply_async(
        args=[isin],
        kwargs={"force_full": force_full},
        priority=1,
    )
    return {"task_id": task.id, "status": "queued", "isin": isin}


@router.post("/admin/seed-universe", status_code=202)
async def seed_universe():
    """Admin: seed company universe from instruments_master table."""
    from .tasks import seed_universe_task
    task = seed_universe_task.apply_async()
    return {"task_id": task.id, "status": "queued"}


@router.post("/admin/mark-stale", status_code=202)
async def mark_stale(stale_months: int = Query(6, ge=1, le=24)):
    """Admin: mark fields older than N months as stale."""
    from .tasks import mark_stale_fields_task
    task = mark_stale_fields_task.apply_async(args=[stale_months])
    return {"task_id": task.id, "status": "queued"}
