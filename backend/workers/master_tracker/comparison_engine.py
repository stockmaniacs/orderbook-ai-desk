"""
Comparison Engine — Master Tracker Worker.

Core logic: given expected (QuarterlyTarget) and actual (QuarterlyActual)
numbers, assign GREEN / YELLOW / RED to every metric and an overall verdict.

Thresholds (tuned for Indian listed companies):
  Revenue   GREEN >= +2%  /  YELLOW -3% to +2%  /  RED < -3%
  EBITDA    GREEN >= +2%  /  YELLOW -4% to +2%  /  RED < -4%
  Margin    GREEN >= +50bps / YELLOW -50 to +50bps / RED < -50bps
  PAT       GREEN >= 0%   /  YELLOW -8% to 0%   /  RED < -8%
  OB        GREEN >= 0%   /  YELLOW -5% to 0%   /  RED < -5%
  Capex     beat = below expected (spending less than guided = YELLOW unless severe miss)
  Guidance  GREEN = upgrade / YELLOW = maintained / RED = cut
  Promoter  GREEN = increasing + no new pledges / YELLOW = stable / RED = selling or pledging
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Signal = Literal["GREEN", "YELLOW", "RED", "NA"]


# ─── Thresholds (all as % of expected value) ─────────────────────────────────
REVENUE_GREEN_PCT   =  2.0   # actual >= expected + 2%
REVENUE_RED_PCT     = -3.0   # actual < expected - 3%

EBITDA_GREEN_PCT    =  2.0
EBITDA_RED_PCT      = -4.0

PAT_GREEN_PCT       =  0.0
PAT_RED_PCT         = -8.0

ORDER_BOOK_GREEN_PCT=  0.0   # in line or better
ORDER_BOOK_RED_PCT  = -5.0

MARGIN_GREEN_BPS    =  50.0  # margin 50 bps above expectation
MARGIN_RED_BPS      = -50.0


@dataclass
class ComparisonResult:
    revenue_signal:     Signal = "NA"
    ebitda_signal:      Signal = "NA"
    margin_signal:      Signal = "NA"
    pat_signal:         Signal = "NA"
    order_book_signal:  Signal = "NA"
    capex_signal:       Signal = "NA"
    guidance_signal:    Signal = "NA"
    promoter_signal:    Signal = "NA"
    overall_signal:     Signal = "NA"

    revenue_beat_pct:     float | None = None
    ebitda_beat_pct:      float | None = None
    margin_delta_bps:     float | None = None
    pat_beat_pct:         float | None = None
    order_book_beat_pct:  float | None = None

    beat_count:    int = 0
    miss_count:    int = 0
    in_line_count: int = 0

    verdict: str = "NA"  # STRONG_BEAT / BEAT / IN_LINE / MISS / STRONG_MISS


def _pct_beat(actual: float | None, expected: float | None) -> float | None:
    """Return (actual - expected) / expected * 100, or None if data missing."""
    if actual is None or expected is None or expected == 0:
        return None
    return (actual - expected) / abs(expected) * 100


def _classify_pct(beat_pct: float | None, green_pct: float, red_pct: float) -> Signal:
    if beat_pct is None:
        return "NA"
    if beat_pct >= green_pct:
        return "GREEN"
    if beat_pct < red_pct:
        return "RED"
    return "YELLOW"


def compute_comparison(
    *,
    # Actual values
    actual_revenue:    float | None,
    actual_ebitda:     float | None,
    actual_ebitda_margin: float | None,
    actual_pat:        float | None,
    actual_order_book: float | None,
    actual_capex:      float | None,
    # Expected values
    exp_revenue:       float | None,
    exp_ebitda:        float | None,
    exp_ebitda_margin: float | None,
    exp_pat:           float | None,
    exp_order_book:    float | None,
    exp_capex:         float | None,
    # Guidance
    guidance_revised:  bool  = False,
    guidance_delta_pct: float | None = None,
    # Promoter
    promoter_change:   float | None = None,   # + = buying, - = selling
    pledged_change:    float | None = None,   # + = more pledged (bad)
) -> ComparisonResult:
    """
    Core comparison function. Returns a ComparisonResult with per-metric signals.
    """
    r = ComparisonResult()

    # ── Revenue ──────────────────────────────────────────────────────────────
    r.revenue_beat_pct = _pct_beat(actual_revenue, exp_revenue)
    r.revenue_signal   = _classify_pct(r.revenue_beat_pct, REVENUE_GREEN_PCT, REVENUE_RED_PCT)

    # ── EBITDA ───────────────────────────────────────────────────────────────
    r.ebitda_beat_pct = _pct_beat(actual_ebitda, exp_ebitda)
    r.ebitda_signal   = _classify_pct(r.ebitda_beat_pct, EBITDA_GREEN_PCT, EBITDA_RED_PCT)

    # ── Margins (in basis points: 100 bps = 1%) ───────────────────────────────
    if actual_ebitda_margin is not None and exp_ebitda_margin is not None:
        r.margin_delta_bps = (actual_ebitda_margin - exp_ebitda_margin) * 100
        if r.margin_delta_bps >= MARGIN_GREEN_BPS:
            r.margin_signal = "GREEN"
        elif r.margin_delta_bps < MARGIN_RED_BPS:
            r.margin_signal = "RED"
        else:
            r.margin_signal = "YELLOW"

    # ── PAT ──────────────────────────────────────────────────────────────────
    r.pat_beat_pct = _pct_beat(actual_pat, exp_pat)
    r.pat_signal   = _classify_pct(r.pat_beat_pct, PAT_GREEN_PCT, PAT_RED_PCT)

    # ── Order Book ────────────────────────────────────────────────────────────
    r.order_book_beat_pct = _pct_beat(actual_order_book, exp_order_book)
    r.order_book_signal   = _classify_pct(
        r.order_book_beat_pct, ORDER_BOOK_GREEN_PCT, ORDER_BOOK_RED_PCT
    )

    # ── Capex (spending < expected is neutral; > 50% miss = concern) ──────────
    capex_beat = _pct_beat(actual_capex, exp_capex)
    if capex_beat is None:
        r.capex_signal = "NA"
    elif capex_beat > 20:
        r.capex_signal = "RED"       # significantly over budget
    elif capex_beat < -30:
        r.capex_signal = "YELLOW"    # under-spending might signal execution delay
    else:
        r.capex_signal = "GREEN"

    # ── Guidance ──────────────────────────────────────────────────────────────
    if not guidance_revised:
        r.guidance_signal = "YELLOW"   # no change
    elif guidance_delta_pct is not None:
        if guidance_delta_pct >= 5:
            r.guidance_signal = "GREEN"
        elif guidance_delta_pct <= -10:
            r.guidance_signal = "RED"
        else:
            r.guidance_signal = "YELLOW"

    # ── Promoter ──────────────────────────────────────────────────────────────
    prom_score = 0
    if promoter_change is not None:
        if promoter_change > 0.5:  prom_score += 1    # buying
        elif promoter_change < -1: prom_score -= 1    # selling
    if pledged_change is not None:
        if pledged_change > 1:    prom_score -= 2     # pledging more = red flag
        elif pledged_change > 0.5: prom_score -= 1
        elif pledged_change < -1:  prom_score += 1    # reducing pledge = positive
    if prom_score >= 1:   r.promoter_signal = "GREEN"
    elif prom_score <= -1: r.promoter_signal = "RED"
    else:                  r.promoter_signal = "YELLOW"

    # ── Count beats / misses ──────────────────────────────────────────────────
    scored = [
        r.revenue_signal, r.ebitda_signal, r.margin_signal,
        r.pat_signal, r.order_book_signal,
    ]
    r.beat_count    = scored.count("GREEN")
    r.miss_count    = scored.count("RED")
    r.in_line_count = scored.count("YELLOW")

    # ── Overall signal ────────────────────────────────────────────────────────
    if r.miss_count >= 3 or (r.miss_count == 2 and r.beat_count == 0):
        r.overall_signal = "RED"
    elif r.beat_count >= 3:
        r.overall_signal = "GREEN"
    else:
        r.overall_signal = "YELLOW"

    # ── Verdict ───────────────────────────────────────────────────────────────
    score = r.beat_count - r.miss_count
    if score >= 3:    r.verdict = "STRONG_BEAT"
    elif score >= 1:  r.verdict = "BEAT"
    elif score == 0:  r.verdict = "IN_LINE"
    elif score >= -1: r.verdict = "MISS"
    else:             r.verdict = "STRONG_MISS"

    return r


# ─── Alert generation ─────────────────────────────────────────────────────────
@dataclass
class Alert:
    alert_type:     str
    severity:       str
    title:          str
    description:    str
    data_snapshot:  dict = field(default_factory=dict)


def generate_alerts(
    isin: str,
    company_name: str,
    comparison: ComparisonResult,
    consecutive_red: int,
    fiscal_year: int,
    quarter: str,
    *,
    # For thesis check
    prev_signal:         str | None = None,
    guidance_delta_pct:  float | None = None,
    guidance_revised:    bool = False,
    promoter_change:     float | None = None,
    pledged_change:      float | None = None,
    margin_delta_bps:    float | None = None,
    order_book_beat_pct: float | None = None,
    # Technical
    technical_trend:     str | None = None,
    pct_from_52w_high:   float | None = None,
) -> list[Alert]:
    """
    Scan comparison result and generate alerts.
    Returns list of Alert objects to persist.
    """
    alerts: list[Alert] = []
    qstr = f"{quarter} FY{str(fiscal_year)[-2:]}"

    # ── Thesis deteriorating (2+ consecutive RED) ─────────────────────────────
    if consecutive_red >= 2 and comparison.overall_signal == "RED":
        alerts.append(Alert(
            alert_type="THESIS_DETERIORATING",
            severity="HIGH",
            title=f"⚠ Thesis Deteriorating — {consecutive_red} Consecutive Red Quarters",
            description=(
                f"{company_name} has missed expectations for {consecutive_red} quarters in a row "
                f"({qstr} overall: {comparison.verdict}). Core thesis may need revisiting."
            ),
            data_snapshot={
                "consecutive_red": consecutive_red,
                "current_verdict": comparison.verdict,
                "miss_count": comparison.miss_count,
                "metrics_red": [
                    m for m, s in [
                        ("Revenue", comparison.revenue_signal),
                        ("EBITDA", comparison.ebitda_signal),
                        ("Margin", comparison.margin_signal),
                        ("PAT", comparison.pat_signal),
                    ] if s == "RED"
                ],
            },
        ))

    # ── Strong beat — thesis improving ───────────────────────────────────────
    if comparison.verdict == "STRONG_BEAT":
        alerts.append(Alert(
            alert_type="OUTPERFORMING",
            severity="LOW",
            title=f"✅ Strong Beat — {company_name} {qstr}",
            description=(
                f"{company_name} beat on {comparison.beat_count}/5 metrics in {qstr}. "
                f"Revenue: {comparison.revenue_beat_pct:+.1f}% | PAT: {comparison.pat_beat_pct:+.1f}%."
            ),
            data_snapshot={
                "beat_count": comparison.beat_count,
                "revenue_beat_pct": comparison.revenue_beat_pct,
                "pat_beat_pct": comparison.pat_beat_pct,
                "verdict": comparison.verdict,
            },
        ))

    # ── Guidance cut ─────────────────────────────────────────────────────────
    if guidance_revised and guidance_delta_pct is not None and guidance_delta_pct <= -10:
        alerts.append(Alert(
            alert_type="GUIDANCE_CUT",
            severity="HIGH",
            title=f"🔻 Guidance Cut {guidance_delta_pct:.1f}% — {company_name}",
            description=(
                f"Management cut guidance by {abs(guidance_delta_pct):.1f}% in {qstr}. "
                f"Watch for further cuts if macro headwinds persist."
            ),
            data_snapshot={"guidance_revision_pct": guidance_delta_pct, "quarter": qstr},
        ))
    elif guidance_revised and guidance_delta_pct is not None and guidance_delta_pct >= 10:
        alerts.append(Alert(
            alert_type="GUIDANCE_UPGRADE",
            severity="LOW",
            title=f"⬆ Guidance Raised +{guidance_delta_pct:.1f}% — {company_name}",
            description=(
                f"Management upgraded guidance by {guidance_delta_pct:.1f}% in {qstr}."
            ),
            data_snapshot={"guidance_revision_pct": guidance_delta_pct},
        ))

    # ── Margin compression ────────────────────────────────────────────────────
    if margin_delta_bps is not None and margin_delta_bps <= -150:
        alerts.append(Alert(
            alert_type="MARGIN_COMPRESSION",
            severity="HIGH",
            title=f"📉 Margin Compressed {margin_delta_bps:.0f} bps — {company_name}",
            description=(
                f"EBITDA margin fell {abs(margin_delta_bps):.0f} bps below expectation in {qstr}. "
                f"Monitor input costs and pricing power."
            ),
            data_snapshot={"margin_delta_bps": margin_delta_bps},
        ))

    # ── Margin expansion ─────────────────────────────────────────────────────
    if margin_delta_bps is not None and margin_delta_bps >= 150:
        alerts.append(Alert(
            alert_type="MARGIN_EXPANSION",
            severity="LOW",
            title=f"📈 Margin Expanded +{margin_delta_bps:.0f} bps — {company_name}",
            description=f"EBITDA margin exceeded expectation by {margin_delta_bps:.0f} bps in {qstr}.",
            data_snapshot={"margin_delta_bps": margin_delta_bps},
        ))

    # ── Promoter pledging ─────────────────────────────────────────────────────
    if pledged_change is not None and pledged_change > 2:
        alerts.append(Alert(
            alert_type="PROMOTER_PLEDGING",
            severity="HIGH",
            title=f"🚨 Promoter Pledging Increased — {company_name}",
            description=(
                f"Promoter pledging increased by {pledged_change:.1f}% in {qstr}. "
                f"This is a key risk indicator — monitor closely."
            ),
            data_snapshot={"pledged_change_pct": pledged_change},
        ))

    # ── Promoter buying ───────────────────────────────────────────────────────
    if promoter_change is not None and promoter_change > 1:
        alerts.append(Alert(
            alert_type="PROMOTER_BUY",
            severity="LOW",
            title=f"👍 Promoter Buying — {company_name}",
            description=f"Promoter holding increased by {promoter_change:.1f}% in {qstr} — bullish signal.",
            data_snapshot={"promoter_change_pct": promoter_change},
        ))

    # ── Order book decline ────────────────────────────────────────────────────
    if order_book_beat_pct is not None and order_book_beat_pct <= -10:
        alerts.append(Alert(
            alert_type="ORDER_BOOK_DECLINE",
            severity="MEDIUM",
            title=f"📋 Order Book Below Target — {company_name}",
            description=(
                f"Order book came in {abs(order_book_beat_pct):.1f}% below expectations in {qstr}. "
                f"Watch for revenue guidance impact next quarter."
            ),
            data_snapshot={"order_book_beat_pct": order_book_beat_pct},
        ))

    # ── Technical breakdown ───────────────────────────────────────────────────
    if technical_trend == "DOWNTREND" and pct_from_52w_high is not None and pct_from_52w_high < -30:
        alerts.append(Alert(
            alert_type="TECHNICAL_BREAKDOWN",
            severity="MEDIUM",
            title=f"📊 Technical Breakdown — {company_name}",
            description=(
                f"{company_name} is in a downtrend and {abs(pct_from_52w_high):.1f}% below its 52-week high. "
                f"Consider reviewing position size."
            ),
            data_snapshot={"pct_from_52w_high": pct_from_52w_high, "trend": technical_trend},
        ))

    return alerts


# ─── Technical score computation ──────────────────────────────────────────────
def compute_technical_score(
    *,
    above_sma_50:       bool | None,
    above_sma_200:      bool | None,
    golden_cross:       bool | None,
    death_cross:        bool | None,
    rsi_14:             float | None,
    macd_histogram:     float | None,
    pct_from_52w_high:  float | None,
    volume_vs_ma:       float | None = None,  # volume / volume_ma20
) -> tuple[float, str]:
    """
    Returns (score 0–100, trend label).
    Score > 65 = UPTREND, 40–65 = SIDEWAYS, < 40 = DOWNTREND.
    """
    score = 50.0  # neutral start

    # Moving averages (most weight)
    if above_sma_200 is True:  score += 15
    elif above_sma_200 is False: score -= 15
    if above_sma_50 is True:   score += 10
    elif above_sma_50 is False: score -= 10

    # Golden / death cross
    if golden_cross:  score += 10
    if death_cross:   score -= 15

    # RSI
    if rsi_14 is not None:
        if 50 <= rsi_14 <= 70:   score += 8    # healthy bullish momentum
        elif rsi_14 > 80:         score -= 5    # overbought — slight penalty
        elif 30 <= rsi_14 < 50:   score -= 5    # below midline
        elif rsi_14 < 30:         score -= 10   # oversold (not always bad)

    # MACD histogram
    if macd_histogram is not None:
        if macd_histogram > 0:  score += 5
        else:                   score -= 5

    # Distance from 52-week high
    if pct_from_52w_high is not None:
        if pct_from_52w_high >= -10:  score += 5
        elif pct_from_52w_high < -30: score -= 5

    # Volume
    if volume_vs_ma is not None:
        if volume_vs_ma > 1.5:  score += 3     # high volume confirms move

    # Clamp 0–100
    score = max(0.0, min(100.0, score))

    # Determine trend label
    if score >= 65:
        trend = "UPTREND"
    elif score >= 50:
        trend = "SIDEWAYS"
    elif score >= 35:
        trend = "DOWNTREND"
    else:
        trend = "DOWNTREND"

    # Reversal detection
    if above_sma_200 and golden_cross and rsi_14 and rsi_14 > 50:
        if score >= 55:
            trend = "REVERSAL_UP"

    return round(score, 1), trend


# ─── Risk-reward score ────────────────────────────────────────────────────────
def compute_risk_reward(
    *,
    upside_pct:       float | None,
    expected_cagr_3y: float | None,
    conviction_score: float | None,   # 0–100
    consecutive_red:  int = 0,
    overall_signal:   str = "YELLOW",
    technical_score:  float | None = None,
) -> float:
    """
    Returns risk-reward score 0–10.
    10 = very high upside, great thesis, improving technically.
    """
    score = 5.0

    # Upside (each 10% upside = 0.5 pts, up to 3 pts)
    if upside_pct:
        score += min(3.0, upside_pct / 10 * 0.5)

    # CAGR expectation
    if expected_cagr_3y:
        score += min(2.0, expected_cagr_3y / 10 * 0.5)

    # Conviction
    if conviction_score:
        score += (conviction_score - 50) / 50   # -1 to +1

    # Thesis signal
    if overall_signal == "GREEN":    score += 0.5
    elif overall_signal == "RED":    score -= 1.0

    # Consecutive misses (risk factor)
    score -= consecutive_red * 0.5

    # Technical (bonus for uptrend alignment)
    if technical_score:
        score += (technical_score - 50) / 100   # -0.5 to +0.5

    return round(max(0.0, min(10.0, score)), 1)
