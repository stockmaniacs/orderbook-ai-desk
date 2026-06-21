"""
Opportunity Analyzer — Subcontract Opportunity Worker.

Given a large order win (prime contractor + order details) and the supply-chain
graph, scores each candidate beneficiary and generates:
  - Probability score (0–100): likelihood of winning subcontract work
  - Revenue impact (₹ Cr + % of TTM revenue)
  - Confidence score: evidence quality
  - Overall composite rank score
  - Investment action: STRONG_BUY_TRIGGER → UNLIKELY
  - AI narrative: rationale, risks, catalysts
"""
from __future__ import annotations

import json
import re
from typing import Any

from workers.ai_client import MODEL_FAST, call_ai, parse_json_response

# ─── Theme → subcontract category map ────────────────────────────────────────
# Which product categories are needed for each order theme, with typical spend %
THEME_CATEGORY_MAP: dict[str, dict[str, float]] = {
    "POWER_T&D": {
        "cables": 0.20, "transformers": 0.18, "switchgear": 0.12,
        "conductors": 0.10, "towers": 0.08, "insulators": 0.05,
        "civil_construction": 0.15, "instrumentation": 0.05,
    },
    "RAILWAYS": {
        "signalling": 0.15, "cables": 0.10, "overhead_equipment": 0.08,
        "structural_steel": 0.12, "civil_construction": 0.20,
        "electronics": 0.10, "fabrication": 0.08,
    },
    "ROADS_HIGHWAYS": {
        "civil_construction": 0.35, "structural_steel": 0.15,
        "bitumen": 0.08, "pipes": 0.06, "earthmoving": 0.10,
    },
    "DEFENCE": {
        "electronics": 0.18, "forgings": 0.12, "composites": 0.10,
        "optics": 0.08, "propulsion": 0.12, "software": 0.10,
    },
    "HYDROCARBON": {
        "pipes": 0.18, "valves": 0.10, "pumps": 0.08,
        "heat_exchangers": 0.08, "instrumentation": 0.10,
        "cables": 0.08, "structural_steel": 0.12, "fabrication": 0.10,
    },
    "GREEN_ENERGY": {
        "solar_modules": 0.30, "inverters": 0.12, "cables": 0.12,
        "transformers": 0.10, "structural_steel": 0.08, "civil_construction": 0.10,
    },
    "URBAN_INFRA": {
        "pipes": 0.15, "cables": 0.12, "pumps": 0.08,
        "IT_systems": 0.10, "sensors": 0.08, "civil_construction": 0.25,
    },
    "DATA_CENTRES": {
        "UPS": 0.12, "cooling_systems": 0.10, "cables": 0.10,
        "switchgear": 0.10, "generators": 0.08, "structural_steel": 0.12,
    },
    "WATER_SANITATION": {
        "pipes": 0.22, "pumps": 0.15, "valves": 0.10,
        "chemicals": 0.08, "instrumentation": 0.08, "civil_construction": 0.20,
    },
    "PORTS_WATERWAYS": {
        "structural_steel": 0.15, "cables": 0.10, "crane_services": 0.12,
        "marine_cables": 0.08, "civil_construction": 0.25,
    },
}

# Default for unknown themes
DEFAULT_CATEGORY_MAP = {
    "structural_steel": 0.15, "cables": 0.12, "civil_construction": 0.20,
    "fabrication": 0.10, "instrumentation": 0.08, "pipes": 0.08,
}

# Typical subcontract ratios (% of order value that goes to subs)
THEME_SUBCONTRACT_RATIOS: dict[str, float] = {
    "POWER_T&D": 0.55, "RAILWAYS": 0.50, "ROADS_HIGHWAYS": 0.45,
    "DEFENCE": 0.40, "HYDROCARBON": 0.50, "GREEN_ENERGY": 0.52,
    "URBAN_INFRA": 0.48, "DATA_CENTRES": 0.45, "WATER_SANITATION": 0.50,
    "PORTS_WATERWAYS": 0.42,
}

# ─── Scoring weights ──────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "relationship_strength": 0.30,   # how strong is the supply-chain edge
    "category_fit":          0.25,   # does product match what this order needs
    "revenue_materiality":   0.20,   # % of beneficiary's revenue = more upside
    "order_size_factor":     0.15,   # larger orders = more opportunity
    "historical_accuracy":   0.10,   # track record of past predictions
}


# ─── Scoring formula ──────────────────────────────────────────────────────────
def score_beneficiary(
    *,
    relationship_strength: float,    # 0–1 from graph edge
    revenue_share_pct: float | None, # % beneficiary's rev from prime contractor
    product_category: str | None,
    order_theme: str,
    order_amount_cr: float,
    beneficiary_ttm_rev_cr: float,
    supply_chain_hops: int = 1,
    historical_accuracy: float = 0.5,
) -> dict:
    """
    Compute all scores for one beneficiary candidate.
    Returns score_breakdown dict + derived metrics.
    """
    # 1. Relationship strength (direct from graph edge, penalise tier-2+)
    hop_penalty = 1.0 if supply_chain_hops == 1 else (0.6 if supply_chain_hops == 2 else 0.3)
    rel_score = min(1.0, relationship_strength * hop_penalty)

    # 2. Category fit: does this company's product match what the order needs?
    theme_cats = THEME_CATEGORY_MAP.get(order_theme, DEFAULT_CATEGORY_MAP)
    cat_weight = theme_cats.get(product_category or "", 0.0)
    # Also check partial matches
    if cat_weight == 0 and product_category:
        for theme_cat, w in theme_cats.items():
            if theme_cat in (product_category or "") or (product_category or "") in theme_cat:
                cat_weight = w * 0.7
                break
    category_fit = min(1.0, cat_weight * 3.0)  # normalize to 0–1

    # 3. Revenue materiality: how big is this order relative to beneficiary?
    subcontract_ratio = THEME_SUBCONTRACT_RATIOS.get(order_theme, 0.45)
    # This beneficiary's share of the subcontract pool
    rev_share = min(1.0, (revenue_share_pct or 10.0) / 100.0)
    potential_rev_cr = order_amount_cr * subcontract_ratio * cat_weight * rev_share
    rev_impact_pct = (potential_rev_cr / max(beneficiary_ttm_rev_cr, 1)) * 100

    # Materiality score: 1.0 if potential = 5%+ of revenue
    rev_materiality = min(1.0, rev_impact_pct / 5.0)

    # 4. Order size factor: bigger orders have more subcontracting value
    if order_amount_cr >= 10_000:
        order_factor = 1.0
    elif order_amount_cr >= 2_000:
        order_factor = 0.8
    elif order_amount_cr >= 500:
        order_factor = 0.6
    else:
        order_factor = 0.4

    # 5. Historical accuracy of this relationship type
    hist_score = min(1.0, historical_accuracy)

    # Composite probability score (0–100)
    probability = (
        rel_score          * SCORE_WEIGHTS["relationship_strength"] +
        category_fit       * SCORE_WEIGHTS["category_fit"] +
        rev_materiality    * SCORE_WEIGHTS["revenue_materiality"] +
        order_factor       * SCORE_WEIGHTS["order_size_factor"] +
        hist_score         * SCORE_WEIGHTS["historical_accuracy"]
    ) * 100

    # Confidence score = quality of evidence supporting the relationship
    confidence = min(100.0, rel_score * 70 + hist_score * 30)

    # Overall composite score for ranking
    overall = probability * 0.6 + confidence * 0.3 + min(rev_impact_pct * 2, 10) * 1.0

    # Investment action thresholds
    if overall >= 72 and rev_impact_pct >= 3:
        action = "STRONG_BUY_TRIGGER"
    elif overall >= 55 and rev_impact_pct >= 1.5:
        action = "BUY_TRIGGER"
    elif overall >= 40:
        action = "MONITOR"
    elif overall >= 25:
        action = "WATCH"
    else:
        action = "UNLIKELY"

    return {
        "probability_score":   round(probability, 1),
        "revenue_impact_cr":   round(potential_rev_cr, 2),
        "revenue_impact_pct":  round(rev_impact_pct, 2),
        "confidence_score":    round(confidence, 1),
        "overall_score":       round(overall, 1),
        "investment_action":   action,
        "score_breakdown": {
            "relationship_strength": round(rel_score, 3),
            "category_fit":          round(category_fit, 3),
            "revenue_materiality":   round(rev_materiality, 3),
            "order_size_factor":     round(order_factor, 3),
            "historical_accuracy":   round(hist_score, 3),
            "hop_penalty":           round(hop_penalty, 2),
            "subcontract_ratio":     subcontract_ratio,
        },
    }


# ─── AI narrative generator ───────────────────────────────────────────────────
NARRATIVE_PROMPT = """You are an Indian equity research analyst specializing in supply-chain investing.

A large order has been won by {prime_contractor} (₹{order_amount_cr:,.0f} Cr, {order_theme} sector).
You are assessing whether {beneficiary_name} (ISIN: {beneficiary_isin}) will benefit as a subcontractor.

ORDER DETAILS:
- Prime contractor: {prime_contractor}
- Order value: ₹{order_amount_cr:,.0f} Cr
- Theme: {order_theme}
- Customer: {order_customer}
- Description: {order_description}

BENEFICIARY DETAILS:
- Company: {beneficiary_name}
- Product: {product_category}
- Relationship: {rel_type} (strength: {rel_strength:.0%})
- Estimated subcontract value: ₹{revenue_impact_cr:,.0f} Cr
- Revenue impact: {revenue_impact_pct:.1f}% of TTM revenue
- Probability score: {probability_score:.0f}/100

Write:
1. rationale: 2-3 sentences on WHY this company benefits (cite specific product need + relationship)
2. key_catalysts: 3 specific positive triggers (list of strings)
3. key_risks: 3 specific downside risks (list of strings)

Return JSON only:
{{
  "rationale": "<2-3 sentences>",
  "key_catalysts": ["<catalyst 1>", "<catalyst 2>", "<catalyst 3>"],
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"]
}}
"""


async def generate_beneficiary_narratives(
    beneficiaries: list[dict],
    order: dict,
    model: str = MODEL_FAST,
) -> list[dict]:
    """
    Generate AI narratives for the top N beneficiaries (to save API cost).
    Batch up to 10 per call.
    """
    # Only generate narratives for top beneficiaries (STRONG_BUY or BUY)
    top = [b for b in beneficiaries if b.get("investment_action") in ("STRONG_BUY_TRIGGER", "BUY_TRIGGER")][:10]

    for b in top:
        prompt = NARRATIVE_PROMPT.format(
            prime_contractor=order.get("prime_contractor_name", ""),
            order_amount_cr=float(order.get("order_amount_cr", 0)),
            order_theme=order.get("theme", ""),
            order_customer=order.get("order_customer", ""),
            order_description=(order.get("order_description") or "")[:300],
            beneficiary_name=b.get("beneficiary_name", ""),
            beneficiary_isin=b.get("beneficiary_isin", ""),
            product_category=b.get("product_category", ""),
            rel_type=b.get("relationship_type", ""),
            rel_strength=float(b.get("score_breakdown", {}).get("relationship_strength", 0.5)),
            revenue_impact_cr=float(b.get("revenue_impact_cr", 0)),
            revenue_impact_pct=float(b.get("revenue_impact_pct", 0)),
            probability_score=float(b.get("probability_score", 0)),
        )

        try:
            raw = await call_ai(prompt, model=model, temperature=0.2)
            narrative = parse_json_response(raw)
            b["rationale"] = narrative.get("rationale")
            b["key_catalysts"] = narrative.get("key_catalysts", [])
            b["key_risks"] = narrative.get("key_risks", [])
        except Exception:
            b["rationale"] = f"{b.get('beneficiary_name')} supplies {b.get('product_category')} to {order.get('prime_contractor_name')}."
            b["key_catalysts"] = ["Direct supply relationship", "Large order provides multi-year revenue visibility"]
            b["key_risks"] = ["Competition from other vendors", "Execution risk", "Price negotiation pressure"]

    return beneficiaries


def classify_order_theme(
    order_description: str,
    order_sector: str | None,
    customer_name: str | None,
) -> tuple[str, list[str]]:
    """
    Classify order into a theme based on keywords.
    Returns (primary_theme, sub_themes).
    """
    text = f"{order_description} {order_sector or ''} {customer_name or ''}".lower()

    theme_keywords = {
        "POWER_T&D":       ["transmission", "distribution", "t&d", "substation", "grid", "power line", "400kv", "220kv", "gis"],
        "RAILWAYS":        ["railway", "rail", "metro", "coach", "locomotive", "signalling", "track", "rfid", "irctc", "dmrc"],
        "ROADS_HIGHWAYS":  ["highway", "road", "expressway", "bridge", "flyover", "nhai", "tunnel"],
        "DEFENCE":         ["defence", "military", "army", "navy", "air force", "missile", "radar", "hal ", "drdo", "weapon"],
        "HYDROCARBON":     ["refinery", "petrochemical", "oil", "gas", "ongc", "iocl", "hpcl", "bpcl", "lng", "cracker"],
        "GREEN_ENERGY":    ["solar", "wind", "green hydrogen", "electrolyzer", "renewable", "battery storage"],
        "URBAN_INFRA":     ["smart city", "water supply", "sewage", "municipality", "urban", "sewerage", "amrut"],
        "DATA_CENTRES":    ["data centre", "data center", "hyperscale", "cloud", "colocation"],
        "WATER_SANITATION":["water treatment", "desalination", "sewage treatment", "nwc", "irrigation"],
        "PORTS_WATERWAYS": ["port", "jetty", "berth", "inland waterway", "jnpt", "container terminal"],
    }

    scores: dict[str, int] = {}
    for theme, keywords in theme_keywords.items():
        scores[theme] = sum(1 for kw in keywords if kw in text)

    best_theme = max(scores, key=lambda t: scores[t]) if any(scores.values()) else "INFRASTRUCTURE"

    # Sub-themes: keywords that match
    best_kws = theme_keywords.get(best_theme, [])
    sub_themes = [kw for kw in best_kws if kw in text][:3]

    return best_theme, sub_themes
