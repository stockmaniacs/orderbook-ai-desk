"""
SQLAlchemy models — Technical Analysis AI Worker.

Tables:
  ta_profiles          — master profile per stock (scores, classification, signal)
  ta_daily_snapshots   — daily OHLCV + all computed indicators
  ta_relative_strength — RS scores vs Nifty500, sector, timeframes
  ta_patterns          — detected chart patterns with status tracking
  ta_breakout_levels   — entry / stop / target levels per detected setup
  ta_alerts            — generated daily/intraday alerts
  ta_signal_history    — every signal emitted; tracks future performance
  ta_market_breadth    — daily market-wide breadth metrics
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ─── 1. Technical Profile ─────────────────────────────────────────────────────
class TechnicalProfile(Base):
    """
    One row per stock — updated daily after market close.
    Stores composite scores and the current classification / signal.
    """
    __tablename__ = "ta_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:         Mapped[str]  = mapped_column(String(12), unique=True, nullable=False, index=True)
    symbol_nse:   Mapped[str | None]  = mapped_column(String(30))
    symbol_bse:   Mapped[str | None]  = mapped_column(String(20))
    company_name: Mapped[str]  = mapped_column(String(200), nullable=False)
    sector:       Mapped[str | None]  = mapped_column(String(100))
    industry:     Mapped[str | None]  = mapped_column(String(100))
    exchange:     Mapped[str]  = mapped_column(String(10), default="NSE")
    market_cap_cr: Mapped[float | None] = mapped_column(Float)
    market_cap_cat: Mapped[str | None]  = mapped_column(String(10))   # LARGE/MID/SMALL/MICRO

    # ── Composite scores (0–100) ──────────────────────────────────────────
    trend_score:        Mapped[float | None] = mapped_column(Float)   # Minervini + Stage
    rs_score:           Mapped[float | None] = mapped_column(Float)   # Relative Strength
    momentum_score:     Mapped[float | None] = mapped_column(Float)   # RSI/ADX/MACD
    volume_score:       Mapped[float | None] = mapped_column(Float)   # Accum/Dist/Delivery
    pattern_score:      Mapped[float | None] = mapped_column(Float)   # Pattern quality
    technical_score:    Mapped[float | None] = mapped_column(Float)   # Overall 0–100
    conviction_score:   Mapped[float | None] = mapped_column(Float)   # Final conviction

    # ── Rankings ─────────────────────────────────────────────────────────
    rs_rating:          Mapped[int | None] = mapped_column(Integer)   # 1–99 (IBD-style)
    sector_rank:        Mapped[int | None] = mapped_column(Integer)
    industry_rank:      Mapped[int | None] = mapped_column(Integer)
    market_leader_rank: Mapped[int | None] = mapped_column(Integer)   # rank across universe

    # ── Classification & Signal ──────────────────────────────────────────
    # ELITE_LEADER / STRONG_STRUCTURE / EMERGING_LEADER / CONSTRUCTIVE /
    # WATCHLIST / WEAK_STRUCTURE / AVOID
    classification: Mapped[str] = mapped_column(String(30), default="WATCHLIST")
    # STRONG_BUY / BUY / ACCUMULATION / HOLD / REDUCE / SELL / AVOID
    signal:         Mapped[str] = mapped_column(String(20), default="HOLD")
    stage:          Mapped[int | None] = mapped_column(Integer)   # Weinstein Stage 1–4
    minervini_count: Mapped[int] = mapped_column(Integer, default=0)  # 0–8 criteria met

    # ── Key Levels ───────────────────────────────────────────────────────
    cmp:              Mapped[float | None] = mapped_column(Float)
    pivot_price:      Mapped[float | None] = mapped_column(Float)
    entry_price:      Mapped[float | None] = mapped_column(Float)
    ideal_buy_zone_lo: Mapped[float | None] = mapped_column(Float)
    ideal_buy_zone_hi: Mapped[float | None] = mapped_column(Float)
    breakout_level:   Mapped[float | None] = mapped_column(Float)
    stop_loss:        Mapped[float | None] = mapped_column(Float)
    atr_stop:         Mapped[float | None] = mapped_column(Float)
    trailing_stop:    Mapped[float | None] = mapped_column(Float)
    target_price:     Mapped[float | None] = mapped_column(Float)
    expected_upside_pct: Mapped[float | None] = mapped_column(Float)
    risk_reward_ratio:   Mapped[float | None] = mapped_column(Float)

    # ── Risk ─────────────────────────────────────────────────────────────
    atr_14:           Mapped[float | None] = mapped_column(Float)
    atr_pct:          Mapped[float | None] = mapped_column(Float)    # ATR as % of price
    volatility_20d:   Mapped[float | None] = mapped_column(Float)    # 20-day realized vol
    risk_score:       Mapped[float | None] = mapped_column(Float)    # 0–10
    position_size_pct: Mapped[float | None] = mapped_column(Float)   # % of portfolio
    max_portfolio_alloc: Mapped[float | None] = mapped_column(Float) # % cap

    # ── Active pattern ────────────────────────────────────────────────────
    active_pattern:   Mapped[str | None] = mapped_column(String(40))  # e.g. VCP
    pattern_maturity: Mapped[float | None] = mapped_column(Float)     # 0–100%

    # ── Timestamps ───────────────────────────────────────────────────────
    scores_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_date:        Mapped[date | None]      = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ta_profile_score", "technical_score"),
        Index("idx_ta_profile_signal", "signal"),
        Index("idx_ta_profile_class",  "classification"),
        Index("idx_ta_profile_rs",     "rs_rating"),
        Index("idx_ta_profile_stage",  "stage"),
    )


# ─── 2. Daily Snapshot ────────────────────────────────────────────────────────
class DailySnapshot(Base):
    """
    Daily OHLCV + all computed technical indicators.
    One row per (isin, date).
    """
    __tablename__ = "ta_daily_snapshots"

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:   Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    snap_date: Mapped[date] = mapped_column(Date, nullable=False)

    # OHLCV
    open:   Mapped[float | None] = mapped_column(Float)
    high:   Mapped[float | None] = mapped_column(Float)
    low:    Mapped[float | None] = mapped_column(Float)
    close:  Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None]   = mapped_column(BigInteger)
    delivery_pct: Mapped[float | None] = mapped_column(Float)   # % delivery of total volume

    # Moving Averages
    sma_10:  Mapped[float | None] = mapped_column(Float)
    sma_20:  Mapped[float | None] = mapped_column(Float)
    sma_50:  Mapped[float | None] = mapped_column(Float)
    sma_150: Mapped[float | None] = mapped_column(Float)
    sma_200: Mapped[float | None] = mapped_column(Float)
    ema_20:  Mapped[float | None] = mapped_column(Float)
    ema_50:  Mapped[float | None] = mapped_column(Float)
    wma_30w: Mapped[float | None] = mapped_column(Float)   # 30-week (150-day) WMA proxy

    # MA relationships
    above_sma_50:    Mapped[bool | None] = mapped_column(Boolean)
    above_sma_150:   Mapped[bool | None] = mapped_column(Boolean)
    above_sma_200:   Mapped[bool | None] = mapped_column(Boolean)
    sma_50_vs_150:   Mapped[float | None] = mapped_column(Float)  # sma50 / sma150 - 1
    sma_150_vs_200:  Mapped[float | None] = mapped_column(Float)  # slope direction
    sma_200_slope_8w: Mapped[float | None] = mapped_column(Float) # 8-week slope of 200MA

    # 52-week levels
    high_52w:     Mapped[float | None] = mapped_column(Float)
    low_52w:      Mapped[float | None] = mapped_column(Float)
    pct_from_52w_high: Mapped[float | None] = mapped_column(Float)
    pct_from_52w_low:  Mapped[float | None] = mapped_column(Float)
    new_52w_high: Mapped[bool] = mapped_column(Boolean, default=False)
    new_52w_low:  Mapped[bool] = mapped_column(Boolean, default=False)

    # Momentum
    rsi_14:       Mapped[float | None] = mapped_column(Float)
    rsi_weekly:   Mapped[float | None] = mapped_column(Float)
    adx_14:       Mapped[float | None] = mapped_column(Float)
    di_plus:      Mapped[float | None] = mapped_column(Float)
    di_minus:     Mapped[float | None] = mapped_column(Float)
    macd:         Mapped[float | None] = mapped_column(Float)
    macd_signal:  Mapped[float | None] = mapped_column(Float)
    macd_hist:    Mapped[float | None] = mapped_column(Float)
    macd_hist_expanding: Mapped[bool | None] = mapped_column(Boolean)  # vs prior bar

    # Momentum acceleration (rate-of-change)
    roc_10:  Mapped[float | None] = mapped_column(Float)   # 10-day ROC
    roc_20:  Mapped[float | None] = mapped_column(Float)
    roc_60:  Mapped[float | None] = mapped_column(Float)   # quarterly momentum

    # Volume & Accumulation
    vol_sma_20:   Mapped[int | None]   = mapped_column(BigInteger)
    vol_sma_50:   Mapped[int | None]   = mapped_column(BigInteger)
    vol_ratio:    Mapped[float | None] = mapped_column(Float)    # vol / vol_sma_20
    up_vol_ratio: Mapped[float | None] = mapped_column(Float)    # up-volume / total (21d)
    accum_dist:   Mapped[float | None] = mapped_column(Float)    # A/D line value
    obv:          Mapped[float | None] = mapped_column(Float)    # On-Balance Volume
    is_pocket_pivot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_accumulation_day: Mapped[bool] = mapped_column(Boolean, default=False)
    is_distribution_day: Mapped[bool] = mapped_column(Boolean, default=False)
    distribution_days_20: Mapped[int] = mapped_column(Integer, default=0)  # count in 20d
    tight_action_5d: Mapped[bool] = mapped_column(Boolean, default=False)   # <1.5% range 5d

    # ATR & Volatility
    atr_14:       Mapped[float | None] = mapped_column(Float)
    volatility_20d: Mapped[float | None] = mapped_column(Float)

    # Scores computed on this day
    trend_score:    Mapped[float | None] = mapped_column(Float)
    rs_score:       Mapped[float | None] = mapped_column(Float)
    momentum_score: Mapped[float | None] = mapped_column(Float)
    volume_score:   Mapped[float | None] = mapped_column(Float)
    technical_score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("isin", "snap_date", name="uq_ta_snap_isin_date"),
        Index("idx_ta_snap_date",  "snap_date"),
        Index("idx_ta_snap_score", "technical_score"),
    )


# ─── 3. Relative Strength ─────────────────────────────────────────────────────
class RelativeStrength(Base):
    """
    RS scores vs benchmarks for multiple timeframes — updated daily.
    """
    __tablename__ = "ta_relative_strength"

    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:    Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    rs_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Raw RS vs Nifty 500 (1 = stock / nifty500 ratio)
    rs_vs_nifty500_1m:  Mapped[float | None] = mapped_column(Float)
    rs_vs_nifty500_3m:  Mapped[float | None] = mapped_column(Float)
    rs_vs_nifty500_6m:  Mapped[float | None] = mapped_column(Float)
    rs_vs_nifty500_12m: Mapped[float | None] = mapped_column(Float)

    # RS vs sector index
    rs_vs_sector_1m:  Mapped[float | None] = mapped_column(Float)
    rs_vs_sector_3m:  Mapped[float | None] = mapped_column(Float)
    rs_vs_sector_6m:  Mapped[float | None] = mapped_column(Float)

    # IBD-style composite RS Rating (1–99)
    rs_rating:    Mapped[int | None] = mapped_column(Integer)

    # RS trend: slope of 10-week RS line (positive = outperforming)
    rs_trend_slope: Mapped[float | None] = mapped_column(Float)
    rs_trend:       Mapped[str | None]   = mapped_column(String(20))  # UP/DOWN/FLAT

    # RS breakout: RS line made new high before or with price breakout
    rs_breakout:    Mapped[bool] = mapped_column(Boolean, default=False)
    rs_new_high:    Mapped[bool] = mapped_column(Boolean, default=False)  # RS line at new 52w high

    # Sector RS rank (1 = best sector)
    sector_rs_rank: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("isin", "rs_date", name="uq_ta_rs_isin_date"),
        Index("idx_ta_rs_rating", "rs_rating"),
    )


# ─── 4. Pattern Detection ─────────────────────────────────────────────────────
class PatternDetection(Base):
    """
    Chart patterns detected by the pattern engine.
    Patterns evolve through states: FORMING → COMPLETE / BREAKOUT / FAILED.
    """
    __tablename__ = "ta_patterns"

    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:      Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    # VCP / CUP_HANDLE / FLAT_BASE / DOUBLE_BOTTOM / DARVAS_BOX /
    # ASCENDING_BASE / HIGH_TIGHT_FLAG / RANGE_CONTRACTION
    pattern_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # FORMING / COMPLETE / BREAKOUT / FAILED / INVALIDATED
    status:    Mapped[str] = mapped_column(String(20), default="FORMING")

    detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    breakout_date: Mapped[date | None] = mapped_column(Date)
    failed_date:   Mapped[date | None] = mapped_column(Date)

    # Pattern geometry
    depth_pct:     Mapped[float | None] = mapped_column(Float)   # correction depth %
    duration_days: Mapped[int | None]   = mapped_column(Integer) # base length
    tight_pct:     Mapped[float | None] = mapped_column(Float)   # tightness of action
    contractions:  Mapped[int | None]   = mapped_column(Integer) # VCP: # of contractions

    # Key levels derived from pattern
    pivot_price:   Mapped[float | None] = mapped_column(Float)
    buy_zone_lo:   Mapped[float | None] = mapped_column(Float)
    buy_zone_hi:   Mapped[float | None] = mapped_column(Float)
    pattern_stop:  Mapped[float | None] = mapped_column(Float)   # stop below pattern
    pattern_target: Mapped[float | None] = mapped_column(Float)

    # Quality
    quality_score: Mapped[float | None] = mapped_column(Float)  # 0–100

    # Pattern parameters (JSON for pattern-specific data)
    pattern_data:  Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ta_pat_isin", "isin"),
        Index("idx_ta_pat_status", "status"),
        Index("idx_ta_pat_type", "pattern_type"),
        Index("idx_ta_pat_date", "detected_date"),
    )


# ─── 5. Breakout Levels ───────────────────────────────────────────────────────
class BreakoutLevel(Base):
    """
    Derived trade setup levels for a stock — updated whenever a new pattern
    is detected or the current setup matures.
    """
    __tablename__ = "ta_breakout_levels"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:       Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    pattern_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ta_patterns.id", ondelete="SET NULL"), nullable=True)
    calc_date:  Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    cmp:              Mapped[float | None] = mapped_column(Float)
    entry_price:      Mapped[float | None] = mapped_column(Float)
    ideal_buy_zone_lo: Mapped[float | None] = mapped_column(Float)
    ideal_buy_zone_hi: Mapped[float | None] = mapped_column(Float)
    breakout_level:   Mapped[float | None] = mapped_column(Float)
    pivot_price:      Mapped[float | None] = mapped_column(Float)

    # Stop levels
    stop_loss:     Mapped[float | None] = mapped_column(Float)    # hard stop
    atr_stop:      Mapped[float | None] = mapped_column(Float)    # price - 1.5×ATR
    trailing_stop: Mapped[float | None] = mapped_column(Float)    # 10-week low MA proxy

    # Reward / Risk
    target_price:       Mapped[float | None] = mapped_column(Float)
    expected_upside_pct: Mapped[float | None] = mapped_column(Float)
    risk_pct:           Mapped[float | None] = mapped_column(Float)  # (entry - stop) / entry
    risk_reward_ratio:  Mapped[float | None] = mapped_column(Float)

    # Position sizing
    position_size_pct:   Mapped[float | None] = mapped_column(Float)
    max_portfolio_alloc: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── 6. Technical Alerts ─────────────────────────────────────────────────────
class TechnicalAlert(Base):
    """
    Generated alerts — one per event, de-duplicated with a cooldown window.
    """
    __tablename__ = "ta_alerts"

    id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:     Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String(200))
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)

    # NEW_BREAKOUT / VCP_COMPLETE / RS_BREAKOUT / POCKET_PIVOT /
    # SMA50_RECLAIM / SMA150_RECLAIM / SMA200_RECLAIM /
    # HIGH_52W_BREAKOUT / STAGE2_BREAKOUT / HEAVY_ACCUM /
    # HEAVY_DIST / TREND_DETERIORATION / PATTERN_FAILED / NEW_52W_HIGH
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity:   Mapped[str] = mapped_column(String(10), default="MEDIUM")  # HIGH/MEDIUM/LOW

    title:       Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    price_at_alert: Mapped[float | None] = mapped_column(Float)

    # Classification / signal at time of alert
    classification_at: Mapped[str | None] = mapped_column(String(30))
    signal_at:         Mapped[str | None] = mapped_column(String(20))
    tech_score_at:     Mapped[float | None] = mapped_column(Float)
    rs_rating_at:      Mapped[int | None]   = mapped_column(Integer)

    data_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    is_read:      Mapped[bool] = mapped_column(Boolean, default=False)
    is_actioned:  Mapped[bool] = mapped_column(Boolean, default=False)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_ta_alert_isin",    "isin"),
        Index("idx_ta_alert_type",    "alert_type"),
        Index("idx_ta_alert_date",    "alert_date"),
        Index("idx_ta_alert_unread",  "is_read"),
    )


# ─── 7. Signal History ────────────────────────────────────────────────────────
class SignalHistory(Base):
    """
    Every signal emitted — tracks future price performance to continuously
    improve the scoring model.
    """
    __tablename__ = "ta_signal_history"

    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin:      Mapped[str]  = mapped_column(String(12), nullable=False, index=True)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)

    signal:         Mapped[str] = mapped_column(String(20), nullable=False)
    classification: Mapped[str] = mapped_column(String(30))
    pattern_type:   Mapped[str | None] = mapped_column(String(30))
    alert_type:     Mapped[str | None] = mapped_column(String(40))

    # Scores at time of signal
    technical_score: Mapped[float | None] = mapped_column(Float)
    rs_rating:       Mapped[int | None]   = mapped_column(Integer)
    trend_score:     Mapped[float | None] = mapped_column(Float)
    momentum_score:  Mapped[float | None] = mapped_column(Float)
    volume_score:    Mapped[float | None] = mapped_column(Float)
    conviction_score: Mapped[float | None] = mapped_column(Float)

    # Trade levels at signal time
    price_at_signal:  Mapped[float | None] = mapped_column(Float)
    entry_price:      Mapped[float | None] = mapped_column(Float)
    stop_loss:        Mapped[float | None] = mapped_column(Float)
    target_price:     Mapped[float | None] = mapped_column(Float)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Float)

    # Forward performance (populated by update_outcomes_task)
    price_7d:    Mapped[float | None] = mapped_column(Float)
    price_30d:   Mapped[float | None] = mapped_column(Float)
    price_60d:   Mapped[float | None] = mapped_column(Float)
    price_90d:   Mapped[float | None] = mapped_column(Float)
    return_7d:   Mapped[float | None] = mapped_column(Float)   # % return
    return_30d:  Mapped[float | None] = mapped_column(Float)
    return_60d:  Mapped[float | None] = mapped_column(Float)
    return_90d:  Mapped[float | None] = mapped_column(Float)
    hit_target:  Mapped[bool | None]  = mapped_column(Boolean)
    hit_stop:    Mapped[bool | None]  = mapped_column(Boolean)
    max_gain_pct: Mapped[float | None] = mapped_column(Float)  # max favorable excursion
    max_loss_pct: Mapped[float | None] = mapped_column(Float)  # max adverse excursion
    outcome:      Mapped[str | None]  = mapped_column(String(20))  # WIN/LOSS/OPEN/NEUTRAL

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ta_sig_hist_date",    "signal_date"),
        Index("idx_ta_sig_hist_signal",  "signal"),
        Index("idx_ta_sig_hist_outcome", "outcome"),
    )


# ─── 8. Market Breadth ───────────────────────────────────────────────────────
class MarketBreadth(Base):
    """
    Daily market-wide breadth metrics — universe: NSE 500 equivalent.
    """
    __tablename__ = "ta_market_breadth"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breadth_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)

    # Universe stats
    total_stocks: Mapped[int | None] = mapped_column(Integer)

    # % Above MAs
    pct_above_sma_50:  Mapped[float | None] = mapped_column(Float)
    pct_above_sma_150: Mapped[float | None] = mapped_column(Float)
    pct_above_sma_200: Mapped[float | None] = mapped_column(Float)

    # New highs / lows (52-week)
    new_highs:   Mapped[int | None] = mapped_column(Integer)
    new_lows:    Mapped[int | None] = mapped_column(Integer)
    nh_nl_ratio: Mapped[float | None] = mapped_column(Float)  # highs/(highs+lows)

    # Advance / Decline
    advances:  Mapped[int | None] = mapped_column(Integer)
    declines:  Mapped[int | None] = mapped_column(Integer)
    unchanged: Mapped[int | None] = mapped_column(Integer)
    ad_ratio:  Mapped[float | None] = mapped_column(Float)    # advances/declines
    ad_line:   Mapped[float | None] = mapped_column(Float)    # cumulative A-D

    # Signal counts (how many stocks in each classification)
    elite_leaders_count:    Mapped[int] = mapped_column(Integer, default=0)
    strong_structure_count: Mapped[int] = mapped_column(Integer, default=0)
    emerging_leaders_count: Mapped[int] = mapped_column(Integer, default=0)
    avoid_count:            Mapped[int] = mapped_column(Integer, default=0)

    # Sector rankings snapshot (top 5 sectors JSON)
    top_sectors:   Mapped[dict | None] = mapped_column(JSONB)
    sector_scores: Mapped[dict | None] = mapped_column(JSONB)  # sector → avg RS score

    # Market regime
    # BULL_CONFIRMED / BULL_UNDER_PRESSURE / SIDEWAYS / BEAR_CONFIRMED / BEAR_RALLY
    market_regime: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
