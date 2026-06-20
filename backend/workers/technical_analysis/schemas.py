"""
Pydantic v2 schemas — Technical Analysis AI Worker.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TechnicalProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    symbol_nse: str | None = None
    company_name: str
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    market_cap_cat: str | None = None

    trend_score: float | None = None
    rs_score: float | None = None
    momentum_score: float | None = None
    volume_score: float | None = None
    pattern_score: float | None = None
    technical_score: float | None = None
    conviction_score: float | None = None

    rs_rating: int | None = None
    sector_rank: int | None = None
    industry_rank: int | None = None
    market_leader_rank: int | None = None

    classification: str = "WATCHLIST"
    signal: str = "HOLD"
    stage: int | None = None
    minervini_count: int = 0

    cmp: float | None = None
    pivot_price: float | None = None
    entry_price: float | None = None
    ideal_buy_zone_lo: float | None = None
    ideal_buy_zone_hi: float | None = None
    breakout_level: float | None = None
    stop_loss: float | None = None
    atr_stop: float | None = None
    trailing_stop: float | None = None
    target_price: float | None = None
    expected_upside_pct: float | None = None
    risk_reward_ratio: float | None = None

    atr_14: float | None = None
    atr_pct: float | None = None
    volatility_20d: float | None = None
    risk_score: float | None = None
    position_size_pct: float | None = None
    max_portfolio_alloc: float | None = None

    active_pattern: str | None = None
    pattern_maturity: float | None = None
    scores_updated_at: datetime | None = None
    price_date: date | None = None


class DailySnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    snap_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    delivery_pct: float | None = None

    sma_50: float | None = None
    sma_150: float | None = None
    sma_200: float | None = None
    above_sma_50: bool | None = None
    above_sma_150: bool | None = None
    above_sma_200: bool | None = None

    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_52w_high: float | None = None
    pct_from_52w_low: float | None = None
    new_52w_high: bool = False

    rsi_14: float | None = None
    rsi_weekly: float | None = None
    adx_14: float | None = None
    macd: float | None = None
    macd_hist: float | None = None
    macd_hist_expanding: bool | None = None

    vol_ratio: float | None = None
    up_vol_ratio: float | None = None
    is_pocket_pivot: bool = False
    is_accumulation_day: bool = False
    is_distribution_day: bool = False
    distribution_days_20: int = 0
    tight_action_5d: bool = False

    atr_14: float | None = None
    technical_score: float | None = None


class RelativeStrengthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    rs_date: date
    rs_vs_nifty500_1m: float | None = None
    rs_vs_nifty500_3m: float | None = None
    rs_vs_nifty500_6m: float | None = None
    rs_vs_nifty500_12m: float | None = None
    rs_vs_sector_1m: float | None = None
    rs_vs_sector_3m: float | None = None
    rs_rating: int | None = None
    rs_trend: str | None = None
    rs_breakout: bool = False
    rs_new_high: bool = False
    sector_rs_rank: int | None = None


class PatternOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    pattern_type: str
    status: str
    detected_date: date
    breakout_date: date | None = None
    depth_pct: float | None = None
    duration_days: int | None = None
    tight_pct: float | None = None
    contractions: int | None = None
    pivot_price: float | None = None
    buy_zone_lo: float | None = None
    buy_zone_hi: float | None = None
    pattern_stop: float | None = None
    pattern_target: float | None = None
    quality_score: float | None = None
    pattern_data: dict | None = None


class BreakoutLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    calc_date: date
    cmp: float | None = None
    entry_price: float | None = None
    ideal_buy_zone_lo: float | None = None
    ideal_buy_zone_hi: float | None = None
    breakout_level: float | None = None
    pivot_price: float | None = None
    stop_loss: float | None = None
    atr_stop: float | None = None
    trailing_stop: float | None = None
    target_price: float | None = None
    expected_upside_pct: float | None = None
    risk_pct: float | None = None
    risk_reward_ratio: float | None = None
    position_size_pct: float | None = None
    max_portfolio_alloc: float | None = None


class TechnicalAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    company_name: str | None = None
    alert_date: date
    alert_type: str
    severity: str
    title: str | None = None
    description: str | None = None
    price_at_alert: float | None = None
    classification_at: str | None = None
    signal_at: str | None = None
    tech_score_at: float | None = None
    rs_rating_at: int | None = None
    is_read: bool = False
    is_actioned: bool = False
    triggered_at: datetime


class SignalHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    isin: str
    signal_date: date
    signal: str
    classification: str
    pattern_type: str | None = None
    technical_score: float | None = None
    rs_rating: int | None = None
    conviction_score: float | None = None
    price_at_signal: float | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    risk_reward_ratio: float | None = None
    return_7d: float | None = None
    return_30d: float | None = None
    return_60d: float | None = None
    return_90d: float | None = None
    hit_target: bool | None = None
    hit_stop: bool | None = None
    max_gain_pct: float | None = None
    max_loss_pct: float | None = None
    outcome: str | None = None


class MarketBreadthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    breadth_date: date
    total_stocks: int | None = None
    pct_above_sma_50: float | None = None
    pct_above_sma_150: float | None = None
    pct_above_sma_200: float | None = None
    new_highs: int | None = None
    new_lows: int | None = None
    nh_nl_ratio: float | None = None
    advances: int | None = None
    declines: int | None = None
    ad_ratio: float | None = None
    elite_leaders_count: int = 0
    strong_structure_count: int = 0
    top_sectors: dict | None = None
    market_regime: str | None = None


# ── Dashboard ─────────────────────────────────────────────────────────────────
class DashboardStockRow(BaseModel):
    """Lightweight row for the dashboard table."""
    isin: str
    symbol_nse: str | None = None
    company_name: str
    sector: str | None = None
    market_cap_cat: str | None = None

    technical_score: float | None = None
    conviction_score: float | None = None
    rs_rating: int | None = None
    trend_score: float | None = None
    momentum_score: float | None = None
    volume_score: float | None = None

    classification: str = "WATCHLIST"
    signal: str = "HOLD"
    stage: int | None = None
    minervini_count: int = 0
    active_pattern: str | None = None

    cmp: float | None = None
    target_price: float | None = None
    expected_upside_pct: float | None = None
    risk_reward_ratio: float | None = None
    position_size_pct: float | None = None

    sector_rank: int | None = None
    industry_rank: int | None = None
    market_leader_rank: int | None = None

    unread_alert_count: int = 0
    price_date: date | None = None


class TechnicalDashboardOut(BaseModel):
    total: int
    elite_leaders: int
    strong_structure: int
    emerging_leaders: int
    items: list[DashboardStockRow]
    market_breadth: MarketBreadthOut | None = None
    unread_alerts: int = 0


# ── Detail view ───────────────────────────────────────────────────────────────
class StockDetailOut(BaseModel):
    profile: TechnicalProfileOut
    latest_snapshot: DailySnapshotOut | None = None
    latest_rs: RelativeStrengthOut | None = None
    active_patterns: list[PatternOut] = []
    current_levels: BreakoutLevelOut | None = None
    recent_alerts: list[TechnicalAlertOut] = []
    signal_history: list[SignalHistoryOut] = []
    snapshot_history: list[DailySnapshotOut] = []   # last 60 days for charting
    minervini_criteria: list[bool] = []


# ── Input schemas ─────────────────────────────────────────────────────────────
class IngestSnapshotIn(BaseModel):
    isin: str
    snap_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    delivery_pct: float | None = None


class AddUniverseStockIn(BaseModel):
    isin: str
    symbol_nse: str | None = None
    symbol_bse: str | None = None
    company_name: str
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    market_cap_cat: str | None = None


class AlertMarkIn(BaseModel):
    is_read: bool | None = None
    is_actioned: bool | None = None


class ScanFilterIn(BaseModel):
    classification: str | None = None       # ELITE_LEADER etc.
    signal: str | None = None
    sector: str | None = None
    stage: int | None = None
    min_rs_rating: int | None = None        # e.g. 80
    min_tech_score: float | None = None
    has_pattern: bool | None = None
    sort_by: str = "conviction_score"       # conviction_score / rs_rating / technical_score / market_leader_rank
    limit: int = 50
    offset: int = 0


class JobResultOut(BaseModel):
    status: str
    task_id: str | None = None
    message: str | None = None
    count: int | None = None
