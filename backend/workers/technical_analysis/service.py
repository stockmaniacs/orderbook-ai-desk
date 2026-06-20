"""
Service layer — Technical Analysis AI Worker.

Core operations:
  ingest_daily_snapshot()     — persist OHLCV + compute all indicators + run scoring
  run_full_score()            — score a stock and persist profile + levels + alerts
  scan_universe()             — return ranked dashboard
  get_stock_detail()          — full compound view for one stock
  compute_rs_ratings()        — compute IBD-style RS ratings for entire universe
  update_signal_outcomes()    — fill forward returns on historical signals
  compute_market_breadth()    — daily breadth snapshot
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    BreakoutLevel, DailySnapshot, MarketBreadth, PatternDetection,
    RelativeStrength, SignalHistory, TechnicalAlert, TechnicalProfile,
)
from .pattern_detector import DailyBar, scan_all_patterns
from .scoring import PriceData, ScoringResult, score_stock
from .schemas import (
    DashboardStockRow, MarketBreadthOut, PatternOut, ScanFilterIn,
    StockDetailOut, TechnicalDashboardOut,
)

log = logging.getLogger(__name__)

# ── Alert cooldown (days) by type ─────────────────────────────────────────────
ALERT_COOLDOWN_DAYS: dict[str, int] = {
    "NEW_BREAKOUT":       3,
    "VCP_COMPLETE":       7,
    "RS_BREAKOUT":        5,
    "POCKET_PIVOT":       2,
    "SMA50_RECLAIM":      5,
    "SMA150_RECLAIM":     7,
    "SMA200_RECLAIM":     7,
    "HIGH_52W_BREAKOUT":  3,
    "NEW_52W_HIGH":       3,
    "STAGE2_BREAKOUT":    14,
    "HEAVY_ACCUM":        3,
    "HEAVY_DIST":         3,
    "TREND_DETERIORATION": 7,
    "PATTERN_FAILED":     7,
}

ALERT_SEVERITY: dict[str, str] = {
    "NEW_BREAKOUT":        "HIGH",
    "VCP_COMPLETE":        "HIGH",
    "RS_BREAKOUT":         "HIGH",
    "POCKET_PIVOT":        "HIGH",
    "SMA50_RECLAIM":       "MEDIUM",
    "SMA150_RECLAIM":      "HIGH",
    "SMA200_RECLAIM":      "HIGH",
    "HIGH_52W_BREAKOUT":   "HIGH",
    "NEW_52W_HIGH":        "MEDIUM",
    "STAGE2_BREAKOUT":     "HIGH",
    "HEAVY_ACCUM":         "HIGH",
    "HEAVY_DIST":          "HIGH",
    "TREND_DETERIORATION": "HIGH",
    "PATTERN_FAILED":      "MEDIUM",
}

ALERT_TITLES: dict[str, str] = {
    "NEW_BREAKOUT":        "🚀 New Breakout",
    "VCP_COMPLETE":        "🎯 VCP Completion",
    "RS_BREAKOUT":         "⚡ RS Line Breakout",
    "POCKET_PIVOT":        "📌 Pocket Pivot",
    "SMA50_RECLAIM":       "↑ 50 DMA Reclaimed",
    "SMA150_RECLAIM":      "↑ 150 DMA Reclaimed",
    "SMA200_RECLAIM":      "↑ 200 DMA Reclaimed",
    "HIGH_52W_BREAKOUT":   "🏆 52-Week High Breakout",
    "NEW_52W_HIGH":        "📈 New 52-Week High",
    "STAGE2_BREAKOUT":     "🌅 Stage 2 Breakout",
    "HEAVY_ACCUM":         "🏦 Heavy Institutional Accumulation",
    "HEAVY_DIST":          "⚠ Heavy Distribution",
    "TREND_DETERIORATION": "🔴 Trend Deterioration",
    "PATTERN_FAILED":      "✕ Pattern Failed / Invalidated",
}


# ─── Indicator Computation ────────────────────────────────────────────────────
def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ema(closes: list[float], period: int, prev_ema: float | None = None) -> float | None:
    if len(closes) < period:
        return None
    if prev_ema is None:
        # Seed with SMA
        return _sma(closes, period)
    k = 2 / (period + 1)
    return closes[-1] * k + prev_ema * (1 - k)


def _true_range(bar: dict) -> float:
    return max(
        bar["high"] - bar["low"],
        abs(bar["high"] - bar.get("prev_close", bar["close"])),
        abs(bar["low"]  - bar.get("prev_close", bar["close"])),
    )


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i-1]
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_indicators(bars: list[dict]) -> dict:
    """
    Given a list of OHLCV dicts (oldest first), compute all indicators
    for the latest bar. Returns a flat dict of indicator values.
    """
    if not bars:
        return {}

    closes  = [b["close"] for b in bars]
    highs   = [b["high"]  for b in bars]
    lows    = [b["low"]   for b in bars]
    volumes = [b["volume"] for b in bars]
    n = len(bars)
    last = bars[-1]

    result: dict[str, Any] = {}

    # SMAs
    result["sma_10"]  = _sma(closes, 10)
    result["sma_20"]  = _sma(closes, 20)
    result["sma_50"]  = _sma(closes, 50)
    result["sma_150"] = _sma(closes, 150)
    result["sma_200"] = _sma(closes, 200)
    result["wma_30w"] = _sma(closes, 150)  # proxy
    result["ema_20"]  = _ema(closes, 20)
    result["ema_50"]  = _ema(closes, 50)

    c = last["close"]

    result["above_sma_50"]  = c > result["sma_50"]  if result["sma_50"]  else None
    result["above_sma_150"] = c > result["sma_150"] if result["sma_150"] else None
    result["above_sma_200"] = c > result["sma_200"] if result["sma_200"] else None

    if result["sma_50"] and result["sma_150"]:
        result["sma_50_vs_150"] = result["sma_50"] / result["sma_150"] - 1
    if result["sma_150"] and result["sma_200"]:
        result["sma_150_vs_200"] = result["sma_150"] / result["sma_200"] - 1
    if n >= 40 and result["sma_200"]:
        sma200_40 = _sma(closes[:-40], 200) if n >= 240 else None
        if sma200_40:
            result["sma_200_slope_8w"] = (result["sma_200"] - sma200_40) / sma200_40 * 100

    # 52-week levels
    lookback = min(252, n)
    result["high_52w"] = max(highs[-lookback:])
    result["low_52w"]  = min(lows[-lookback:])
    result["pct_from_52w_high"] = (c - result["high_52w"]) / result["high_52w"] * 100
    result["pct_from_52w_low"]  = (c - result["low_52w"])  / result["low_52w"]  * 100
    result["new_52w_high"] = c >= result["high_52w"] * 0.999
    result["new_52w_low"]  = c <= result["low_52w"]  * 1.001

    # RSI
    result["rsi_14"] = _rsi(closes, 14)

    # ATR
    trs = []
    for i in range(1, n):
        trs.append(max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - bars[i-1]["close"]),
            abs(bars[i]["low"]  - bars[i-1]["close"]),
        ))
    result["atr_14"] = sum(trs[-14:]) / 14 if len(trs) >= 14 else None

    # Volatility (20d annualized)
    if n >= 21:
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(n-20, n)]
        result["volatility_20d"] = statistics.stdev(returns) * (252 ** 0.5) * 100 if len(returns) > 1 else None
    else:
        result["volatility_20d"] = None

    # MACD (12, 26, 9)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if ema12 and ema26:
        result["macd"] = ema12 - ema26
        result["macd_signal"] = result["macd"] * 0.9  # placeholder (needs 9d EMA of MACD)
        result["macd_hist"] = result["macd"] - result["macd_signal"]
    else:
        result["macd"] = result["macd_signal"] = result["macd_hist"] = None

    # Volume
    vol20 = int(sum(volumes[-20:]) / 20) if n >= 20 else None
    vol50 = int(sum(volumes[-50:]) / 50) if n >= 50 else None
    result["vol_sma_20"] = vol20
    result["vol_sma_50"] = vol50
    result["vol_ratio"]  = last["volume"] / vol20 if vol20 else None

    # ROC
    if n >= 10:  result["roc_10"] = (c - closes[-10]) / closes[-10] * 100
    if n >= 20:  result["roc_20"] = (c - closes[-20]) / closes[-20] * 100
    if n >= 60:  result["roc_60"] = (c - closes[-60]) / closes[-60] * 100

    # Tight action: range last 5 days
    if n >= 5:
        r5_hi = max(highs[-5:])
        r5_lo = min(lows[-5:])
        result["tight_action_5d"] = (r5_hi - r5_lo) / r5_lo * 100 < 1.5
    else:
        result["tight_action_5d"] = False

    return result


# ─── Core: Ingest daily snapshot ─────────────────────────────────────────────
async def ingest_daily_snapshot(
    db: AsyncSession,
    isin: str,
    snap_date: date,
    ohlcv: dict,    # {open, high, low, close, volume, delivery_pct}
    indicators: dict | None = None,
) -> dict:
    """
    Persist daily snapshot.  If indicators=None, compute from stored history.
    Returns the snapshot row dict.
    """
    # Fetch history for indicator computation
    if indicators is None:
        hist_result = await db.execute(
            select(DailySnapshot)
            .where(DailySnapshot.isin == isin)
            .order_by(DailySnapshot.snap_date.asc())
            .limit(300)
        )
        hist_rows = hist_result.scalars().all()
        bars = [
            {"open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume or 0}
            for r in hist_rows
        ]
        bars.append({**ohlcv})
        indicators = compute_indicators(bars)

    stmt = pg_insert(DailySnapshot).values(
        id=uuid4(),
        isin=isin,
        snap_date=snap_date,
        open=ohlcv.get("open"),
        high=ohlcv.get("high"),
        low=ohlcv.get("low"),
        close=ohlcv.get("close"),
        volume=ohlcv.get("volume"),
        delivery_pct=ohlcv.get("delivery_pct"),
        **{k: v for k, v in indicators.items() if k in DailySnapshot.__table__.columns.keys()},
    ).on_conflict_do_update(
        index_elements=["isin", "snap_date"],
        set_={k: v for k, v in indicators.items() if k in DailySnapshot.__table__.columns.keys()}
    )
    await db.execute(stmt)
    await db.commit()
    return indicators


# ─── Core: Run full score + persist ──────────────────────────────────────────
async def run_full_score(
    db: AsyncSession,
    isin: str,
    price_data: PriceData,
    snap_date: date,
) -> ScoringResult:
    """
    Score a stock, persist TechnicalProfile, BreakoutLevel, alerts, SignalHistory.
    """
    result = score_stock(price_data)

    # Get company name
    profile_q = await db.execute(select(TechnicalProfile).where(TechnicalProfile.isin == isin))
    profile = profile_q.scalar_one_or_none()
    company_name = profile.company_name if profile else isin
    prev_signal = profile.signal if profile else None

    # Upsert TechnicalProfile
    stmt = pg_insert(TechnicalProfile).values(
        id=uuid4(),
        isin=isin,
        company_name=company_name,
        cmp=price_data.close,
        price_date=snap_date,
        trend_score=result.trend_score,
        rs_score=result.rs_score,
        momentum_score=result.momentum_score,
        volume_score=result.volume_score,
        pattern_score=result.pattern_score,
        technical_score=result.technical_score,
        conviction_score=result.conviction_score,
        rs_rating=price_data.rs_rating,
        classification=result.classification,
        signal=result.signal,
        stage=result.stage,
        minervini_count=result.minervini_count,
        active_pattern=price_data.active_pattern,
        pattern_maturity=price_data.pattern_maturity,
        atr_14=result.atr_14,
        atr_pct=result.atr_pct,
        volatility_20d=result.volatility_20d,
        risk_score=result.risk_score,
        position_size_pct=result.position_size_pct,
        max_portfolio_alloc=result.max_portfolio_alloc,
        entry_price=result.entry_price,
        ideal_buy_zone_lo=result.ideal_buy_zone_lo,
        ideal_buy_zone_hi=result.ideal_buy_zone_hi,
        breakout_level=result.breakout_level,
        pivot_price=result.pivot_price,
        stop_loss=result.stop_loss,
        atr_stop=result.atr_stop,
        trailing_stop=result.trailing_stop,
        target_price=result.target_price,
        expected_upside_pct=result.expected_upside_pct,
        risk_reward_ratio=result.risk_reward_ratio,
        scores_updated_at=func.now(),
    ).on_conflict_do_update(
        index_elements=["isin"],
        set_={
            "cmp": price_data.close,
            "price_date": snap_date,
            "trend_score": result.trend_score,
            "rs_score": result.rs_score,
            "momentum_score": result.momentum_score,
            "volume_score": result.volume_score,
            "pattern_score": result.pattern_score,
            "technical_score": result.technical_score,
            "conviction_score": result.conviction_score,
            "rs_rating": price_data.rs_rating,
            "classification": result.classification,
            "signal": result.signal,
            "stage": result.stage,
            "minervini_count": result.minervini_count,
            "active_pattern": price_data.active_pattern,
            "pattern_maturity": price_data.pattern_maturity,
            "atr_14": result.atr_14,
            "atr_pct": result.atr_pct,
            "volatility_20d": result.volatility_20d,
            "risk_score": result.risk_score,
            "position_size_pct": result.position_size_pct,
            "max_portfolio_alloc": result.max_portfolio_alloc,
            "entry_price": result.entry_price,
            "ideal_buy_zone_lo": result.ideal_buy_zone_lo,
            "ideal_buy_zone_hi": result.ideal_buy_zone_hi,
            "breakout_level": result.breakout_level,
            "pivot_price": result.pivot_price,
            "stop_loss": result.stop_loss,
            "atr_stop": result.atr_stop,
            "trailing_stop": result.trailing_stop,
            "target_price": result.target_price,
            "expected_upside_pct": result.expected_upside_pct,
            "risk_reward_ratio": result.risk_reward_ratio,
            "scores_updated_at": func.now(),
        }
    )
    await db.execute(stmt)

    # Persist BreakoutLevel (new record each day, invalidate old)
    await db.execute(
        update(BreakoutLevel)
        .where(BreakoutLevel.isin == isin, BreakoutLevel.is_current == True)
        .values(is_current=False)
    )
    db.add(BreakoutLevel(
        isin=isin,
        calc_date=snap_date,
        is_current=True,
        cmp=price_data.close,
        entry_price=result.entry_price,
        ideal_buy_zone_lo=result.ideal_buy_zone_lo,
        ideal_buy_zone_hi=result.ideal_buy_zone_hi,
        breakout_level=result.breakout_level,
        pivot_price=result.pivot_price,
        stop_loss=result.stop_loss,
        atr_stop=result.atr_stop,
        trailing_stop=result.trailing_stop,
        target_price=result.target_price,
        expected_upside_pct=result.expected_upside_pct,
        risk_pct=(price_data.close - (result.stop_loss or 0)) / price_data.close if result.stop_loss else None,
        risk_reward_ratio=result.risk_reward_ratio,
        position_size_pct=result.position_size_pct,
        max_portfolio_alloc=result.max_portfolio_alloc,
    ))

    # Persist signal change to history
    if prev_signal != result.signal:
        db.add(SignalHistory(
            isin=isin,
            signal_date=snap_date,
            signal=result.signal,
            classification=result.classification,
            pattern_type=price_data.active_pattern,
            technical_score=result.technical_score,
            rs_rating=price_data.rs_rating,
            trend_score=result.trend_score,
            momentum_score=result.momentum_score,
            volume_score=result.volume_score,
            conviction_score=result.conviction_score,
            price_at_signal=price_data.close,
            entry_price=result.entry_price,
            stop_loss=result.stop_loss,
            target_price=result.target_price,
            risk_reward_ratio=result.risk_reward_ratio,
        ))

    # Generate alerts
    await _generate_alerts(db, isin, company_name, snap_date, price_data.close,
                           result, result.alert_triggers)

    await db.commit()
    return result


# ─── Alert Generation ─────────────────────────────────────────────────────────
async def _generate_alerts(
    db: AsyncSession,
    isin: str,
    company_name: str,
    alert_date: date,
    price: float,
    result: ScoringResult,
    triggers: list[str],
) -> None:
    if not triggers:
        return

    for alert_type in triggers:
        cooldown = ALERT_COOLDOWN_DAYS.get(alert_type, 3)
        since = alert_date - timedelta(days=cooldown)
        existing = await db.execute(text("""
            SELECT 1 FROM ta_alerts
            WHERE isin = :isin AND alert_type = :atype AND alert_date >= :since
            LIMIT 1
        """), {"isin": isin, "atype": alert_type, "since": since})
        if existing.fetchone():
            continue

        db.add(TechnicalAlert(
            isin=isin,
            company_name=company_name,
            alert_date=alert_date,
            alert_type=alert_type,
            severity=ALERT_SEVERITY.get(alert_type, "MEDIUM"),
            title=f"{ALERT_TITLES.get(alert_type, alert_type)} — {company_name}",
            description=_alert_description(alert_type, company_name, price, result),
            price_at_alert=price,
            classification_at=result.classification,
            signal_at=result.signal,
            tech_score_at=result.technical_score,
            data_snapshot={
                "stage": result.stage,
                "minervini_count": result.minervini_count,
                "trend_score": result.trend_score,
                "rs_score": result.rs_score,
                "momentum_score": result.momentum_score,
                "volume_score": result.volume_score,
                "conviction_score": result.conviction_score,
                "pattern": result.classification,
            }
        ))


def _alert_description(alert_type: str, name: str, price: float, r: ScoringResult) -> str:
    desc_map = {
        "NEW_BREAKOUT":        f"{name} broke out at ₹{price:.0f}. Tech score {r.technical_score:.0f}/100. RR: {r.risk_reward_ratio:.1f}x.",
        "VCP_COMPLETE":        f"VCP pattern complete for {name}. Pivot ₹{r.pivot_price:.0f}, stop ₹{r.stop_loss:.0f}. {r.minervini_count}/8 Minervini criteria.",
        "RS_BREAKOUT":         f"{name} RS line making new high — outperforming Nifty 500. Strong institutional interest.",
        "POCKET_PIVOT":        f"Pocket pivot detected for {name} at ₹{price:.0f}. Volume surge on up day from key support.",
        "SMA50_RECLAIM":       f"{name} reclaimed 50 DMA at ₹{price:.0f}. Stage {r.stage}.",
        "SMA150_RECLAIM":      f"{name} reclaimed 150 DMA — constructive action. {r.minervini_count}/8 Minervini.",
        "SMA200_RECLAIM":      f"{name} reclaimed 200 DMA — key trend change. Watch for Stage 2 confirmation.",
        "HIGH_52W_BREAKOUT":   f"{name} broke 52-week high. Elite pattern: {r.classification}. Entry ₹{r.entry_price:.0f}, target ₹{r.target_price:.0f}.",
        "STAGE2_BREAKOUT":     f"{name} entering Stage 2 advance. All SMAs aligned. Conviction {r.conviction_score:.0f}/100.",
        "HEAVY_ACCUM":         f"Heavy institutional accumulation in {name}. Pocket pivot + high up/down volume ratio.",
        "HEAVY_DIST":          f"⚠ Distribution detected in {name}. Review thesis. Stop loss: ₹{r.stop_loss:.0f}.",
        "TREND_DETERIORATION": f"🔴 Technical deterioration in {name}. Score dropped significantly. Stage {r.stage}.",
    }
    return desc_map.get(alert_type, f"{alert_type} triggered for {name} at ₹{price:.0f}.")


# ─── Pattern persistence ──────────────────────────────────────────────────────
async def persist_patterns(
    db: AsyncSession,
    isin: str,
    bars: list[dict],
    detect_date: date,
) -> list[dict]:
    """Detect patterns and persist. Return list of detected pattern dicts."""
    daily_bars = [
        DailyBar(
            date=b.get("date", detect_date),
            open=b["open"], high=b["high"], low=b["low"],
            close=b["close"], volume=b.get("volume", 0)
        ) for b in bars
    ]

    patterns = scan_all_patterns(daily_bars)
    result_dicts: list[dict] = []

    for pat in patterns:
        # Check if same pattern type already exists in FORMING/COMPLETE state
        existing_q = await db.execute(
            select(PatternDetection).where(
                PatternDetection.isin == isin,
                PatternDetection.pattern_type == pat.pattern_type,
                PatternDetection.status.in_(["FORMING", "COMPLETE"]),
            )
        )
        existing = existing_q.scalar_one_or_none()
        if existing:
            # Update existing
            existing.status = pat.status
            existing.quality_score = pat.quality_score
            existing.depth_pct = pat.depth_pct
            existing.tight_pct = pat.tight_pct
            existing.pivot_price = pat.pivot_price
            existing.buy_zone_lo = pat.buy_zone_lo
            existing.buy_zone_hi = pat.buy_zone_hi
            existing.pattern_stop = pat.pattern_stop
            existing.pattern_data = pat.pattern_data
        else:
            db.add(PatternDetection(
                isin=isin,
                pattern_type=pat.pattern_type,
                status=pat.status,
                detected_date=detect_date,
                depth_pct=pat.depth_pct,
                duration_days=pat.duration_days,
                tight_pct=pat.tight_pct,
                contractions=pat.contractions,
                pivot_price=pat.pivot_price,
                buy_zone_lo=pat.buy_zone_lo,
                buy_zone_hi=pat.buy_zone_hi,
                pattern_stop=pat.pattern_stop,
                pattern_target=pat.pattern_target,
                quality_score=pat.quality_score,
                pattern_data=pat.pattern_data,
            ))
        result_dicts.append({"pattern_type": pat.pattern_type, "status": pat.status,
                              "quality": pat.quality_score, "pivot": pat.pivot_price})

    if patterns:
        await db.commit()
    return result_dicts


# ─── RS Ratings ──────────────────────────────────────────────────────────────
async def compute_rs_ratings(db: AsyncSession, rs_date: date) -> int:
    """
    Compute IBD-style RS Ratings for all stocks in the universe.
    RS = composite of 1m (20%), 3m (20%), 6m (20%), 12m (40%) performance.
    Ranks 1–99 within the universe.
    """
    # Get all profiles with recent snapshots
    result = await db.execute(text("""
        SELECT p.isin,
               (s252.close - COALESCE(s252_start.close, s252.close)) / NULLIF(COALESCE(s252_start.close, s252.close), 0) as r12m,
               (s252.close - COALESCE(s126.close, s252.close))       / NULLIF(COALESCE(s126.close, s252.close), 0)       as r6m,
               (s252.close - COALESCE(s63.close,  s252.close))       / NULLIF(COALESCE(s63.close,  s252.close), 0)       as r3m,
               (s252.close - COALESCE(s21.close,  s252.close))       / NULLIF(COALESCE(s21.close,  s252.close), 0)       as r1m
        FROM ta_profiles p
        JOIN ta_daily_snapshots s252 ON s252.isin = p.isin
            AND s252.snap_date = (SELECT MAX(snap_date) FROM ta_daily_snapshots WHERE isin = p.isin)
        LEFT JOIN ta_daily_snapshots s252_start ON s252_start.isin = p.isin
            AND s252_start.snap_date = (SELECT snap_date FROM ta_daily_snapshots WHERE isin = p.isin
                ORDER BY ABS(EXTRACT(DOY FROM snap_date) - EXTRACT(DOY FROM :rs_date - INTERVAL '252 days')) LIMIT 1)
        LEFT JOIN ta_daily_snapshots s126 ON s126.isin = p.isin
            AND s126.snap_date = (SELECT snap_date FROM ta_daily_snapshots WHERE isin = p.isin
                ORDER BY ABS(EXTRACT(DOY FROM snap_date) - EXTRACT(DOY FROM :rs_date - INTERVAL '126 days')) LIMIT 1)
        LEFT JOIN ta_daily_snapshots s63 ON s63.isin = p.isin
            AND s63.snap_date = (SELECT snap_date FROM ta_daily_snapshots WHERE isin = p.isin
                ORDER BY ABS(EXTRACT(DOY FROM snap_date) - EXTRACT(DOY FROM :rs_date - INTERVAL '63 days')) LIMIT 1)
        LEFT JOIN ta_daily_snapshots s21 ON s21.isin = p.isin
            AND s21.snap_date = (SELECT snap_date FROM ta_daily_snapshots WHERE isin = p.isin
                ORDER BY ABS(EXTRACT(DOY FROM snap_date) - EXTRACT(DOY FROM :rs_date - INTERVAL '21 days')) LIMIT 1)
    """), {"rs_date": rs_date})
    rows = result.fetchall()

    if not rows:
        return 0

    # Composite score
    scored = []
    for r in rows:
        r12m = (r.r12m or 0) * 100
        r6m  = (r.r6m  or 0) * 100
        r3m  = (r.r3m  or 0) * 100
        r1m  = (r.r1m  or 0) * 100
        comp = r12m * 0.40 + r6m * 0.20 + r3m * 0.20 + r1m * 0.20
        scored.append((r.isin, comp))

    scored.sort(key=lambda x: x[1])
    n = len(scored)

    for rank_0, (isin, _) in enumerate(scored):
        rs_rating = int((rank_0 / (n - 1)) * 98) + 1 if n > 1 else 50
        await db.execute(text("""
            UPDATE ta_profiles SET rs_rating = :r WHERE isin = :isin
        """), {"r": rs_rating, "isin": isin})

    await db.commit()
    return n


# ─── Market Breadth ───────────────────────────────────────────────────────────
async def compute_market_breadth(db: AsyncSession, breadth_date: date) -> dict:
    """Compute and persist daily market breadth snapshot."""
    result = await db.execute(text("""
        SELECT
            COUNT(*) as total,
            AVG(CASE WHEN above_sma_50  THEN 100.0 ELSE 0 END) as pct_sma50,
            AVG(CASE WHEN above_sma_150 THEN 100.0 ELSE 0 END) as pct_sma150,
            AVG(CASE WHEN above_sma_200 THEN 100.0 ELSE 0 END) as pct_sma200,
            SUM(CASE WHEN new_52w_high THEN 1 ELSE 0 END) as new_highs,
            SUM(CASE WHEN new_52w_low  THEN 1 ELSE 0 END) as new_lows,
            SUM(CASE WHEN close > LAG(close) OVER (PARTITION BY isin ORDER BY snap_date) THEN 1 ELSE 0 END) as advances,
            SUM(CASE WHEN close < LAG(close) OVER (PARTITION BY isin ORDER BY snap_date) THEN 1 ELSE 0 END) as declines
        FROM ta_daily_snapshots
        WHERE snap_date = :bd
    """), {"bd": breadth_date})
    row = result.fetchone()

    counts_q = await db.execute(text("""
        SELECT classification, COUNT(*) as cnt
        FROM ta_profiles
        GROUP BY classification
    """))
    counts = {r.classification: r.cnt for r in counts_q.fetchall()}

    # Sector scores
    sector_q = await db.execute(text("""
        SELECT sector, AVG(technical_score) as avg_score, COUNT(*) as cnt
        FROM ta_profiles WHERE sector IS NOT NULL
        GROUP BY sector ORDER BY avg_score DESC LIMIT 10
    """))
    sector_scores = {r.sector: round(r.avg_score or 0, 1) for r in sector_q.fetchall()}
    top_sectors = dict(list(sector_scores.items())[:5])

    if row:
        nh = row.new_highs or 0
        nl = row.new_lows or 0
        adv = row.advances or 0
        dec = row.declines or 0
        regime = _classify_regime(
            pct_above_200=row.pct_sma200 or 0,
            nh_nl_ratio=nh/(nh+nl) if (nh+nl) > 0 else 0.5,
            elite_count=counts.get("ELITE_LEADER", 0),
        )

        stmt = pg_insert(MarketBreadth).values(
            id=uuid4(),
            breadth_date=breadth_date,
            total_stocks=row.total,
            pct_above_sma_50=row.pct_sma50,
            pct_above_sma_150=row.pct_sma150,
            pct_above_sma_200=row.pct_sma200,
            new_highs=nh, new_lows=nl,
            nh_nl_ratio=nh/(nh+nl) if (nh+nl) > 0 else None,
            advances=adv, declines=dec,
            ad_ratio=adv/dec if dec > 0 else None,
            elite_leaders_count=counts.get("ELITE_LEADER", 0),
            strong_structure_count=counts.get("STRONG_STRUCTURE", 0),
            emerging_leaders_count=counts.get("EMERGING_LEADER", 0),
            avoid_count=counts.get("AVOID", 0),
            top_sectors=top_sectors,
            sector_scores=sector_scores,
            market_regime=regime,
        ).on_conflict_do_update(
            index_elements=["breadth_date"],
            set_={
                "pct_above_sma_50": row.pct_sma50,
                "pct_above_sma_200": row.pct_sma200,
                "new_highs": nh, "new_lows": nl,
                "advances": adv, "declines": dec,
                "elite_leaders_count": counts.get("ELITE_LEADER", 0),
                "top_sectors": top_sectors,
                "sector_scores": sector_scores,
                "market_regime": regime,
            }
        )
        await db.execute(stmt)
        await db.commit()
    return {"status": "ok", "date": str(breadth_date)}


def _classify_regime(pct_above_200: float, nh_nl_ratio: float, elite_count: int) -> str:
    if pct_above_200 >= 70 and nh_nl_ratio >= 0.70 and elite_count >= 20:
        return "BULL_CONFIRMED"
    elif pct_above_200 >= 55 and nh_nl_ratio >= 0.55:
        return "BULL_UNDER_PRESSURE"
    elif pct_above_200 >= 40:
        return "SIDEWAYS"
    elif pct_above_200 >= 25:
        return "BEAR_RALLY"
    else:
        return "BEAR_CONFIRMED"


# ─── Dashboard ────────────────────────────────────────────────────────────────
async def get_dashboard(db: AsyncSession, filters: ScanFilterIn) -> TechnicalDashboardOut:
    sort_cols = {
        "conviction_score":  TechnicalProfile.conviction_score,
        "rs_rating":         TechnicalProfile.rs_rating,
        "technical_score":   TechnicalProfile.technical_score,
        "market_leader_rank": TechnicalProfile.market_leader_rank,
        "expected_upside_pct": TechnicalProfile.expected_upside_pct,
        "risk_reward_ratio": TechnicalProfile.risk_reward_ratio,
    }
    sort_col = sort_cols.get(filters.sort_by, TechnicalProfile.conviction_score)

    q = select(TechnicalProfile)
    if filters.classification:
        q = q.where(TechnicalProfile.classification == filters.classification)
    if filters.signal:
        q = q.where(TechnicalProfile.signal == filters.signal)
    if filters.sector:
        q = q.where(TechnicalProfile.sector == filters.sector)
    if filters.stage:
        q = q.where(TechnicalProfile.stage == filters.stage)
    if filters.min_rs_rating:
        q = q.where(TechnicalProfile.rs_rating >= filters.min_rs_rating)
    if filters.min_tech_score:
        q = q.where(TechnicalProfile.technical_score >= filters.min_tech_score)
    if filters.has_pattern:
        q = q.where(TechnicalProfile.active_pattern.isnot(None))

    total_q = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_q.scalar() or 0

    q = q.order_by(sort_col.desc().nullslast()).offset(filters.offset).limit(filters.limit)
    rows_q = await db.execute(q)
    profiles = rows_q.scalars().all()

    # Unread alert counts
    alert_count_q = await db.execute(text("""
        SELECT isin, COUNT(*) as cnt FROM ta_alerts WHERE is_read = false GROUP BY isin
    """))
    alert_counts = {r.isin: r.cnt for r in alert_count_q.fetchall()}
    total_unread = sum(alert_counts.values())

    items = [
        DashboardStockRow(
            isin=p.isin,
            symbol_nse=p.symbol_nse,
            company_name=p.company_name,
            sector=p.sector,
            market_cap_cat=p.market_cap_cat,
            technical_score=p.technical_score,
            conviction_score=p.conviction_score,
            rs_rating=p.rs_rating,
            trend_score=p.trend_score,
            momentum_score=p.momentum_score,
            volume_score=p.volume_score,
            classification=p.classification,
            signal=p.signal,
            stage=p.stage,
            minervini_count=p.minervini_count,
            active_pattern=p.active_pattern,
            cmp=p.cmp,
            target_price=p.target_price,
            expected_upside_pct=p.expected_upside_pct,
            risk_reward_ratio=p.risk_reward_ratio,
            position_size_pct=p.position_size_pct,
            sector_rank=p.sector_rank,
            industry_rank=p.industry_rank,
            market_leader_rank=p.market_leader_rank,
            unread_alert_count=alert_counts.get(p.isin, 0),
            price_date=p.price_date,
        )
        for p in profiles
    ]

    # Count classifications
    elite_q = await db.execute(text("SELECT COUNT(*) FROM ta_profiles WHERE classification = 'ELITE_LEADER'"))
    strong_q = await db.execute(text("SELECT COUNT(*) FROM ta_profiles WHERE classification = 'STRONG_STRUCTURE'"))
    emerging_q = await db.execute(text("SELECT COUNT(*) FROM ta_profiles WHERE classification = 'EMERGING_LEADER'"))

    # Latest breadth
    breadth_q = await db.execute(
        select(MarketBreadth).order_by(MarketBreadth.breadth_date.desc()).limit(1)
    )
    breadth = breadth_q.scalar_one_or_none()

    return TechnicalDashboardOut(
        total=total,
        elite_leaders=elite_q.scalar() or 0,
        strong_structure=strong_q.scalar() or 0,
        emerging_leaders=emerging_q.scalar() or 0,
        items=items,
        market_breadth=MarketBreadthOut.model_validate(breadth) if breadth else None,
        unread_alerts=total_unread,
    )


# ─── Stock Detail ─────────────────────────────────────────────────────────────
async def get_stock_detail(db: AsyncSession, isin: str) -> StockDetailOut | None:
    profile_q = await db.execute(select(TechnicalProfile).where(TechnicalProfile.isin == isin))
    profile = profile_q.scalar_one_or_none()
    if not profile:
        return None

    # Latest snapshot
    snap_q = await db.execute(
        select(DailySnapshot).where(DailySnapshot.isin == isin)
        .order_by(DailySnapshot.snap_date.desc()).limit(1)
    )
    snap = snap_q.scalar_one_or_none()

    # 60-day history for charting
    hist_q = await db.execute(
        select(DailySnapshot).where(DailySnapshot.isin == isin)
        .order_by(DailySnapshot.snap_date.desc()).limit(60)
    )
    hist = list(reversed(hist_q.scalars().all()))

    # RS
    rs_q = await db.execute(
        select(RelativeStrength).where(RelativeStrength.isin == isin)
        .order_by(RelativeStrength.rs_date.desc()).limit(1)
    )
    rs = rs_q.scalar_one_or_none()

    # Active patterns
    pat_q = await db.execute(
        select(PatternDetection).where(
            PatternDetection.isin == isin,
            PatternDetection.status.in_(["FORMING", "COMPLETE", "BREAKOUT"])
        ).order_by(PatternDetection.quality_score.desc()).limit(5)
    )
    patterns = pat_q.scalars().all()

    # Current breakout levels
    level_q = await db.execute(
        select(BreakoutLevel).where(BreakoutLevel.isin == isin, BreakoutLevel.is_current == True)
        .order_by(BreakoutLevel.calc_date.desc()).limit(1)
    )
    levels = level_q.scalar_one_or_none()

    # Alerts
    alert_q = await db.execute(
        select(TechnicalAlert).where(TechnicalAlert.isin == isin)
        .order_by(TechnicalAlert.triggered_at.desc()).limit(20)
    )
    alerts = alert_q.scalars().all()

    # Signal history
    sig_q = await db.execute(
        select(SignalHistory).where(SignalHistory.isin == isin)
        .order_by(SignalHistory.signal_date.desc()).limit(20)
    )
    sigs = sig_q.scalars().all()

    from .schemas import (
        TechnicalProfileOut, DailySnapshotOut, RelativeStrengthOut,
        PatternOut, BreakoutLevelOut, TechnicalAlertOut, SignalHistoryOut,
    )

    return StockDetailOut(
        profile=TechnicalProfileOut.model_validate(profile),
        latest_snapshot=DailySnapshotOut.model_validate(snap) if snap else None,
        latest_rs=RelativeStrengthOut.model_validate(rs) if rs else None,
        active_patterns=[PatternOut.model_validate(p) for p in patterns],
        current_levels=BreakoutLevelOut.model_validate(levels) if levels else None,
        recent_alerts=[TechnicalAlertOut.model_validate(a) for a in alerts],
        signal_history=[SignalHistoryOut.model_validate(s) for s in sigs],
        snapshot_history=[DailySnapshotOut.model_validate(h) for h in hist],
        minervini_criteria=[],   # populated by task after scoring
    )


# ─── Update Signal Outcomes ───────────────────────────────────────────────────
async def update_signal_outcomes(db: AsyncSession) -> int:
    """
    For each open signal in ta_signal_history, fill forward returns
    using the latest daily snapshot.
    """
    today = date.today()
    open_sigs_q = await db.execute(
        select(SignalHistory).where(SignalHistory.outcome == None)
        .order_by(SignalHistory.signal_date)
        .limit(500)
    )
    sigs = open_sigs_q.scalars().all()
    updated = 0

    for sig in sigs:
        # Get price at signal + prices 7/30/60/90 days later
        prices = {}
        for days in [7, 30, 60, 90]:
            target_date = sig.signal_date + timedelta(days=days)
            if target_date > today:
                continue
            price_q = await db.execute(text("""
                SELECT close FROM ta_daily_snapshots
                WHERE isin = :isin AND snap_date <= :d
                ORDER BY snap_date DESC LIMIT 1
            """), {"isin": sig.isin, "d": target_date})
            row = price_q.fetchone()
            if row:
                prices[days] = row.close

        if not prices:
            continue

        base = sig.price_at_signal or sig.entry_price
        if not base:
            continue

        updates: dict[str, Any] = {}
        for days, price in prices.items():
            ret = (price - base) / base * 100
            updates[f"price_{days}d"] = price
            updates[f"return_{days}d"] = ret

        if prices.get(90) or prices.get(60):
            latest_price = prices.get(90) or prices.get(60)
            latest_ret   = (latest_price - base) / base * 100 if latest_price else None
            if sig.target_price and latest_price and latest_price >= sig.target_price:
                updates["hit_target"] = True
                updates["outcome"] = "WIN"
            elif sig.stop_loss and latest_price and latest_price <= sig.stop_loss:
                updates["hit_stop"] = True
                updates["outcome"] = "LOSS"
            elif latest_ret is not None:
                updates["outcome"] = "WIN" if latest_ret > 5 else "LOSS" if latest_ret < -5 else "NEUTRAL"

        await db.execute(
            update(SignalHistory).where(SignalHistory.id == sig.id).values(**updates)
        )
        updated += 1

    await db.commit()
    return updated


# ─── Market Leader Ranks ─────────────────────────────────────────────────────
async def update_market_leader_ranks(db: AsyncSession) -> int:
    """
    Rank all stocks by conviction_score descending → market_leader_rank.
    Also compute sector_rank and industry_rank within their peer group.
    """
    # Global rank
    await db.execute(text("""
        UPDATE ta_profiles p
        SET market_leader_rank = ranked.rn
        FROM (
            SELECT isin,
                   ROW_NUMBER() OVER (ORDER BY conviction_score DESC NULLS LAST) as rn
            FROM ta_profiles
        ) ranked
        WHERE p.isin = ranked.isin
    """))

    # Sector rank
    await db.execute(text("""
        UPDATE ta_profiles p
        SET sector_rank = ranked.rn
        FROM (
            SELECT isin,
                   ROW_NUMBER() OVER (PARTITION BY sector ORDER BY conviction_score DESC NULLS LAST) as rn
            FROM ta_profiles WHERE sector IS NOT NULL
        ) ranked
        WHERE p.isin = ranked.isin AND p.sector IS NOT NULL
    """))

    # Industry rank
    await db.execute(text("""
        UPDATE ta_profiles p
        SET industry_rank = ranked.rn
        FROM (
            SELECT isin,
                   ROW_NUMBER() OVER (PARTITION BY industry ORDER BY conviction_score DESC NULLS LAST) as rn
            FROM ta_profiles WHERE industry IS NOT NULL
        ) ranked
        WHERE p.isin = ranked.isin AND p.industry IS NOT NULL
    """))

    await db.commit()
    count_q = await db.execute(text("SELECT COUNT(*) FROM ta_profiles"))
    return count_q.scalar() or 0
