"""
Pattern Detector — Technical Analysis AI Worker.

Detects:
  VCP (Volatility Contraction Pattern)
  CUP_HANDLE
  FLAT_BASE
  DOUBLE_BOTTOM
  DARVAS_BOX
  ASCENDING_BASE
  HIGH_TIGHT_FLAG
  RANGE_CONTRACTION

Each detector receives a window of daily bars (list of dicts with
{date, open, high, low, close, volume}) and returns a PatternResult
or None if the pattern is not detected.

All detectors are designed for position-trading timeframes (weeks-months).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class PatternResult:
    pattern_type: str
    status: str          # FORMING / COMPLETE / BREAKOUT
    quality_score: float  # 0–100

    # Geometry
    depth_pct: float | None = None
    duration_days: int | None = None
    tight_pct: float | None = None   # tightness (lower = tighter = better)
    contractions: int | None = None  # VCP-specific

    # Levels
    pivot_price: float | None = None
    buy_zone_lo: float | None = None
    buy_zone_hi: float | None = None
    pattern_stop: float | None = None
    pattern_target: float | None = None

    # Extra metadata
    pattern_data: dict = field(default_factory=dict)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _pct(a: float, b: float) -> float:
    """Percent change from b to a."""
    return (a - b) / b * 100 if b else 0.0


def _high(bars: list[DailyBar]) -> float:
    return max(b.high for b in bars)


def _low(bars: list[DailyBar]) -> float:
    return min(b.low for b in bars)


def _avg_vol(bars: list[DailyBar]) -> float:
    return sum(b.volume for b in bars) / len(bars) if bars else 0.0


def _atr(bar: DailyBar, prev_close: float) -> float:
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def _weekly_bars(bars: list[DailyBar]) -> list[DailyBar]:
    """Aggregate daily bars to weekly."""
    from collections import defaultdict
    weeks: dict[str, list[DailyBar]] = defaultdict(list)
    for b in bars:
        iso = b.date.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        weeks[key].append(b)
    result = []
    for key in sorted(weeks.keys()):
        wk = weeks[key]
        result.append(DailyBar(
            date=wk[-1].date,
            open=wk[0].open,
            high=max(d.high for d in wk),
            low=min(d.low for d in wk),
            close=wk[-1].close,
            volume=sum(d.volume for d in wk),
        ))
    return result


# ─── 1. VCP — Volatility Contraction Pattern ─────────────────────────────────
def detect_vcp(bars: list[DailyBar], min_contractions: int = 3) -> PatternResult | None:
    """
    Minervini VCP: series of price contractions where each swing is smaller
    than the previous, on progressively lighter volume.
    Requires at least 3 contractions over 3-8 weeks.

    Ideal VCP:
    - Base lasts 3–8 weeks
    - Each contraction shallower (e.g. 25% → 15% → 8%)
    - Volume dries up in late contraction
    - Pivot = high of last tight area
    """
    if len(bars) < 15:
        return None

    # Find local swings in last 60 days (max base)
    window = bars[-60:] if len(bars) >= 60 else bars

    # Identify corrections: runs from a high to a subsequent low
    contractions: list[dict] = []
    peak_price = window[0].high
    trough_price = None
    in_contraction = False
    contraction_start = 0

    for i, bar in enumerate(window[1:], 1):
        if not in_contraction:
            if bar.low < peak_price * 0.95:
                in_contraction = True
                trough_price = bar.low
                contraction_start = i
        else:
            if bar.low < trough_price:
                trough_price = bar.low
            if bar.close > peak_price * 0.98:
                # Recovery complete
                depth = _pct(peak_price, trough_price)  # negative → correction depth
                vol_during = _avg_vol(window[contraction_start:i+1])
                contractions.append({
                    "depth_pct": abs(depth),
                    "duration": i - contraction_start,
                    "avg_vol": vol_during,
                    "low": trough_price,
                    "high": peak_price,
                })
                peak_price = bar.close
                in_contraction = False
                trough_price = None

    if len(contractions) < min_contractions:
        return None

    # Validate: each contraction shallower than prior
    contracting = all(
        contractions[i]["depth_pct"] < contractions[i-1]["depth_pct"]
        for i in range(1, len(contractions))
    )
    if not contracting:
        return None

    # Volume contracting in later stages
    vol_contracting = all(
        contractions[i]["avg_vol"] < contractions[i-1]["avg_vol"]
        for i in range(1, len(contractions))
    )

    last = contractions[-1]
    first = contractions[0]

    # Quality scoring
    quality = 50.0
    quality += (len(contractions) - min_contractions) * 8   # more contractions = better
    if contracting:             quality += 20
    if vol_contracting:         quality += 15
    if first["depth_pct"] > last["depth_pct"] * 2.5: quality += 15  # deep-to-tight

    pivot = _high(bars[-10:])
    buy_hi = pivot * 1.05
    pattern_stop = last["low"] * 0.98

    return PatternResult(
        pattern_type="VCP",
        status="COMPLETE" if last["depth_pct"] < 8 else "FORMING",
        quality_score=min(quality, 100),
        depth_pct=first["depth_pct"],
        duration_days=len(window),
        tight_pct=last["depth_pct"],
        contractions=len(contractions),
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=buy_hi,
        pattern_stop=pattern_stop,
        pattern_target=pivot * 1.20,
        pattern_data={
            "contractions": contractions,
            "vol_contracting": vol_contracting,
            "final_depth_pct": last["depth_pct"],
        }
    )


# ─── 2. Cup and Handle ───────────────────────────────────────────────────────
def detect_cup_handle(bars: list[DailyBar]) -> PatternResult | None:
    """
    Classic O'Neil Cup-with-Handle:
    - Cup depth 12–33% over 7–65 weeks
    - Right side of cup reclaims left-side high
    - Handle: shallow (5–12%) consolidation on low volume
    - Pivot at top of handle
    """
    if len(bars) < 35:
        return None

    window = bars[-252:] if len(bars) >= 252 else bars  # max 1 year
    cup_high = _high(window[:len(window)//4])   # left side high
    cup_low  = _low(window[len(window)//4: 3*len(window)//4])

    depth_pct = abs(_pct(cup_high, cup_low))
    if not (12 <= depth_pct <= 50):
        return None

    # Right side should approach left-side high
    right_quarter = window[3*len(window)//4:]
    right_high = _high(right_quarter)
    if right_high < cup_high * 0.95:
        return None   # right side not recovering

    # Handle: last 7–25 days tighter than cup
    handle = bars[-20:] if len(bars) >= 20 else bars[-7:]
    handle_depth = abs(_pct(_high(handle), _low(handle)))
    if handle_depth > 15:
        return None   # handle too deep

    # Volume: lighter in handle than base average
    base_vol = _avg_vol(window[:-20]) if len(window) > 20 else _avg_vol(window)
    handle_vol = _avg_vol(handle)
    vol_dry = handle_vol < base_vol * 0.75

    quality = 50.0
    if 15 <= depth_pct <= 30: quality += 20     # ideal depth
    if handle_depth <= 8:     quality += 15     # tight handle
    if vol_dry:               quality += 15     # volume dries in handle
    quality += max(0, (len(window)//5 - 2) * 3)  # longer base = slightly better

    pivot = _high(handle)
    return PatternResult(
        pattern_type="CUP_HANDLE",
        status="COMPLETE" if right_high >= cup_high * 0.98 else "FORMING",
        quality_score=min(quality, 100),
        depth_pct=depth_pct,
        duration_days=len(window),
        tight_pct=handle_depth,
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=pivot * 1.05,
        pattern_stop=_low(handle) * 0.98,
        pattern_target=pivot + (pivot - cup_low),
        pattern_data={"cup_high": cup_high, "cup_low": cup_low, "handle_depth": handle_depth, "vol_dry": vol_dry}
    )


# ─── 3. Flat Base ────────────────────────────────────────────────────────────
def detect_flat_base(bars: list[DailyBar]) -> PatternResult | None:
    """
    Flat Base: 5–7 week sideways range, depth <15%, tight closes.
    Often a second-stage base after prior advance.
    """
    if len(bars) < 25:
        return None

    window = bars[-35:] if len(bars) >= 35 else bars
    hi = _high(window)
    lo = _low(window)
    depth = abs(_pct(hi, lo))

    if depth > 15 or depth < 3:
        return None

    # Closes should be within 10% range
    closes = [b.close for b in window]
    close_range = (max(closes) - min(closes)) / min(closes) * 100
    if close_range > 12:
        return None

    # Volume dry-up in mid base
    mid = window[len(window)//4: 3*len(window)//4]
    mid_vol = _avg_vol(mid)
    total_vol = _avg_vol(window)
    vol_quiet = mid_vol < total_vol * 0.80

    quality = 55.0
    if depth <= 8:    quality += 20
    if vol_quiet:     quality += 15
    if close_range <= 7: quality += 10

    pivot = hi
    return PatternResult(
        pattern_type="FLAT_BASE",
        status="COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=depth,
        duration_days=len(window),
        tight_pct=close_range,
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=pivot * 1.05,
        pattern_stop=lo * 0.98,
        pattern_target=pivot * 1.15,
        pattern_data={"close_range_pct": close_range, "vol_quiet": vol_quiet}
    )


# ─── 4. Double Bottom ────────────────────────────────────────────────────────
def detect_double_bottom(bars: list[DailyBar]) -> PatternResult | None:
    """
    W-shaped pattern: two lows approximately equal, middle peak,
    breakout on right side above the middle peak.
    """
    if len(bars) < 20:
        return None

    window = bars[-60:] if len(bars) >= 60 else bars
    n = len(window)
    first_third  = window[:n//3]
    second_third = window[n//3: 2*n//3]
    last_third   = window[2*n//3:]

    lo1 = _low(first_third)
    mid_hi = _high(second_third)
    lo2 = _low(last_third)
    right_close = window[-1].close

    # Two lows within 5% of each other
    if abs(lo1 - lo2) / lo1 > 0.05:
        return None

    # Middle peak > lows
    depth = abs(_pct(mid_hi, lo1))
    if depth < 10:
        return None

    quality = 50.0
    if abs(lo1 - lo2) / lo1 < 0.02: quality += 20  # lows very close
    if right_close >= mid_hi * 0.95: quality += 20  # right side approaching pivot
    if depth >= 15: quality += 10

    pivot = mid_hi
    return PatternResult(
        pattern_type="DOUBLE_BOTTOM",
        status="BREAKOUT" if right_close >= mid_hi else "COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=depth,
        duration_days=len(window),
        pivot_price=pivot,
        buy_zone_lo=pivot * 0.99,
        buy_zone_hi=pivot * 1.04,
        pattern_stop=min(lo1, lo2) * 0.97,
        pattern_target=pivot + (pivot - min(lo1, lo2)),
        pattern_data={"lo1": lo1, "lo2": lo2, "mid_hi": mid_hi}
    )


# ─── 5. Darvas Box ───────────────────────────────────────────────────────────
def detect_darvas_box(bars: list[DailyBar]) -> PatternResult | None:
    """
    Nicolas Darvas box: tight price action in a defined box after a breakout move.
    New all-time / multi-year high → consolidation → box top = pivot.
    """
    if len(bars) < 10:
        return None

    window = bars[-30:] if len(bars) >= 30 else bars
    box_hi = _high(window)
    box_lo = _low(window)
    box_range = abs(_pct(box_hi, box_lo))

    if box_range > 15 or box_range < 3:
        return None

    # Recent bars should not breach box boundaries
    recent = window[-5:]
    for b in recent:
        if b.high > box_hi * 1.03 or b.low < box_lo * 0.97:
            return None  # box violated

    quality = 50.0
    if box_range <= 8:  quality += 25
    if box_range <= 5:  quality += 15
    quality += max(0, 10 - len(window) // 3)  # shorter box = cleaner

    return PatternResult(
        pattern_type="DARVAS_BOX",
        status="COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=box_range,
        duration_days=len(window),
        pivot_price=box_hi,
        buy_zone_lo=box_hi,
        buy_zone_hi=box_hi * 1.04,
        pattern_stop=box_lo * 0.98,
        pattern_target=box_hi + (box_hi - box_lo) * 2,
        pattern_data={"box_hi": box_hi, "box_lo": box_lo, "box_range": box_range}
    )


# ─── 6. Ascending Base ───────────────────────────────────────────────────────
def detect_ascending_base(bars: list[DailyBar]) -> PatternResult | None:
    """
    Three pullbacks where each low is higher than prior — stock 'stair-stepping' up.
    Often seen in super strong stocks holding up in a weak market.
    """
    if len(bars) < 30:
        return None

    window = bars[-60:] if len(bars) >= 60 else bars
    weeks = _weekly_bars(window)
    if len(weeks) < 8:
        return None

    # Find three local lows in weekly data
    lows: list[float] = []
    for i in range(1, len(weeks) - 1):
        if weeks[i].low < weeks[i-1].low and weeks[i].low < weeks[i+1].low:
            lows.append(weeks[i].low)

    if len(lows) < 3:
        return None

    # Verify ascending lows
    ascending = all(lows[i] > lows[i-1] for i in range(1, 3))
    if not ascending:
        return None

    depth = abs(_pct(max(w.high for w in weeks), min(lows)))
    quality = 55.0
    if lows[1] > lows[0] * 1.02: quality += 15  # clearly ascending
    if lows[2] > lows[1] * 1.02: quality += 15
    quality += min(10, (len(weeks) - 8))

    pivot = _high(bars[-10:])
    return PatternResult(
        pattern_type="ASCENDING_BASE",
        status="COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=depth,
        duration_days=len(window),
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=pivot * 1.05,
        pattern_stop=lows[-1] * 0.97,
        pattern_target=pivot * 1.20,
        pattern_data={"ascending_lows": lows[:3]}
    )


# ─── 7. High Tight Flag ──────────────────────────────────────────────────────
def detect_high_tight_flag(bars: list[DailyBar]) -> PatternResult | None:
    """
    O'Neil High Tight Flag:
    - Stock doubles in 4–8 weeks (≥100% move)
    - Then consolidates 10–25% in 3–5 weeks on low volume
    - Most powerful pattern but rare
    """
    if len(bars) < 15:
        return None

    flag_window = bars[-25:] if len(bars) >= 25 else bars
    pole_window = bars[-65:-25] if len(bars) >= 65 else bars[:max(1, len(bars)-25)]

    if len(pole_window) < 5:
        return None

    pole_move = _pct(_high(flag_window[:5]), _low(pole_window))
    if pole_move < 70:    # should be ≥70% advance (strict: 100%)
        return None

    flag_depth = abs(_pct(_high(flag_window), _low(flag_window)))
    if flag_depth > 25 or flag_depth < 5:
        return None

    # Flag volume should dry up
    flag_vol = _avg_vol(flag_window)
    pole_vol  = _avg_vol(pole_window)
    vol_dry = flag_vol < pole_vol * 0.70

    quality = 60.0
    if pole_move >= 100: quality += 25
    elif pole_move >= 80: quality += 15
    if flag_depth <= 15: quality += 15
    if vol_dry:          quality += 10

    pivot = _high(flag_window)
    return PatternResult(
        pattern_type="HIGH_TIGHT_FLAG",
        status="COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=flag_depth,
        duration_days=len(flag_window),
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=pivot * 1.05,
        pattern_stop=_low(flag_window) * 0.97,
        pattern_target=pivot * 1.40,   # high tight flags can double again
        pattern_data={"pole_move_pct": pole_move, "flag_depth_pct": flag_depth, "vol_dry": vol_dry}
    )


# ─── 8. Range Contraction ────────────────────────────────────────────────────
def detect_range_contraction(bars: list[DailyBar]) -> PatternResult | None:
    """
    Price ranges narrowing over 3–6 days (inside bars, NR7, NR4).
    Used for precise timing — supplements a larger base pattern.
    """
    if len(bars) < 7:
        return None

    window = bars[-7:]
    ranges = [b.high - b.low for b in window]

    # NR7: today's range smallest in 7 days
    if ranges[-1] > min(ranges):
        return None

    # Measure contraction: last 3 days narrowing
    if not (ranges[-1] < ranges[-2] < ranges[-3]):
        return None

    contraction = (ranges[-3] - ranges[-1]) / ranges[-3] * 100 if ranges[-3] > 0 else 0

    quality = 55.0
    if contraction >= 50: quality += 25
    if contraction >= 70: quality += 10
    if bars[-1].close > bars[-7].close: quality += 10  # price rising in contraction

    pivot = max(b.high for b in window)
    return PatternResult(
        pattern_type="RANGE_CONTRACTION",
        status="COMPLETE",
        quality_score=min(quality, 100),
        depth_pct=None,
        duration_days=7,
        tight_pct=contraction,
        pivot_price=pivot,
        buy_zone_lo=pivot,
        buy_zone_hi=pivot * 1.03,
        pattern_stop=min(b.low for b in window) * 0.99,
        pattern_target=pivot * 1.10,
        pattern_data={"nr7_range": ranges[-1], "contraction_pct": contraction}
    )


# ─── Master Pattern Scan ─────────────────────────────────────────────────────
PATTERN_PRIORITY = [
    "HIGH_TIGHT_FLAG",
    "VCP",
    "CUP_HANDLE",
    "FLAT_BASE",
    "ASCENDING_BASE",
    "DOUBLE_BOTTOM",
    "DARVAS_BOX",
    "RANGE_CONTRACTION",
]

DETECTORS = {
    "HIGH_TIGHT_FLAG":   detect_high_tight_flag,
    "VCP":               detect_vcp,
    "CUP_HANDLE":        detect_cup_handle,
    "FLAT_BASE":         detect_flat_base,
    "ASCENDING_BASE":    detect_ascending_base,
    "DOUBLE_BOTTOM":     detect_double_bottom,
    "DARVAS_BOX":        detect_darvas_box,
    "RANGE_CONTRACTION": detect_range_contraction,
}


def scan_patterns(bars: list[DailyBar]) -> PatternResult | None:
    """
    Run all detectors in priority order and return the highest-priority match.
    Returns None if no pattern detected.
    """
    for pattern_name in PATTERN_PRIORITY:
        try:
            result = DETECTORS[pattern_name](bars)
            if result is not None and result.quality_score >= 50:
                return result
        except Exception:
            continue
    return None


def scan_all_patterns(bars: list[DailyBar]) -> list[PatternResult]:
    """Run all detectors, return all matches (quality ≥ 45), sorted by quality."""
    results: list[PatternResult] = []
    for pattern_name in PATTERN_PRIORITY:
        try:
            result = DETECTORS[pattern_name](bars)
            if result is not None and result.quality_score >= 45:
                results.append(result)
        except Exception:
            continue
    return sorted(results, key=lambda r: r.quality_score, reverse=True)
