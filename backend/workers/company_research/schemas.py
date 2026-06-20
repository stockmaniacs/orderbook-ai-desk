"""
Pydantic v2 schemas — Company Research Worker.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─── Company ──────────────────────────────────────────────────────────────────
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    symbol_nse: str | None
    symbol_bse: str | None
    company_name: str
    short_name: str | None
    sector: str | None
    industry: str | None
    market_cap_cr: float | None
    market_cap_cat: str | None
    website_url: str | None
    research_priority: int | None
    last_research_date: datetime | None
    next_research_due: datetime | None
    research_status: str | None
    created_at: datetime | None


class CompanyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    symbol_nse: str | None
    company_name: str
    sector: str | None
    market_cap_cr: float | None
    market_cap_cat: str | None
    research_status: str | None
    last_research_date: datetime | None


# ─── Research Document ────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    isin: str
    doc_type: str
    title: str | None
    source: str | None
    source_url: str | None
    fiscal_year: int | None
    quarter: str | None
    published_date: date | None
    page_count: int | None
    text_extracted: bool
    ai_extracted: bool
    created_at: datetime | None


# ─── Research Field ───────────────────────────────────────────────────────────
class ResearchFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    field_name: str
    field_category: str | None
    value_text: str | None
    value_json: Any | None
    source_types: list[str] | None
    primary_source: str | None
    as_of_date: date | None
    fiscal_period: str | None
    confidence: float | None
    is_stale: bool
    version: int
    last_updated: datetime | None
    update_reason: str | None


class ResearchFieldHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    value_text: str | None
    confidence: float | None
    update_reason: str | None
    recorded_at: datetime | None


# ─── SWOT item ────────────────────────────────────────────────────────────────
class SwotItem(BaseModel):
    point: str
    evidence: str | None = None
    confidence: float = 0.5


# ─── Investment Thesis ────────────────────────────────────────────────────────
class InvestmentThesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    company_name: str | None
    one_liner: str | None
    thesis_text: str | None
    strengths: list[SwotItem] | None
    weaknesses: list[SwotItem] | None
    opportunities: list[SwotItem] | None
    threats: list[SwotItem] | None
    bull_case: str | None
    bull_cagr_pct: float | None
    bull_target_cr: float | None
    base_case: str | None
    base_cagr_pct: float | None
    base_target_cr: float | None
    bear_case: str | None
    bear_cagr_pct: float | None
    bear_target_cr: float | None
    bull_probability: float | None
    base_probability: float | None
    bear_probability: float | None
    current_price: float | None
    fair_value_low: float | None
    fair_value_mid: float | None
    fair_value_high: float | None
    target_price_12m: float | None
    expected_cagr_3y: float | None
    rating: str | None
    confidence_score: float | None
    version: int
    sections_updated: list[str] | None
    last_updated: datetime | None
    update_trigger: str | None


# ─── Company Financials ───────────────────────────────────────────────────────
class FinancialsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    period_type: str
    fiscal_year: int
    quarter: str | None
    period_end_date: date | None
    is_consolidated: bool
    revenue: float | None
    gross_profit: float | None
    ebitda: float | None
    ebitda_margin: float | None
    pat: float | None
    pat_margin: float | None
    eps: float | None
    total_debt: float | None
    net_debt: float | None
    cash: float | None
    total_equity: float | None
    cfo: float | None
    capex: float | None
    free_cash_flow: float | None
    roe: float | None
    roce: float | None
    debt_equity: float | None
    interest_coverage: float | None


# ─── Research Report ──────────────────────────────────────────────────────────
class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    isin: str
    company_name: str | None
    report_version: int
    is_current: bool
    markdown_content: str
    trigger: str | None
    sections_changed: list[str] | None
    diff_summary: str | None
    word_count: int | None
    confidence_score: float | None
    generated_at: datetime | None


class ReportMeta(BaseModel):
    """Lightweight report listing (no markdown body)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    isin: str
    report_version: int
    is_current: bool
    trigger: str | None
    sections_changed: list[str] | None
    diff_summary: str | None
    word_count: int | None
    confidence_score: float | None
    generated_at: datetime | None


# ─── Full Research Dashboard ──────────────────────────────────────────────────
class ResearchDashboard(BaseModel):
    """Single-company research dashboard."""
    company: CompanyOut
    thesis: InvestmentThesisOut | None
    fields: list[ResearchFieldOut]
    latest_report: ReportOut | None
    recent_docs: list[DocumentOut]
    latest_financials: FinancialsOut | None


# ─── Universe / Leaderboard ───────────────────────────────────────────────────
class UniverseItem(BaseModel):
    """One row in the research universe list."""
    model_config = ConfigDict(from_attributes=True)

    isin: str
    symbol_nse: str | None
    company_name: str
    sector: str | None
    market_cap_cr: float | None
    market_cap_cat: str | None
    rating: str | None
    confidence_score: float | None
    expected_cagr_3y: float | None
    target_price_12m: float | None
    current_price: float | None
    upside_pct: float | None
    last_research_date: datetime | None


# ─── Task trigger ─────────────────────────────────────────────────────────────
class TriggerResearchIn(BaseModel):
    isin: str
    priority: int = Field(default=1, ge=1, le=5)
    force_full_refresh: bool = False
