"""
Master Tracker Worker — SQLAlchemy models.

Tracks every stock's investment thesis, quarterly expectations vs actuals,
GREEN/YELLOW/RED signals, alerts, scenarios, and technical snapshots.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─── Tracked stocks universe ──────────────────────────────────────────────────
class TrackedStock(Base):
    """Master record for every stock being tracked."""
    __tablename__ = "mt_stocks"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin             = Column(String(12), unique=True, nullable=False)
    symbol_nse       = Column(String(20))
    company_name     = Column(String(255), nullable=False)
    sector           = Column(String(100))
    industry         = Column(String(100))
    market_cap_cr    = Column(Numeric(20, 2))
    market_cap_cat   = Column(String(10))   # LARGE / MID / SMALL / MICRO

    # Current price data
    cmp              = Column(Numeric(12, 2))   # Current market price
    price_updated_at = Column(DateTime(timezone=True))

    # Investment thesis (summary — full text in InvestmentThesis)
    thesis_summary   = Column(Text)
    thesis_quality   = Column(String(10), default="YELLOW")  # GREEN / YELLOW / RED
    thesis_updated_at= Column(DateTime(timezone=True))

    # Expected returns
    expected_cagr_3y = Column(Float)          # % annualised
    fair_value       = Column(Numeric(12, 2))
    target_price_12m = Column(Numeric(12, 2))
    upside_pct       = Column(Float)          # (target - cmp) / cmp * 100

    # Rating
    rating           = Column(String(20), default="NEUTRAL")  # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
    risk_reward_score= Column(Float)          # 0–10
    conviction_score = Column(Float)          # 0–100

    # Technical
    technical_trend  = Column(String(20))     # UPTREND / DOWNTREND / SIDEWAYS / REVERSAL
    technical_score  = Column(Float)          # 0–100

    # Tracking metadata
    tracking_status  = Column(String(20), default="ACTIVE")  # ACTIVE / WATCHLIST / EXITED
    tracking_priority= Column(SmallInteger, default=2)        # 1=high, 2=normal, 3=low
    added_date       = Column(Date, default=date.today)
    last_updated_at  = Column(DateTime(timezone=True))

    # Composite signal (overall health)
    overall_signal   = Column(String(10), default="YELLOW")  # GREEN / YELLOW / RED
    consecutive_red  = Column(SmallInteger, default=0)       # quarters in a row with RED
    tags             = Column(JSONB)                          # ["capex_cycle", "infra_theme", ...]

    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at       = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Investment thesis (full versioned text) ──────────────────────────────────
class MasterThesis(Base):
    """Full investment thesis for a tracked stock. One active at a time."""
    __tablename__ = "mt_thesis"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    version         = Column(Integer, nullable=False, default=1)
    is_current      = Column(Boolean, default=True)

    # Core thesis
    thesis_text     = Column(Text)              # Long-form narrative
    growth_drivers  = Column(JSONB)             # list of strings
    key_risks       = Column(JSONB)             # list of strings
    moat            = Column(Text)              # Competitive moat description
    management_quality = Column(String(20))     # EXCELLENT / GOOD / AVERAGE / POOR

    # Expectations (current view)
    expected_revenue_cagr_3y = Column(Float)
    expected_ebitda_margin   = Column(Float)    # target steady-state
    expected_pat_cagr_3y     = Column(Float)
    expected_pe_entry        = Column(Float)
    expected_pe_exit         = Column(Float)
    expected_ev_ebitda       = Column(Float)

    # Scenarios
    bull_case       = Column(JSONB)             # {description, target_price, cagr, probability}
    base_case       = Column(JSONB)
    bear_case       = Column(JSONB)

    authored_by     = Column(String(100), default="AI_SYSTEM")
    authored_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    invalidated_at  = Column(DateTime(timezone=True))


# ─── Quarterly expectations (set BEFORE results) ─────────────────────────────
class QuarterlyTarget(Base):
    """Expected numbers for an upcoming quarter — set by AI or analyst."""
    __tablename__ = "mt_quarterly_targets"
    __table_args__ = (
        UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_qt_period"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    fiscal_year     = Column(Integer, nullable=False)   # e.g. 2026
    quarter         = Column(String(3), nullable=False) # Q1 / Q2 / Q3 / Q4

    # P&L expectations
    expected_revenue_cr     = Column(Numeric(20, 2))
    expected_ebitda_cr      = Column(Numeric(20, 2))
    expected_ebitda_margin  = Column(Float)             # %
    expected_pat_cr         = Column(Numeric(20, 2))
    expected_pat_margin     = Column(Float)             # %

    # Operational expectations
    expected_order_book_cr  = Column(Numeric(20, 2))
    expected_order_inflow_cr= Column(Numeric(20, 2))
    expected_capex_cr       = Column(Numeric(20, 2))
    expected_debt_cr        = Column(Numeric(20, 2))

    # Guidance from previous quarter
    mgmt_revenue_guidance   = Column(Numeric(20, 2))   # ₹ Cr from concall
    mgmt_margin_guidance    = Column(Float)             # % from concall
    guidance_notes          = Column(Text)

    # Metadata
    set_by          = Column(String(50), default="AI_SYSTEM")
    set_at          = Column(DateTime(timezone=True), default=datetime.utcnow)
    confidence      = Column(Float, default=0.7)        # 0–1
    notes           = Column(Text)


# ─── Quarterly actuals (filled AFTER results) ─────────────────────────────────
class QuarterlyActual(Base):
    """Actual results for a completed quarter."""
    __tablename__ = "mt_quarterly_actuals"
    __table_args__ = (
        UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_qa_period"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    fiscal_year     = Column(Integer, nullable=False)
    quarter         = Column(String(3), nullable=False)
    result_date     = Column(Date)

    # P&L actuals
    revenue_cr      = Column(Numeric(20, 2))
    ebitda_cr       = Column(Numeric(20, 2))
    ebitda_margin   = Column(Float)
    pat_cr          = Column(Numeric(20, 2))
    pat_margin      = Column(Float)
    eps             = Column(Float)

    # YoY / QoQ growth
    revenue_yoy_pct = Column(Float)
    ebitda_yoy_pct  = Column(Float)
    pat_yoy_pct     = Column(Float)
    revenue_qoq_pct = Column(Float)

    # Operational actuals
    order_book_cr   = Column(Numeric(20, 2))
    order_inflow_cr = Column(Numeric(20, 2))
    capex_cr        = Column(Numeric(20, 2))
    debt_cr         = Column(Numeric(20, 2))
    cash_cr         = Column(Numeric(20, 2))

    # Shareholding
    promoter_holding_pct  = Column(Float)
    promoter_pledged_pct  = Column(Float)
    fii_holding_pct       = Column(Float)
    dii_holding_pct       = Column(Float)

    # Management commentary
    mgmt_guidance_revenue = Column(Numeric(20, 2))   # next quarter / FY guidance
    mgmt_guidance_margin  = Column(Float)
    mgmt_commentary       = Column(Text)              # AI-summarised concall key points
    guidance_revised      = Column(Boolean, default=False)
    guidance_revision_pct = Column(Float)             # + = upgrade, - = downgrade

    source          = Column(String(50), default="BSE_RESULT")
    ingested_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Expectation vs Actual comparison ────────────────────────────────────────
class ExpectationComparison(Base):
    """
    GREEN / YELLOW / RED signals per metric for a given quarter.
    Computed automatically when actuals are ingested.
    """
    __tablename__ = "mt_comparisons"
    __table_args__ = (
        UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_comp_period"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    fiscal_year     = Column(Integer, nullable=False)
    quarter         = Column(String(3), nullable=False)

    # Signal per metric (GREEN / YELLOW / RED / NA)
    revenue_signal      = Column(String(10), default="NA")
    ebitda_signal       = Column(String(10), default="NA")
    margin_signal       = Column(String(10), default="NA")
    pat_signal          = Column(String(10), default="NA")
    order_book_signal   = Column(String(10), default="NA")
    capex_signal        = Column(String(10), default="NA")
    guidance_signal     = Column(String(10), default="NA")
    promoter_signal     = Column(String(10), default="NA")
    overall_signal      = Column(String(10), default="NA")

    # Miss / beat magnitudes (actual - expected) / expected * 100
    revenue_beat_pct    = Column(Float)
    ebitda_beat_pct     = Column(Float)
    margin_delta_bps    = Column(Float)   # basis points: actual - expected margin * 100
    pat_beat_pct        = Column(Float)
    order_book_beat_pct = Column(Float)

    # Summary
    beat_count          = Column(SmallInteger, default=0)  # metrics that are GREEN
    miss_count          = Column(SmallInteger, default=0)  # metrics that are RED
    in_line_count       = Column(SmallInteger, default=0)  # metrics that are YELLOW
    verdict             = Column(String(30))               # STRONG_BEAT / BEAT / IN_LINE / MISS / STRONG_MISS

    ai_summary          = Column(Text)  # 2-3 sentence AI assessment

    computed_at         = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Thesis alerts ────────────────────────────────────────────────────────────
class ThesisAlert(Base):
    """
    Generated when thesis deteriorates or significant event occurs.
    """
    __tablename__ = "mt_alerts"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    company_name    = Column(String(255))

    alert_type      = Column(String(50), nullable=False)
    # THESIS_DETERIORATING | THESIS_IMPROVING | OUTPERFORMING
    # GUIDANCE_CUT | GUIDANCE_UPGRADE | MARGIN_COMPRESSION | MARGIN_EXPANSION
    # PROMOTER_PLEDGING | PROMOTER_BUY | ORDER_BOOK_DECLINE | ORDER_BOOK_SURGE
    # CONSECUTIVE_MISS | CONSECUTIVE_BEAT | VALUATION_STRETCHED | VALUATION_ATTRACTIVE
    # TECHNICAL_BREAKDOWN | TECHNICAL_BREAKOUT

    severity        = Column(String(10), default="MEDIUM")  # HIGH / MEDIUM / LOW
    title           = Column(String(255))
    description     = Column(Text)
    data_snapshot   = Column(JSONB)   # relevant numbers that triggered the alert
    fiscal_year     = Column(Integer)
    quarter         = Column(String(3))

    is_read         = Column(Boolean, default=False)
    is_actioned     = Column(Boolean, default=False)

    triggered_at    = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Bull / Base / Bear scenarios ─────────────────────────────────────────────
class StockScenario(Base):
    """Price scenarios with explicit assumptions."""
    __tablename__ = "mt_scenarios"
    __table_args__ = (
        UniqueConstraint("isin", "scenario_type", "version", name="uq_scenario"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    scenario_type   = Column(String(10), nullable=False)  # BULL / BASE / BEAR
    version         = Column(Integer, default=1)
    is_current      = Column(Boolean, default=True)

    target_price    = Column(Numeric(12, 2))
    target_date     = Column(Date)            # e.g. Mar 2028
    expected_cagr   = Column(Float)           # annualised
    probability     = Column(Float)           # 0–1

    # Key assumptions
    revenue_cagr    = Column(Float)
    ebitda_margin   = Column(Float)
    exit_pe         = Column(Float)
    exit_ev_ebitda  = Column(Float)

    description     = Column(Text)           # narrative assumptions
    key_triggers    = Column(JSONB)           # list of triggers for this scenario
    key_risks       = Column(JSONB)           # list of risks to this scenario

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Technical snapshots ──────────────────────────────────────────────────────
class TechnicalSnapshot(Base):
    """Daily technical indicator snapshot for trend tracking."""
    __tablename__ = "mt_technical_snapshots"
    __table_args__ = (
        UniqueConstraint("isin", "snapshot_date", name="uq_tech_date"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False)
    snapshot_date   = Column(Date, nullable=False)

    close_price     = Column(Numeric(12, 2))
    volume          = Column(Numeric(20, 0))
    volume_ma20     = Column(Numeric(20, 0))

    # Moving averages
    sma_20          = Column(Float)
    sma_50          = Column(Float)
    sma_200         = Column(Float)
    ema_20          = Column(Float)

    # Above/below key MAs
    above_sma_50    = Column(Boolean)
    above_sma_200   = Column(Boolean)
    golden_cross    = Column(Boolean)   # SMA50 > SMA200 (bullish)
    death_cross     = Column(Boolean)   # SMA50 < SMA200 (bearish)

    # Momentum
    rsi_14          = Column(Float)
    macd            = Column(Float)
    macd_signal     = Column(Float)
    macd_histogram  = Column(Float)

    # Price from highs/lows
    pct_from_52w_high = Column(Float)
    pct_from_52w_low  = Column(Float)

    # Computed trend
    trend           = Column(String(20))   # UPTREND / DOWNTREND / SIDEWAYS / REVERSAL_UP / REVERSAL_DOWN
    technical_score = Column(Float)        # 0–100

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─── Promoter tracking ────────────────────────────────────────────────────────
class PromoterTracking(Base):
    """Quarterly promoter shareholding and pledging history."""
    __tablename__ = "mt_promoter_tracking"
    __table_args__ = (
        UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_prom_period"),
    )

    id                      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin                    = Column(String(12), nullable=False)
    fiscal_year             = Column(Integer, nullable=False)
    quarter                 = Column(String(3), nullable=False)

    promoter_holding_pct    = Column(Float)
    promoter_pledged_pct    = Column(Float)   # % of promoter holding that is pledged
    promoter_pledged_abs_pct= Column(Float)   # % of total shares pledged
    fii_pct                 = Column(Float)
    dii_pct                 = Column(Float)
    public_pct              = Column(Float)

    # Change vs previous quarter
    promoter_change_pct     = Column(Float)   # + = bought, - = sold
    pledged_change_pct      = Column(Float)   # + = more pledged (bearish)

    signal                  = Column(String(10), default="YELLOW")  # GREEN / YELLOW / RED

    recorded_at             = Column(DateTime(timezone=True), default=datetime.utcnow)
