"""
AI Researcher — Company Research Worker.
Synthesizes extracted fields into:
  - Investment thesis (SWOT + scenarios + valuation)
  - Bull / Base / Bear cases with expected CAGR
  - Fair value range + target price
  - Confidence score
  - Rating (STRONG_BUY → AVOID)

Uses Gemini Pro for deep synthesis. Only regenerates sections that changed.
"""
from __future__ import annotations

import json
import re
from typing import Any

from workers.ai_client import MODEL_DEEP, call_ai, parse_json_response

# ─── Synthesis prompt ─────────────────────────────────────────────────────────
THESIS_PROMPT = """You are a senior Indian equity research analyst.
Based on the extracted research fields below, generate a comprehensive investment thesis for {company_name} (ISIN: {isin}).

COMPANY CONTEXT:
- Sector: {sector}
- Market Cap: ₹{market_cap_cr} Cr ({market_cap_cat})
- Current Price: ₹{current_price}
- TTM Revenue: ₹{revenue_cr} Cr
- TTM EBITDA Margin: {ebitda_margin}%
- Net Debt: ₹{net_debt_cr} Cr (D/E: {debt_equity}x)
- ROCE: {roce}%
- 3Y Revenue CAGR: {revenue_cagr_3y}%
- 3Y PAT CAGR: {pat_cagr_3y}%

EXTRACTED RESEARCH FIELDS (from latest documents):
{fields_json}

SECTIONS TO REGENERATE (only these have changed):
{sections_to_update}

INSTRUCTIONS:
1. Write an investment thesis covering ONLY the sections listed in SECTIONS TO REGENERATE.
2. For unchanged sections, output null so the caller preserves the existing content.
3. Be specific: cite numbers, percentages, and time periods.
4. Bull/Base/Bear cases must have a clear CAGR assumption and a 3-year target market cap.
5. Fair value range: provide low (bear), mid (base), high (bull) — all in ₹ per share.
6. Confidence score (0-100): 90+ = complete high-quality data; <50 = sparse data.
7. Rating: STRONG_BUY (>40% upside), BUY (20-40%), ACCUMULATE (10-20%),
           HOLD (0-10%), REDUCE (-10-0%), SELL (>-10% downside), AVOID (uninvestable).

Return ONLY valid JSON:
{{
  "one_liner": "<30-word investment verdict or null>",
  "thesis_text": "<3-5 paragraph narrative or null>",
  "strengths": [<{{point, evidence, confidence}}>] or null,
  "weaknesses": [<{{point, evidence, confidence}}>] or null,
  "opportunities": [<{{point, evidence, confidence}}>] or null,
  "threats": [<{{point, evidence, confidence}}>] or null,
  "bull_case": "<paragraph or null>",
  "bull_cagr_pct": <number|null>,
  "bull_target_cr": <number|null>,
  "base_case": "<paragraph or null>",
  "base_cagr_pct": <number|null>,
  "base_target_cr": <number|null>,
  "bear_case": "<paragraph or null>",
  "bear_cagr_pct": <number|null>,
  "bear_target_cr": <number|null>,
  "bull_probability": <number|null>,
  "base_probability": <number|null>,
  "bear_probability": <number|null>,
  "fair_value_low": <number|null>,
  "fair_value_mid": <number|null>,
  "fair_value_high": <number|null>,
  "target_price_12m": <number|null>,
  "expected_cagr_3y": <number|null>,
  "rating": "<STRONG_BUY|BUY|ACCUMULATE|HOLD|REDUCE|SELL|AVOID|null>",
  "confidence_score": <0-100|null>,
  "sections_updated": [<list of section names actually updated>]
}}
"""

# Which field categories map to which thesis sections
FIELD_TO_SECTION_MAP = {
    "growth_drivers": ["thesis_text", "bull_case", "opportunities"],
    "risks": ["bear_case", "threats", "thesis_text"],
    "capex_plans": ["bull_case", "thesis_text"],
    "guidance": ["bull_case", "base_case", "one_liner"],
    "margins": ["thesis_text", "base_case"],
    "debt_profile": ["weaknesses", "bear_case"],
    "market_share": ["strengths", "thesis_text"],
    "competitive_moat": ["strengths", "one_liner"],
    "promoters": ["weaknesses", "threats"],
    "pledging": ["threats", "weaknesses"],
    "export_exposure": ["opportunities", "thesis_text"],
    "management_quality": ["strengths", "one_liner"],
    "regulatory_risks": ["threats", "bear_case"],
    "sector_tailwinds": ["opportunities", "bull_case"],
    "business_segments": ["thesis_text"],
    "customer_concentration": ["threats", "weaknesses"],
    "subsidiaries": ["thesis_text"],
    "working_capital": ["weaknesses", "base_case"],
    "related_party_transactions": ["threats"],
    "esg_highlights": ["strengths"],
    "recent_developments": ["thesis_text", "one_liner"],
    "order_book_commentary": ["bull_case", "base_case", "thesis_text"],
}


def sections_to_update_from_changed_fields(changed_fields: list[str]) -> list[str]:
    """Determine which thesis sections need regeneration based on changed fields."""
    sections = set()
    for field in changed_fields:
        sections.update(FIELD_TO_SECTION_MAP.get(field, []))
    # Always refresh valuation when any field changes
    sections.update(["fair_value_low", "fair_value_mid", "fair_value_high", "target_price_12m",
                     "expected_cagr_3y", "rating", "confidence_score"])
    return list(sections)


async def generate_investment_thesis(
    company_name: str,
    isin: str,
    sector: str,
    market_cap_cr: float,
    market_cap_cat: str,
    current_price: float,
    financials: dict,
    extracted_fields: dict[str, dict],
    changed_fields: list[str],
    model: str = MODEL_DEEP,
) -> dict[str, Any]:
    """
    Generate or update the investment thesis.
    Only regenerates sections affected by changed_fields.
    """
    sections = sections_to_update_from_changed_fields(changed_fields) if changed_fields else None
    # If no changed fields specified, regenerate everything
    sections_label = json.dumps(sections or "ALL")

    # Build fields summary (current value_text for each field)
    fields_summary = {}
    for fname, fdata in extracted_fields.items():
        if fdata.get("value_text"):
            fields_summary[fname] = {
                "value": fdata["value_text"],
                "confidence": fdata.get("confidence", 0.5),
                "fiscal_period": fdata.get("fiscal_period"),
            }
        elif fdata.get("value_json"):
            fields_summary[fname] = {
                "value": fdata["value_json"],
                "confidence": fdata.get("confidence", 0.5),
            }

    fin = financials or {}
    prompt = THESIS_PROMPT.format(
        company_name=company_name,
        isin=isin,
        sector=sector or "Unknown",
        market_cap_cr=f"{market_cap_cr:,.0f}" if market_cap_cr else "N/A",
        market_cap_cat=market_cap_cat or "N/A",
        current_price=f"{current_price:.2f}" if current_price else "N/A",
        revenue_cr=f"{fin.get('revenue', 0):,.0f}",
        ebitda_margin=f"{fin.get('ebitda_margin', 0):.1f}",
        net_debt_cr=f"{fin.get('net_debt', 0):,.0f}",
        debt_equity=f"{fin.get('debt_equity', 0):.2f}",
        roce=f"{fin.get('roce', 0):.1f}",
        revenue_cagr_3y=f"{fin.get('revenue_cagr_3y', 0):.1f}",
        pat_cagr_3y=f"{fin.get('pat_cagr_3y', 0):.1f}",
        fields_json=json.dumps(fields_summary, indent=2, default=str),
        sections_to_update=sections_label,
    )

    raw = await call_ai(prompt, model=model, temperature=0.2)

    try:
        result = parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return _fallback_thesis(company_name, current_price)

    return result


def _fallback_thesis(company_name: str, current_price: float) -> dict[str, Any]:
    """Minimal fallback when Gemini fails."""
    return {
        "one_liner": f"{company_name} — insufficient data for rating.",
        "thesis_text": None,
        "strengths": None,
        "weaknesses": None,
        "opportunities": None,
        "threats": None,
        "bull_case": None,
        "bull_cagr_pct": None,
        "bull_target_cr": None,
        "base_case": None,
        "base_cagr_pct": None,
        "base_target_cr": None,
        "bear_case": None,
        "bear_cagr_pct": None,
        "bear_target_cr": None,
        "bull_probability": 33.0,
        "base_probability": 34.0,
        "bear_probability": 33.0,
        "fair_value_low": None,
        "fair_value_mid": None,
        "fair_value_high": None,
        "target_price_12m": None,
        "expected_cagr_3y": None,
        "rating": None,
        "confidence_score": 10.0,
        "sections_updated": [],
    }
