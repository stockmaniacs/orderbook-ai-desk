"""
Order Tracking Worker — Pydantic v2 Schemas
Request/response models for all API endpoints.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# OrderAnnouncement
# ---------------------------------------------------------------------------
class OrderAnnouncementCreate(BaseModel):
    source: str
    source_id: str
    source_url: Optional[str] = None
    isin: str
    company_name: str
    sector: Optional[str] = None
    customer_name: Optional[str] = None
    order_amount_cr: Optional[float] = None
    order_amount_raw: Optional[str] = None
    order_currency: str = "INR"
    order_type: Optional[str] = None
    project_description: Optional[str] = None
    announced_date: date
    execution_start: Optional[date] = None
    execution_end: Optional[date] = None
    duration_months: Optional[int] = None
    sector_category: Optional[str] = None
    project_type: Optional[str] = None
    is_repeat_order: bool = False
    raw_text: Optional[str] = None
    content_hash: str


class OrderAnnouncementOut(ORMBase):
    id: UUID
    source: str
    source_id: str
    source_url: Optional[str]
    isin: str
    company_name: str
    symbol_nse: Optional[str]
    symbol_bse: Optional[str]
    sector: Optional[str]
    customer_name: Optional[str]
    order_amount_cr: Optional[float]
    order_amount_raw: Optional[str]
    order_currency: str
    order_type: Optional[str]
    project_description: Optional[str]
    announced_date: date
    execution_start: Optional[date]
    execution_end: Optional[date]
    duration_months: Optional[int]
    sector_category: Optional[str]
    project_type: Optional[str]
    is_repeat_order: bool
    fiscal_year: Optional[int]
    quarter: Optional[str]
    extraction_confidence: Optional[float]
    processing_status: str
    created_at: datetime


class OrderAnnouncementList(BaseModel):
    items: list[OrderAnnouncementOut]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# OrderBookSnapshot
# ---------------------------------------------------------------------------
class SnapshotPoint(ORMBase):
    quarter: str
    fiscal_year: int
    quarter_num: int
    snapshot_date: date
    opening_order_book_cr: Optional[float]
    new_orders_cr: Optional[float]
    revenue_executed_cr: Optional[float]
    closing_order_book_cr: Optional[float]
    order_count: int
    domestic_orders_cr: Optional[float]
    export_orders_cr: Optional[float]
    quarterly_revenue_cr: Optional[float]
    annual_revenue_ttm_cr: Optional[float]
    is_estimated: bool


class OrderBookHistory(BaseModel):
    isin: str
    company_name: str
    snapshots: list[SnapshotPoint]


# ---------------------------------------------------------------------------
# OrderBookMetrics
# ---------------------------------------------------------------------------
class ScenarioAssumptions(BaseModel):
    quarterly_inflow_growth_pct: float
    win_rate_assumption: str
    key_driver: str


class Scenarios(BaseModel):
    bull: ScenarioAssumptions
    base: ScenarioAssumptions
    bear: ScenarioAssumptions


class OrderBookMetricsOut(ORMBase):
    isin: str
    company_name: Optional[str]
    current_order_book_cr: Optional[float]
    last_order_date: Optional[date]
    total_orders_count: int
    ttm_orders_won_cr: Optional[float]

    # Growth
    order_inflow_growth_yoy_pct: Optional[float]
    order_book_growth_yoy_pct: Optional[float]
    order_book_cagr_3y: Optional[float]
    order_book_cagr_5y: Optional[float]

    # Ratios
    order_book_to_sales: Optional[float]
    bill_to_book_ratio: Optional[float]
    order_to_sales_trend: Optional[str]

    # Acceleration
    order_acceleration_score: Optional[float]
    order_momentum: Optional[str]

    # Scenarios
    bull_case_ob_cr: Optional[float]
    base_case_ob_cr: Optional[float]
    bear_case_ob_cr: Optional[float]
    scenario_horizon_quarters: int
    scenario_assumptions: Optional[dict[str, Any]]

    # Mix
    domestic_pct: Optional[float]
    export_pct: Optional[float]
    sector_breakdown: Optional[dict[str, Any]]
    customer_concentration: Optional[dict[str, Any]]

    updated_at: datetime


# ---------------------------------------------------------------------------
# AI Summary
# ---------------------------------------------------------------------------
class RiskFactor(BaseModel):
    risk: str
    severity: str  # HIGH | MEDIUM | LOW


class PositiveSignal(BaseModel):
    signal: str
    impact: str  # HIGH | MEDIUM | LOW


class OrderAISummaryOut(ORMBase):
    id: UUID
    isin: str
    generated_at: datetime
    trend: Optional[str]
    trend_confidence: Optional[float]
    executive_summary: Optional[str]
    pipeline_analysis: Optional[str]
    customer_concentration_note: Optional[str]
    geographic_mix_note: Optional[str]
    risk_factors: Optional[list[dict[str, Any]]]
    positive_signals: Optional[list[dict[str, Any]]]
    key_customers: Optional[list[dict[str, Any]]]
    bull_narrative: Optional[str]
    base_narrative: Optional[str]
    bear_narrative: Optional[str]
    ai_verdict: Optional[str]
    model_version: Optional[str]


# ---------------------------------------------------------------------------
# Compound response for the stock detail page
# ---------------------------------------------------------------------------
class OrderTrackingDashboard(BaseModel):
    isin: str
    company_name: str
    sector: Optional[str]
    metrics: Optional[OrderBookMetricsOut]
    history: OrderBookHistory
    recent_orders: list[OrderAnnouncementOut]
    ai_summary: Optional[OrderAISummaryOut]


# ---------------------------------------------------------------------------
# Chart data schemas (pre-aggregated for frontend)
# ---------------------------------------------------------------------------
class QuarterlyChartPoint(BaseModel):
    quarter: str
    order_book_cr: Optional[float]
    new_orders_cr: Optional[float]
    executed_cr: Optional[float]
    ob_to_sales: Optional[float]


class YoYChartPoint(BaseModel):
    fiscal_year: int
    ttm_orders_cr: Optional[float]
    yoy_growth_pct: Optional[float]


class RollingChartPoint(BaseModel):
    date: str          # ISO date string
    rolling_4q_cr: Optional[float]   # 4-quarter rolling order inflows


class ChartsData(BaseModel):
    quarterly: list[QuarterlyChartPoint]
    yoy_growth: list[YoYChartPoint]
    rolling: list[RollingChartPoint]


# ---------------------------------------------------------------------------
# Search / filter params
# ---------------------------------------------------------------------------
class OrderSearchParams(BaseModel):
    isin: Optional[str] = None
    sector: Optional[str] = None
    order_type: Optional[str] = None  # DOMESTIC | EXPORT | MIXED
    min_amount_cr: Optional[float] = None
    max_amount_cr: Optional[float] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    customer_name: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# Manual order entry (for orders not on exchanges)
# ---------------------------------------------------------------------------
class ManualOrderCreate(BaseModel):
    isin: str
    company_name: str
    customer_name: Optional[str] = None
    order_amount_cr: float
    order_type: str = "DOMESTIC"
    project_description: Optional[str] = None
    announced_date: date
    execution_start: Optional[date] = None
    execution_end: Optional[date] = None
    sector_category: Optional[str] = None
    project_type: Optional[str] = None
    notes: Optional[str] = None
