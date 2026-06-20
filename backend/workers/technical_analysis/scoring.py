"""
Scoring Engine — Technical Analysis AI Worker.

Computes:
  - Minervini Trend Template (8 criteria checklist)
  - Stan Weinstein Stage Analysis (1–4)
  - Trend Score (0–100)
  - Relative Strength Score (0–100)
  - Momentum Score (0–100)
  - Volume / Accumulation Score (0–100)
  - Pattern Score (0–100)
  - Technical Score — weighted composite (0–100)
  - Conviction Score — final output (0–100)
  - Classification: ELITE_LEADER → AVOID
  - Signal: STRONG_BUY → AVOID
  - Risk metrics: ATR stop, position size, risk-reward
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ─── Input dataclasses ────────────────────────────────────────────────────────
@dataclass
class PriceData:
    """Snapshot of price + indicator values for one stock on one date."""
    isin: str
    close: float
    high: float
    low: float
    volume: int

    sma_10: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_150: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    wma_30w: float | None = None   # 30-week WMA proxy

    high_52w: float | None = None
    low_52w: float | None = None

    rsi_14: float | None = None
    rsi_weekly: float | None = None
    adx_14: float | None = None
    di_plus: float | None = None
    di_minus: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    macd_hist_prev: float | None = None  # prior day (for expansion check)

    roc_10: float | None = None
    roc_20: float | None = None
    roc_60: float | None = None

    vol_sma_20: int | None = None
    vol_sma_50: int | None = None
    up_vol_ratio: float | None = None   # up-vol / total vol (21-day)
    delivery_pct: float | None = None
    accum_dist: float | None = None
    obv: float | None = None
    is_pocket_pivot: bool = False
    distribution_days_20: int = 0
    tight_action_5d: bool = False

    atr_14: float | None = None
    volatility_20d: float | None = None

    # RS fields
    rs_rating: int | None = None          # 1–99
    rs_vs_nifty500_3m: float | None = None
    rs_vs_nifty500_6m: float | None = None
    rs_trend: str | None = None           # UP/DOWN/FLAT
    rs_breakout: bool = False
    rs_new_high: bool = False

    # Pattern
    active_pattern: str | None = None
    pattern_maturity: float | None = None  # 0–100
    pattern_quality: float | None = None   # 0–100

    # Prior scores (for signal change detection)
    prev_technical_score: float | None = None
    prev_signal: str | None = None


@dataclass
class ScoringResult:
    """Full scoring output for one stock."""
    isin: str

    # ── Minervini ────────────────────────────────────────────────────────
    minervini_criteria: list[bool] = field(default_factory=lambda: [False] * 8)
    minervini_count: int = 0    # 0–8

    # ── Stage ────────────────────────────────────────────────────────────
    stage: int = 0              # 1–4

    # ── Component scores ─────────────────────────────────────────────────
    trend_score: float = 0.0        # 0–100
    rs_score: float = 0.0
    momentum_score: float = 0.0
    volume_score: float = 0.0
    pattern_score: float = 0.0
    technical_score: float = 0.0    # weighted composite
    conviction_score: float = 0.0

    # ── Classification & Signal ──────────────────────────────────────────
    classification: str = "WATCHLIST"
    signal: str = "HOLD"

    # ── Risk & Levels ────────────────────────────────────────────────────
    atr_14: float | None = None
    atr_pct: float | None = None
    volatility_20d: float | None = None
    risk_score: float = 5.0           # 0–10 (0=lowest risk)
    position_size_pct: float = 2.0    # % of portfolio
    max_portfolio_alloc: float = 5.0

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
    risk_reward_ratio: float | None = None

    # ── Alert triggers ────────────────────────────────────────────────────
    alert_triggers: list[str] = field(default_factory=list)


# ─── Constants ────────────────────────────────────────────────────────────────
# Minervini Trend Template criteria (see "Trade Like a Stock Market Wizard")
# 1. Price > 200 SMA
# 2. 200 SMA trending up for at least 4 weeks
# 3. 50 SMA > 200 SMA (golden cross alignment)
# 4. 150 SMA > 200 SMA
# 5. Price > 50 SMA
# 6. Price within 25% of 52-week high (not too far extended)
# 7. Price > 30% above 52-week low
# 8. RS Rating ≥ 70 (top 30% of all stocks)

SCORE_WEIGHTS = {
    "trend":    0.30,
    "rs":       0.25,
    "momentum": 0.20,
    "volume":   0.15,
    "pattern":  0.10,
}

CLASSIFICATION_THRESHOLDS = [
    (87, "ELITE_LEADER"),
    (74, "STRONG_STRUCTURE"),
    (62, "EMERGING_LEADER"),
    (52, "CONSTRUCTIVE"),
    (40, "WATCHLIST"),
    (28, "WEAK_STRUCTURE"),
    (0,  "AVOID"),
]

SIGNAL_MAP = {
    "ELITE_LEADER":     "STRONG_BUY",
    "STRONG_STRUCTURE": "BUY",
    "EMERGING_LEADER":  "ACCUMULATION",
    "CONSTRUCTIVE":     "HOLD",
    "WATCHLIST":        "HOLD",
    "WEAK_STRUCTURE":   "REDUCE",
    "AVOID":            "AVOID",
}

# Risk-adjusted position sizing (Kelly-inspired)
MAX_ALLOC_BY_CLASS = {
    "ELITE_LEADER":     8.0,
    "STRONG_STRUCTURE": 6.0,
    "EMERGING_LEADER":  5.0,
    "CONSTRUCTIVE":     3.0,
    "WATCHLIST":        2.0,
    "WEAK_STRUCTURE":   0.0,
    "AVOID":            0.0,
}


# ─── Helper ───────────────────────────────────────────────────────────────────
def _safe(val: float | None, fallback: float = 0.0) -> float:
    return val if val is not None else fallback


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


# ─── 1. Minervini Trend Template ─────────────────────────────────────────────
def check_minervini_template(p: PriceData) -> tuple[list[bool], int]:
    """
    Returns (criteria_list, count_met).
    True = criterion satisfied.
    """
    c = p.close
    criteria: list[bool] = [False] * 8

    # 1. Price > 200 SMA
    if p.sma_200 and c > p.sma_200:
        criteria[0] = True

    # 2. 200 SMA trending up — proxy: SMA200 > SMA200 from implied earlier
    #    We approximate via sma_150 < sma_200 check inverted for trend direction.
    #    In practice the slope is computed from snapshot history.
    #    Here: use sma_200 vs sma_150 direction heuristic
    if p.sma_200 and p.sma_150:
        # if 150 > 200 SMA, 200 is trending up (price has been above it recently)
        criteria[1] = p.sma_150 > p.sma_200 * 0.99

    # 3. 50 SMA > 200 SMA
    if p.sma_50 and p.sma_200:
        criteria[2] = p.sma_50 > p.sma_200

    # 4. 150 SMA > 200 SMA
    if p.sma_150 and p.sma_200:
        criteria[3] = p.sma_150 > p.sma_200

    # 5. Price > 50 SMA
    if p.sma_50:
        criteria[4] = c > p.sma_50

    # 6. Price within 25% of 52-week high
    if p.high_52w:
        pct_from_high = (p.high_52w - c) / p.high_52w
        criteria[5] = pct_from_high <= 0.25

    # 7. Price ≥ 130% of 52-week low (i.e. ≥30% above)
    if p.low_52w:
        criteria[6] = c >= p.low_52w * 1.30

    # 8. RS Rating ≥ 70
    if p.rs_rating is not None:
        criteria[7] = p.rs_rating >= 70

    return criteria, sum(criteria)


# ─── 2. Stan Weinstein Stage Analysis ────────────────────────────────────────
def compute_stage(p: PriceData) -> int:
    """
    Stage 1: Base — price flat, above 30w WMA or bouncing from below
    Stage 2: Advance — price above rising 30w WMA, trending up
    Stage 3: Top — price below peak but above 30w WMA, WMA flattening
    Stage 4: Decline — price below declining 30w WMA
    """
    if not p.sma_150:  # 150-day ≈ 30-week
        return 0

    above_wma = p.close > p.sma_150

    # Use sma_50 relative to sma_150 as proxy for WMA trend
    if p.sma_50:
        wma_trending_up = p.sma_50 > p.sma_150

        if above_wma and wma_trending_up:
            # Stage 2: price above rising MA
            if p.sma_200 and p.close > p.sma_200:
                return 2
            # possibly early stage 2
            return 2
        elif above_wma and not wma_trending_up:
            # Stage 3: topping
            return 3
        elif not above_wma and not wma_trending_up:
            # Stage 4: decline
            return 4
        else:
            # Stage 1: basing (price below WMA but WMA turning up)
            return 1
    return 0


# ─── 3. Trend Score ───────────────────────────────────────────────────────────
def compute_trend_score(p: PriceData, minervini_count: int, stage: int) -> float:
    """
    Combines Minervini template + stage analysis into 0–100.
    Minervini: up to 60 points (7.5 per criterion)
    Stage:     up to 25 points
    MA slope:  up to 15 points
    """
    score = 0.0

    # Minervini (60 pts max)
    score += minervini_count * 7.5

    # Stage bonus/penalty (25 pts)
    stage_pts = { 0: 0, 1: 8, 2: 25, 3: 10, 4: 0 }
    score += stage_pts.get(stage, 0)

    # MA alignment bonus (15 pts)
    # All three stacked: price > 50 > 150 > 200
    if all([p.sma_50, p.sma_150, p.sma_200]):
        if p.close > p.sma_50 > p.sma_150 > p.sma_200:
            score += 15
        elif p.sma_50 > p.sma_150 > p.sma_200:
            score += 8

    # Small bonus: within 5% of 52-week high
    if p.high_52w:
        pct_from_high = (p.high_52w - p.close) / p.high_52w
        if pct_from_high <= 0.05:
            score += 5
        elif pct_from_high <= 0.10:
            score += 3

    return _clamp(score)


# ─── 4. Relative Strength Score ──────────────────────────────────────────────
def compute_rs_score(p: PriceData) -> float:
    """
    RS Rating (1–99) → 40% of RS score
    RS vs Nifty500 3M/6M → 30%
    RS trend + breakout → 20%
    RS new high → 10%
    """
    score = 0.0

    # RS Rating (40 pts)
    if p.rs_rating is not None:
        # Linear: RS 99 = 40 pts, RS 50 = 20 pts, RS 1 = 0.4 pts
        score += (p.rs_rating / 99) * 40

    # RS vs Nifty500 3M (20 pts) — >0 means outperforming
    if p.rs_vs_nifty500_3m is not None:
        # Outperformance capped at ±20%
        rs3 = _clamp(p.rs_vs_nifty500_3m * 100, -20, 20)
        score += (rs3 + 20) / 40 * 20  # normalize [-20,20] → [0,20]

    # RS vs Nifty500 6M (10 pts)
    if p.rs_vs_nifty500_6m is not None:
        rs6 = _clamp(p.rs_vs_nifty500_6m * 100, -30, 30)
        score += (rs6 + 30) / 60 * 10

    # RS trend direction (10 pts)
    rs_trend_pts = { "UP": 10, "FLAT": 5, "DOWN": 0 }
    score += rs_trend_pts.get(p.rs_trend or "FLAT", 5)

    # RS breakout (10 pts) + RS new high (10 pts)
    if p.rs_breakout:
        score += 10
    if p.rs_new_high:
        score += 10

    return _clamp(score)


# ─── 5. Momentum Score ───────────────────────────────────────────────────────
def compute_momentum_score(p: PriceData) -> float:
    """
    RSI daily (25 pts) + RSI weekly (15 pts) + ADX (20 pts) +
    MACD histogram (20 pts) + ROC acceleration (20 pts)
    """
    score = 0.0

    # RSI 14 (25 pts)
    # Ideal range 55–75: full 25 pts. >80 = extended, <40 = weak
    if p.rsi_14 is not None:
        r = p.rsi_14
        if 55 <= r <= 75:
            score += 25
        elif 45 <= r < 55:
            score += 15
        elif 75 < r <= 80:
            score += 18     # slightly extended
        elif r > 80:
            score += 8      # overbought risk
        elif 35 <= r < 45:
            score += 5
        # < 35: 0

    # Weekly RSI (15 pts)
    if p.rsi_weekly is not None:
        rw = p.rsi_weekly
        if rw >= 50:
            score += min((rw - 50) / 30 * 15, 15)  # 50→0, 80→15

    # ADX (20 pts) — trend strength
    # ADX > 25: trending; 20-25: emerging; <20: no trend
    if p.adx_14 is not None:
        adx = p.adx_14
        if adx >= 40:
            score += 20
        elif adx >= 30:
            score += 17
        elif adx >= 25:
            score += 13
        elif adx >= 20:
            score += 8
        # <20: weak trend = 0
        # DI+ > DI- required
        if p.di_plus and p.di_minus and p.di_plus > p.di_minus:
            score += 3  # bonus: directional alignment

    # MACD histogram (20 pts)
    if p.macd_hist is not None:
        if p.macd_hist > 0:
            score += 12
            # Expanding = extra momentum
            if p.macd_hist_prev is not None and p.macd_hist > p.macd_hist_prev:
                score += 8  # histogram expanding
        elif p.macd_hist < 0:
            # Histogram contracting (turning up from below zero)
            if p.macd_hist_prev is not None and p.macd_hist > p.macd_hist_prev:
                score += 5  # improving

    # ROC acceleration (17 pts)
    if p.roc_10 is not None and p.roc_20 is not None:
        # Short-term momentum > long-term = accelerating
        if p.roc_10 > 0 and p.roc_20 > 0:
            score += 10
            if p.roc_10 > p.roc_20:  # short-term accelerating
                score += 7
        elif p.roc_10 > 0:
            score += 5

    return _clamp(score)


# ─── 6. Volume / Accumulation Score ─────────────────────────────────────────
def compute_volume_score(p: PriceData) -> float:
    """
    Volume expansion (20) + Up/Down vol ratio (20) + Delivery % (15) +
    Pocket pivots (20) + Distribution day count (15) + Tight action (10)
    """
    score = 0.0

    # Volume ratio (vs 20-day avg)
    if p.vol_sma_20 and p.vol_sma_20 > 0:
        vol_ratio = p.volume / p.vol_sma_20
        if vol_ratio >= 2.0:
            score += 20     # huge volume surge
        elif vol_ratio >= 1.5:
            score += 15
        elif vol_ratio >= 1.2:
            score += 10
        elif vol_ratio >= 0.8:
            score += 6
        # low volume: 0

    # Up/Down volume ratio (21-day)
    if p.up_vol_ratio is not None:
        # >0.6 = accumulation; <0.4 = distribution
        uvr = p.up_vol_ratio
        if uvr >= 0.65:
            score += 20
        elif uvr >= 0.55:
            score += 14
        elif uvr >= 0.45:
            score += 8
        elif uvr < 0.40:
            score += 0  # distribution

    # Delivery percentage (15 pts)
    if p.delivery_pct is not None:
        dlv = p.delivery_pct
        if dlv >= 60:
            score += 15     # strong institutional delivery
        elif dlv >= 50:
            score += 10
        elif dlv >= 40:
            score += 6
        elif dlv >= 30:
            score += 3

    # Pocket pivot (20 pts) — only award if positive day
    if p.is_pocket_pivot:
        score += 20

    # Distribution day count (15 pts — lower is better)
    dist = p.distribution_days_20
    if dist == 0:
        score += 15
    elif dist <= 1:
        score += 12
    elif dist <= 2:
        score += 8
    elif dist <= 3:
        score += 4
    elif dist >= 5:
        score -= 10   # heavy distribution

    # Tight action (10 pts)
    if p.tight_action_5d:
        score += 10

    return _clamp(score)


# ─── 7. Pattern Score ────────────────────────────────────────────────────────
# Pattern hierarchy: high-quality leading patterns score highest
PATTERN_BASE_SCORES: dict[str, float] = {
    "VCP":              90,
    "HIGH_TIGHT_FLAG":  88,
    "CUP_HANDLE":       82,
    "FLAT_BASE":        78,
    "ASCENDING_BASE":   75,
    "DOUBLE_BOTTOM":    72,
    "RANGE_CONTRACTION":65,
    "DARVAS_BOX":       60,
}


def compute_pattern_score(p: PriceData) -> float:
    if not p.active_pattern:
        return 40.0   # neutral — no active pattern

    base = PATTERN_BASE_SCORES.get(p.active_pattern, 50)
    maturity = _safe(p.pattern_maturity, 50) / 100
    quality  = _safe(p.pattern_quality, 60) / 100

    # Blend: 60% base pattern prestige, 40% quality×maturity
    score = base * 0.60 + (quality * maturity * 100) * 0.40
    return _clamp(score)


# ─── 8. Technical Score (weighted composite) ─────────────────────────────────
def compute_technical_score(
    trend: float, rs: float, momentum: float, volume: float, pattern: float
) -> float:
    w = SCORE_WEIGHTS
    return _clamp(
        trend    * w["trend"]    +
        rs       * w["rs"]       +
        momentum * w["momentum"] +
        volume   * w["volume"]   +
        pattern  * w["pattern"]
    )


# ─── 9. Conviction Score ─────────────────────────────────────────────────────
def compute_conviction_score(
    tech_score: float,
    minervini_count: int,
    stage: int,
    rs_score: float,
    rs_breakout: bool,
    rs_new_high: bool,
    is_pocket_pivot: bool,
    distribution_days: int,
) -> float:
    """
    Conviction applies a multiplier on the technical score based on
    confirmations from multiple disciplines converging.
    """
    multiplier = 1.0

    # All Minervini criteria met is a significant confirmation
    if minervini_count >= 7:
        multiplier += 0.15
    elif minervini_count >= 5:
        multiplier += 0.08

    # Stage 2 is the sweet spot
    if stage == 2:
        multiplier += 0.10
    elif stage in (3, 4):
        multiplier -= 0.15

    # RS confirmations
    if rs_breakout and rs_new_high:
        multiplier += 0.12
    elif rs_breakout or rs_new_high:
        multiplier += 0.06

    # Pocket pivot = institutional accumulation
    if is_pocket_pivot:
        multiplier += 0.08

    # Heavy distribution = reduce conviction
    if distribution_days >= 4:
        multiplier -= 0.15
    elif distribution_days >= 3:
        multiplier -= 0.08

    return _clamp(tech_score * multiplier)


# ─── 10. Classification & Signal ─────────────────────────────────────────────
def classify_stock(conviction_score: float) -> str:
    for threshold, cls in CLASSIFICATION_THRESHOLDS:
        if conviction_score >= threshold:
            return cls
    return "AVOID"


def derive_signal(classification: str, stage: int, distribution_days: int, minervini_count: int) -> str:
    base = SIGNAL_MAP.get(classification, "HOLD")
    # Override: Stage 4 = immediate sell signal
    if stage == 4:
        if classification in ("ELITE_LEADER", "STRONG_STRUCTURE"):
            return "REDUCE"
        return "SELL"
    # Override: Heavy distribution
    if distribution_days >= 5:
        return "REDUCE"
    # Override: Very few Minervini criteria met
    if minervini_count <= 2 and base in ("ACCUMULATION", "BUY", "STRONG_BUY"):
        return "HOLD"
    return base


# ─── 11. Risk & Level Calculator ─────────────────────────────────────────────
def compute_risk_levels(p: PriceData, classification: str) -> dict[str, float | None]:
    """Compute all trade levels and risk metrics."""
    c = p.close
    atr = p.atr_14 or (c * 0.02)   # fallback: 2% of price

    # ATR stop: entry - 1.5×ATR
    atr_stop = c - 1.5 * atr

    # Hard stop: last swing low proxy = low_52w + 10% buffer (crude)
    # In practice this would be the pattern base low
    if p.sma_50:
        stop_loss = p.sma_50 * 0.97   # 3% below 50 DMA
    elif p.low_52w:
        stop_loss = max(p.low_52w, c * 0.88)
    else:
        stop_loss = c * 0.90

    stop_loss = max(stop_loss, atr_stop)  # use tighter of the two

    # Trailing stop: 10-week low proxy using 50 SMA
    trailing_stop = p.sma_50 * 0.95 if p.sma_50 else c * 0.92

    # Entry: within buy zone (pivot ±2%)
    pivot = p.high_52w * 0.98 if p.high_52w else c * 1.02
    buy_lo = pivot
    buy_hi = pivot * 1.05

    entry = (buy_lo + buy_hi) / 2

    # Target: based on pattern
    target_mult = {
        "ELITE_LEADER":     2.0,
        "STRONG_STRUCTURE": 1.7,
        "EMERGING_LEADER":  1.5,
        "CONSTRUCTIVE":     1.3,
    }.get(classification, 1.2)

    risk_pct = (entry - stop_loss) / entry if entry > 0 else 0.05
    reward_pct = risk_pct * target_mult * 3   # target = 3× the risk
    target = entry * (1 + reward_pct)
    rr = reward_pct / risk_pct if risk_pct > 0 else 0

    # Risk score (lower = less risky) 0–10
    risk_score = _clamp(
        (p.volatility_20d or 30) / 5 +  # high vol = risky
        max(0, 5 - p.atr_14 / c * 100 if p.atr_14 else 5) +  # low ATR = safe
        (p.distribution_days_20 or 0) * 0.5,
        0, 10
    )

    # Position sizing: Kelly-inspired, capped
    max_alloc = MAX_ALLOC_BY_CLASS.get(classification, 2.0)
    if risk_pct > 0:
        # Risk 1% of portfolio per position
        raw_size = 0.01 / risk_pct * 100   # as %
        position_size = min(raw_size, max_alloc)
    else:
        position_size = 2.0

    return {
        "atr_14":           atr,
        "atr_pct":          atr / c * 100,
        "volatility_20d":   p.volatility_20d,
        "risk_score":       risk_score,
        "position_size_pct": position_size,
        "max_portfolio_alloc": max_alloc,
        "entry_price":      entry,
        "ideal_buy_zone_lo": buy_lo,
        "ideal_buy_zone_hi": buy_hi,
        "breakout_level":   p.high_52w,
        "pivot_price":      pivot,
        "stop_loss":        stop_loss,
        "atr_stop":         atr_stop,
        "trailing_stop":    trailing_stop,
        "target_price":     target,
        "expected_upside_pct": reward_pct * 100,
        "risk_reward_ratio": rr,
    }


# ─── 12. Alert Triggers ───────────────────────────────────────────────────────
def detect_alerts(p: PriceData, prev_score: float | None, stage: int) -> list[str]:
    """Return list of alert_type strings that fired on this data point."""
    alerts: list[str] = []

    # 52-week high breakout
    if p.high_52w and p.close >= p.high_52w * 0.999:
        alerts.append("HIGH_52W_BREAKOUT")
        alerts.append("NEW_52W_HIGH")

    # SMA reclaims (price crossed back above MA from below)
    if p.sma_50 and p.close > p.sma_50:
        alerts.append("SMA50_RECLAIM")
    if p.sma_150 and p.close > p.sma_150:
        alerts.append("SMA150_RECLAIM")
    if p.sma_200 and p.close > p.sma_200:
        alerts.append("SMA200_RECLAIM")

    # Stage 2 breakout
    if stage == 2:
        alerts.append("STAGE2_BREAKOUT")

    # RS breakout
    if p.rs_breakout:
        alerts.append("RS_BREAKOUT")

    # Pocket pivot
    if p.is_pocket_pivot:
        alerts.append("POCKET_PIVOT")

    # VCP completion
    if p.active_pattern == "VCP" and (p.pattern_maturity or 0) >= 90:
        alerts.append("VCP_COMPLETE")
    elif p.active_pattern and (p.pattern_maturity or 0) >= 85:
        alerts.append("NEW_BREAKOUT")

    # Heavy accumulation: up vol ratio high + pocket pivot
    if (p.up_vol_ratio or 0) >= 0.65 and p.is_pocket_pivot:
        alerts.append("HEAVY_ACCUM")

    # Heavy distribution
    if p.distribution_days_20 >= 4:
        alerts.append("HEAVY_DIST")

    # Trend deterioration: score dropped significantly
    if prev_score is not None and p.prev_technical_score is not None:
        if p.prev_technical_score - prev_score >= 15:  # 15-point drop
            alerts.append("TREND_DETERIORATION")

    return list(dict.fromkeys(alerts))  # deduplicate preserving order


# ─── 13. Main Scoring Entry Point ────────────────────────────────────────────
def score_stock(p: PriceData) -> ScoringResult:
    """
    Full pipeline: OHLCV + indicators → ScoringResult.
    Call once per stock per day after market close.
    """
    result = ScoringResult(isin=p.isin)

    # Minervini
    criteria, count = check_minervini_template(p)
    result.minervini_criteria = criteria
    result.minervini_count    = count

    # Stage
    stage = compute_stage(p)
    result.stage = stage

    # Component scores
    trend_s    = compute_trend_score(p, count, stage)
    rs_s       = compute_rs_score(p)
    momentum_s = compute_momentum_score(p)
    volume_s   = compute_volume_score(p)
    pattern_s  = compute_pattern_score(p)

    result.trend_score    = round(trend_s, 1)
    result.rs_score       = round(rs_s, 1)
    result.momentum_score = round(momentum_s, 1)
    result.volume_score   = round(volume_s, 1)
    result.pattern_score  = round(pattern_s, 1)

    # Technical score
    tech = compute_technical_score(trend_s, rs_s, momentum_s, volume_s, pattern_s)
    result.technical_score = round(tech, 1)

    # Conviction
    conv = compute_conviction_score(
        tech_score=tech,
        minervini_count=count,
        stage=stage,
        rs_score=rs_s,
        rs_breakout=p.rs_breakout,
        rs_new_high=p.rs_new_high,
        is_pocket_pivot=p.is_pocket_pivot,
        distribution_days=p.distribution_days_20,
    )
    result.conviction_score = round(conv, 1)

    # Classification & Signal
    cls    = classify_stock(conv)
    signal = derive_signal(cls, stage, p.distribution_days_20, count)
    result.classification = cls
    result.signal         = signal

    # Risk & Levels
    levels = compute_risk_levels(p, cls)
    for k, v in levels.items():
        setattr(result, k, round(v, 2) if v is not None else None)

    # Alert triggers
    result.alert_triggers = detect_alerts(p, conv, stage)

    return result
