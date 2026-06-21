"""
AI Order Flow Analyzer
Generates executive summaries, scenario narratives, and trend verdicts
using Google Gemini 1.5 Pro over aggregated order data.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """
You are a senior equity research analyst at an institutional research desk in India.
Analyse the order flow data for the company below and produce a structured JSON response.

COMPANY: {company_name} (ISIN: {isin})
SECTOR: {sector}

── ORDER BOOK METRICS ───────────────────────────────────────────────
Current Order Book: ₹{current_ob:.0f} Cr
TTM Order Inflows: ₹{ttm_inflows:.0f} Cr
Order Inflow Growth (YoY): {inflow_growth:+.1f}%
Order Book Growth (YoY): {ob_growth:+.1f}%
Order Book / Sales: {ob_to_sales:.2f}x
Bill-to-Book Ratio: {bill_to_book:.2f}x
Order Acceleration Score: {acceleration_score:.0f}/100
Order Momentum: {momentum}
3Y CAGR (Order Book): {cagr_3y}%
Domestic / Export Mix: {domestic_pct:.0f}% / {export_pct:.0f}%

── RECENT ORDERS (last 12 months) ───────────────────────────────────
{recent_orders_text}

── QUARTERLY TREND ──────────────────────────────────────────────────
{quarterly_trend_text}

── SCENARIO PROJECTIONS (4 quarters out) ────────────────────────────
Bull Case Order Book: ₹{bull_case:.0f} Cr
Base Case Order Book: ₹{base_case:.0f} Cr
Bear Case Order Book: ₹{bear_case:.0f} Cr

──────────────────────────────────────────────────────────────────────

Produce ONLY a valid JSON object with these fields. No markdown, no explanation:

{{
  "trend": "IMPROVING | STABLE | DETERIORATING",
  "trend_confidence": 0.0 to 1.0,

  "executive_summary": "3-4 sentence summary of the overall order flow trajectory",

  "pipeline_analysis": "2-3 sentences on the order pipeline strength, diversity, and execution risk",

  "customer_concentration_note": "1-2 sentences on customer concentration risk or diversification",

  "geographic_mix_note": "1-2 sentences on domestic vs export mix and implications",

  "risk_factors": [
    {{"risk": "description", "severity": "HIGH | MEDIUM | LOW"}}
  ],

  "positive_signals": [
    {{"signal": "description", "impact": "HIGH | MEDIUM | LOW"}}
  ],

  "bull_narrative": "2-3 sentences: what has to go right for the bull case to materialise",

  "base_narrative": "2-3 sentences: what the base case assumes and why",

  "bear_narrative": "2-3 sentences: what could go wrong and how bad it gets",

  "ai_verdict": "One crisp sentence (max 25 words): is the order flow IMPROVING, STABLE, or DETERIORATING and why"
}}
"""


async def generate_analysis(
    isin: str,
    company_name: str,
    sector: str,
    metrics: dict[str, Any],
    recent_orders: list[dict],
    quarterly_snapshots: list[dict],
    model: str = "meta-llama/llama-3.3-70b-instruct:free",
) -> dict[str, Any]:
    """
    Generate AI analysis for a company's order book.
    Returns structured dict matching OrderAISummary fields.
    """
    from workers.ai_client import call_ai_sync, parse_json_response  # noqa: PLC0415

    # Format recent orders for the prompt
    orders_text = _format_orders(recent_orders[:15])
    quarterly_text = _format_quarterly(quarterly_snapshots[-8:])

    prompt = ANALYSIS_PROMPT.format(
        company_name=company_name,
        isin=isin,
        sector=sector or "Diversified",
        current_ob=metrics.get("current_order_book_cr") or 0,
        ttm_inflows=metrics.get("ttm_orders_won_cr") or 0,
        inflow_growth=metrics.get("order_inflow_growth_yoy_pct") or 0,
        ob_growth=metrics.get("order_book_growth_yoy_pct") or 0,
        ob_to_sales=metrics.get("order_book_to_sales") or 0,
        bill_to_book=metrics.get("bill_to_book_ratio") or 0,
        acceleration_score=metrics.get("order_acceleration_score") or 0,
        momentum=metrics.get("order_momentum") or "STABLE",
        cagr_3y=metrics.get("order_book_cagr_3y") or "N/A",
        domestic_pct=metrics.get("domestic_pct") or 50,
        export_pct=metrics.get("export_pct") or 50,
        recent_orders_text=orders_text,
        quarterly_trend_text=quarterly_text,
        bull_case=metrics.get("bull_case_ob_cr") or 0,
        base_case=metrics.get("base_case_ob_cr") or 0,
        bear_case=metrics.get("bear_case_ob_cr") or 0,
    )

    try:
        raw = call_ai_sync(prompt, model=model, temperature=0.3)
        data = parse_json_response(raw)
        data["model_version"] = model
        return data

    except json.JSONDecodeError as e:
        logger.error("Gemini returned invalid JSON: %s", e)
        return _fallback_analysis(metrics)
    except Exception as e:
        logger.error("Gemini analysis error: %s", e)
        return _fallback_analysis(metrics)


def _format_orders(orders: list[dict]) -> str:
    lines = []
    for o in orders:
        amt = f"₹{o.get('order_amount_cr', 0):.0f} Cr" if o.get("order_amount_cr") else "Undisclosed"
        customer = o.get("customer_name") or "Undisclosed Customer"
        desc = o.get("project_description") or o.get("headline", "")[:80]
        dt = o.get("announced_date", "")
        lines.append(f"• [{dt}] {amt} from {customer} — {desc}")
    return "\n".join(lines) if lines else "No recent orders found."


def _format_quarterly(snapshots: list[dict]) -> str:
    lines = []
    for s in snapshots:
        q = s.get("quarter", "")
        ob = s.get("closing_order_book_cr", 0) or 0
        new = s.get("new_orders_cr", 0) or 0
        lines.append(f"  {q}: Closing OB ₹{ob:.0f} Cr | New Orders ₹{new:.0f} Cr")
    return "\n".join(lines) if lines else "No quarterly data available."


def _fallback_analysis(metrics: dict) -> dict[str, Any]:
    """Rule-based fallback when Gemini is unavailable."""
    score = metrics.get("order_acceleration_score") or 50
    growth = metrics.get("order_inflow_growth_yoy_pct") or 0
    ob_to_sales = metrics.get("order_book_to_sales") or 0

    if score >= 65 and growth > 10:
        trend = "IMPROVING"
        verdict = "Order flow is improving with accelerating inflows and expanding order book coverage."
    elif score <= 35 or growth < -10:
        trend = "DETERIORATING"
        verdict = "Order flow is deteriorating with declining inflows and shrinking pipeline coverage."
    else:
        trend = "STABLE"
        verdict = "Order flow is stable with steady inflows matching historical run-rate."

    return {
        "trend": trend,
        "trend_confidence": 0.55,
        "executive_summary": (
            f"The company's order book stands at ₹{metrics.get('current_order_book_cr', 0):.0f} Cr, "
            f"representing {ob_to_sales:.1f}x trailing revenues. "
            f"TTM order inflows grew {growth:+.1f}% YoY. "
            f"The overall order momentum is {metrics.get('order_momentum', 'STABLE')}."
        ),
        "pipeline_analysis": "Order pipeline analysis requires AI processing. Data is being queued.",
        "customer_concentration_note": "Customer concentration data available from order history.",
        "geographic_mix_note": (
            f"Domestic orders account for approximately "
            f"{metrics.get('domestic_pct', 50):.0f}% of TTM inflows."
        ),
        "risk_factors": [
            {"risk": "Execution delays on large orders", "severity": "MEDIUM"},
            {"risk": "Customer concentration risk", "severity": "MEDIUM"},
        ],
        "positive_signals": [
            {"signal": "Growing order book coverage ratio", "severity": "HIGH"}
            if ob_to_sales > 2.0
            else {"signal": "Steady order inflows", "impact": "MEDIUM"}
        ],
        "bull_narrative": "Strong macro order cycle and new segment penetration could accelerate growth.",
        "base_narrative": "Steady conversion of existing pipeline at historical win rates assumed.",
        "bear_narrative": "Demand slowdown and competitive pressure could compress margins and win rates.",
        "ai_verdict": verdict,
        "model_version": "fallback_rules",
    }
