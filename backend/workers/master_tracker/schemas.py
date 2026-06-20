"""
Pydantic v2 schemas — Master Tracker Worker.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrackedStockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    symbol_nse: str | None = None
    company_name: str
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    market_cap_cat: str | None = None
    cmp: float | None = None
    price_updated_at: datetime | None = None

    thesis_summary: str | None = None
    thesis_quality: str = "YELLOW"
    expected_cagr_3y: float | None = None
    fair_value: float | None = None
    target_price_12m: float | None = None
    upside_pct: float | None = None

    rating: str = "NEUTRAL"
    risk_reward_score: float | None = None
    conviction_score: float | None = None

    technical_trend: str | None = None
    technical_score: float | None = None

    tracking_status: str = "ACTIVE"
    tracking_priority: int = 2
    overall_signal: str = "YELLOW"
    consecutive_red: int = 0
    tags: list[str] | None = None


class MasterThesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    version: int
    is_current: bool
    thesis_text: str | None = None
    growth_drivers: list[str] | None = None
    key_risks: list[str] | None = None
    moat: str | None = None
    management_quality: str | None = None
    expected_revenue_cagr_3y: float | None = None
    expected_ebitda_margin: float | None = None
    expected_pat_cagr_3y: float | None = None
    expected_pe_entry: float | None = None
    expected_pe_exit: float | None = None
    expected_ev_ebitda: float | None = None
    bull_case: dict | None = None
    base_case: dict | None = None
    bear_case: dict | None = None
    authored_at: datetime | None = None


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_type: str
    target_price: float | None = None
    target_date: date | None = None
    expected_cagr: float | None = None
    probability: float | None = None
    revenue_cagr: float | None = None
    ebitda_margin: float | None = None
    exit_pe: float | None = None
    description: str | None = None
    key_triggers: list[str] | None = None
    key_risks: list[str] | None = None


class QuarterlyTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    fiscal_year: int
    quarter: str
    expected_revenue_cr: float | None = None
    expected_ebitda_cr: float | None = None
    expected_ebitda_margin: float | None = None
    expected_pat_cr: float | None = None
    expected_order_book_cr: float | None = None
    expected_capex_cr: float | None = None
    mgmt_revenue_guidance: float | None = None
    mgmt_margin_guidance: float | None = None
    guidance_notes: str | None = None
    confidence: float = 0.7


class QuarterlyActualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    fiscal_year: int
    quarter: str
    result_date: date | None = None
    revenue_cr: float | None = None
    ebitda_cr: float | None = None
    ebitda_margin: float | None = None
    pat_cr: float | None = None
    pat_margin: float | None = None
    eps: float | None = None
    revenue_yoy_pct: float | None = None
    pat_yoy_pct: float | None = None
    order_book_cr: float | None = None
    capex_cr: float | None = None
    debt_cr: float | None = None
    promoter_holding_pct: float | None = None
    promoter_pledged_pct: float | None = None
    mgmt_commentary: str | None = None
    guidance_revised: bool = False
    guidance_revision_pct: float | None = None


class ComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    fiscal_year: int
    quarter: str

    revenue_signal: str = "NA"
    ebitda_signal: str = "NA"
    margin_signal: str = "NA"
    pat_signal: str = "NA"
    order_book_signal: str = "NA"
    capex_signal: str = "NA"
    guidance_signal: str = "NA"
    promoter_signal: str = "NA"
    overall_signal: str = "NA"

    revenue_beat_pct: float | None = None
    ebitda_beat_pct: float | None = None
    margin_delta_bps: float | None = None
    pat_beat_pct: float | None = None
    order_book_beat_pct: float | None = None

    beat_count: int = 0
    miss_count: int = 0
    in_line_count: int = 0
    verdict: str = "NA"
    ai_summary: str | None = None
    computed_at: datetime | None = None


class ThesisAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    company_name: str | None = None
    alert_type: str
    severity: str
    title: str | None = None
    description: str | None = None
    data_snapshot: dict | None = None
    fiscal_year: int | None = None
    quarter: str | None = None
    is_read: bool = False
    is_actioned: bool = False
    triggered_at: datetime


class TechnicalSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    snapshot_date: date
    close_price: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None
    golden_cross: bool | None = None
    death_cross: bool | None = None
    pct_from_52w_high: float | None = None
    pct_from_52w_low: float | None = None
    trend: str | None = None
    technical_score: float | None = None


class PromoterTrackingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    fiscal_year: int
    quarter: str
    promoter_holding_pct: float | None = None
    promoter_pledged_pct: float | None = None
    fii_pct: float | None = None
    dii_pct: float | None = None
    promoter_change_pct: float | None = None
    pledged_change_pct: float | None = None
    signal: str = "YELLOW"


# ── Compound views ────────────────────────────────────────────────────────────
class QuarterlyRow(BaseModel):
    """Target + Actual + Comparison for one quarter — used in drill-down."""
    fiscal_year: int
    quarter: str
    target: QuarterlyTargetOut | None = None
    actual: QuarterlyActualOut | None = None
    comparison: ComparisonOut | None = None


class CompanyDetailOut(BaseModel):
    stock: TrackedStockOut
    thesis: MasterThesisOut | None = None
    scenarios: list[ScenarioOut] = []
    quarterly_history: list[QuarterlyRow] = []
    recent_alerts: list[ThesisAlertOut] = []
    latest_technical: TechnicalSnapshotOut | None = None
    promoter_history: list[PromoterTrackingOut] = []


class DashboardItemOut(BaseModel):
    """Lightweight row for the master dashboard table."""
    isin: str
    symbol_nse: str | None = None
    company_name: str
    sector: str | None = None
    market_cap_cr: float | None = None
    market_cap_cat: str | None = None
    cmp: float | None = None
    target_price_12m: float | None = None
    upside_pct: float | None = None
    expected_cagr_3y: float | None = None
    rating: str = "NEUTRAL"
    overall_signal: str = "YELLOW"
    thesis_quality: str = "YELLOW"
    risk_reward_score: float | None = None
    conviction_score: float | None = None
    technical_trend: str | None = None
    technical_score: float | None = None
    consecutive_red: int = 0
    last_verdict: str | None = None          # latest quarter verdict
    last_quarter: str | None = None
    unread_alert_count: int = 0


class MasterDashboardOut(BaseModel):
    total: int
    items: list[DashboardItemOut]
    alert_count: int
    high_severity_count: int


# ── Input schemas ─────────────────────────────────────────────────────────────
class AddStockIn(BaseModel):
    isin: str
    symbol_nse: str | None = None
    company_name: str
    sector: str | None = None
    market_cap_cat: str | None = None
    tracking_priority: int = 2
    tags: list[str] | None = None


class SetTargetIn(BaseModel):
    fiscal_year: int
    quarter: str = Field(pattern="^Q[1-4]$")
    expected_revenue_cr: float | None = None
    expected_ebitda_cr: float | None = None
    expected_ebitda_margin: float | None = None
    expected_pat_cr: float | None = None
    expected_order_book_cr: float | None = None
    expected_capex_cr: float | None = None
    mgmt_revenue_guidance: float | None = None
    mgmt_margin_guidance: float | None = None
    guidance_notes: str | None = None
    confidence: float = Field(0.7, ge=0, le=1)


class IngestActualIn(BaseModel):
    fiscal_year: int
    quarter: str = Field(pattern="^Q[1-4]$")
    result_date: date | None = None
    revenue_cr: float | None = None
    ebitda_cr: float | None = None
    ebitda_margin: float | None = None
    pat_cr: float | None = None
    eps: float | None = None
    revenue_yoy_pct: float | None = None
    pat_yoy_pct: float | None = None
    order_book_cr: float | None = None
    capex_cr: float | None = None
    debt_cr: float | None = None
    cash_cr: float | None = None
    promoter_holding_pct: float | None = None
    promoter_pledged_pct: float | None = None
    fii_holding_pct: float | None = None
    mgmt_guidance_revenue: float | None = None
    mgmt_guidance_margin: float | None = None
    mgmt_commentary: str | None = None
    guidance_revised: bool = False
    guidance_revision_pct: float | None = None


class UpdateThesisIn(BaseModel):
    thesis_text: str | None = None
    growth_drivers: list[str] | None = None
    key_risks: list[str] | None = None
    moat: str | None = None
    management_quality: str | None = None
    expected_revenue_cagr_3y: float | None = None
    expected_ebitda_margin: float | None = None
    expected_pat_cagr_3y: float | None = None
    expected_pe_entry: float | None = None
    expected_pe_exit: float | None = None
    bull_case: dict | None = None
    base_case: dict | None = None
    bear_case: dict | None = None


class AlertMarkIn(BaseModel):
    is_read: bool | None = None
    is_actioned: bool | None = None


class JobResultOut(BaseModel):
    status: str
    task_id: str | None = None
    message: str | None = None
