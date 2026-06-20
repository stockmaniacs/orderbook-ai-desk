"""
AI Field Extractor — Company Research Worker.
Extracts 20+ structured research fields from document text using Gemini Flash.
Only fields that have changed are re-extracted (incremental update).
"""
from __future__ import annotations

import json
import re
from typing import Any

import google.generativeai as genai

# ─── Field definitions ────────────────────────────────────────────────────────
# Each field: name, category, description (for the prompt), extraction type
RESEARCH_FIELDS: list[dict] = [
    # STRATEGY
    {"name": "growth_drivers", "category": "STRATEGY",
     "desc": "Key business growth drivers, tailwinds, new markets, product launches, capacity expansions"},
    {"name": "capex_plans", "category": "STRATEGY",
     "desc": "Capital expenditure plans: amounts (₹ Cr), purpose, timeline, expected ROI or capacity addition"},
    {"name": "order_book_commentary", "category": "STRATEGY",
     "desc": "Order book size, inflow guidance, execution timeline, sector mix as mentioned by management"},
    {"name": "business_segments", "category": "STRATEGY",
     "desc": "Business segment breakdown: revenue, margins, growth outlook for each segment"},
    {"name": "guidance", "category": "STRATEGY",
     "desc": "Management guidance: revenue growth %, EBITDA margin %, capex, specific targets for next 1-3 years"},

    # MARKET
    {"name": "market_share", "category": "MARKET",
     "desc": "Market share %, competitive positioning, addressable market size (TAM), rank among peers"},
    {"name": "export_exposure", "category": "MARKET",
     "desc": "Export revenue %, key geographies, export strategy, risks (currency, geopolitical)"},
    {"name": "competitive_moat", "category": "MARKET",
     "desc": "Competitive advantages: technology, brand, distribution, scale, cost leadership, IP"},
    {"name": "customer_concentration", "category": "MARKET",
     "desc": "Top customers, % of revenue from top-5 customers, single-customer risk"},

    # FUNDAMENTALS
    {"name": "margins", "category": "FUNDAMENTALS",
     "desc": "Gross/EBITDA/PAT margins: current levels, trends, pressure points, improvement levers"},
    {"name": "working_capital", "category": "FUNDAMENTALS",
     "desc": "Working capital cycle: debtor days, inventory days, creditor days, cash conversion"},
    {"name": "debt_profile", "category": "FUNDAMENTALS",
     "desc": "Total debt, net debt, D/E ratio, maturity profile, cost of debt, debt reduction plans"},

    # RISK
    {"name": "risks", "category": "RISK",
     "desc": "Key risks: regulatory, competitive, commodity, FX, client concentration, execution, cyclical"},
    {"name": "regulatory_risks", "category": "RISK",
     "desc": "Sector-specific regulations, upcoming policy changes, compliance issues, government dependency"},
    {"name": "related_party_transactions", "category": "RISK",
     "desc": "Material related party transactions, potential conflicts of interest"},

    # GOVERNANCE
    {"name": "promoters", "category": "GOVERNANCE",
     "desc": "Promoter holding %, changes in holding, family/institutional composition, succession"},
    {"name": "pledging", "category": "GOVERNANCE",
     "desc": "Promoter pledged shares %, trend, reason, risk level (HIGH if >30%)"},
    {"name": "management_quality", "category": "GOVERNANCE",
     "desc": "Management track record, execution history, compensation, key person risk, board quality"},
    {"name": "subsidiaries", "category": "GOVERNANCE",
     "desc": "Key subsidiaries: ownership %, revenue contribution, strategic importance, consolidation"},

    # MACRO / SECTOR
    {"name": "sector_tailwinds", "category": "STRATEGY",
     "desc": "Macro/sector-level tailwinds, government policy support, PLI scheme benefits, import substitution"},
    {"name": "esg_highlights", "category": "GOVERNANCE",
     "desc": "ESG initiatives, sustainability targets, carbon footprint, social programs"},
    {"name": "recent_developments", "category": "STRATEGY",
     "desc": "Material recent events: acquisitions, JVs, leadership changes, contracts >₹100 Cr, ratings"},
]

FIELD_NAMES = {f["name"] for f in RESEARCH_FIELDS}

# ─── Extraction prompt ────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """You are a senior equity research analyst specializing in Indian listed companies.

Extract structured research information from the document text below for {company_name} (ISIN: {isin}).

Document type: {doc_type}
Fiscal period: {fiscal_period}

For EACH of the following fields, extract what the document explicitly states.
If a field is NOT covered in this document, output null for it — do not guess.

Fields to extract:
{fields_json}

EXTRACTION RULES:
1. All monetary amounts must be in ₹ Crores. Convert: 1 Cr = 10 Mn, 1 Lakh Cr = 100,000 Cr, $1 Mn ≈ ₹8.3 Cr.
2. Use exact numbers/percentages where stated; use ranges (e.g. "18-20%") if management gave a range.
3. For list fields (risks, growth_drivers, etc.), return an array of concise strings.
4. Confidence: 0.9 = explicitly stated with numbers; 0.7 = clearly implied; 0.5 = general mention; 0.3 = weak inference.
5. Quote the fiscal period (e.g. "Q3FY26", "FY26") when stated.
6. For promoter pledging: if >30% pledged, flag risk as HIGH.
7. Never fabricate data. If uncertain, lower confidence rather than inventing.

Return ONLY valid JSON in this exact format:
{{
  "extracted_fields": {{
    "<field_name>": {{
      "value": <string|array|object|null>,
      "confidence": <0.0-1.0>,
      "fiscal_period": "<Q1FY26|FY26|null>",
      "key_quote": "<verbatim quote from doc, max 100 chars>"
    }}
  }},
  "document_summary": "<2-3 sentence summary of this document's research value>"
}}

Document text:
{text}
"""


async def extract_research_fields(
    text: str,
    company_name: str,
    isin: str,
    doc_type: str,
    fiscal_period: str,
    fields_to_extract: list[str] | None = None,
    model: str = "gemini-1.5-flash",
) -> dict[str, Any]:
    """
    Extract research fields from document text.

    Args:
        fields_to_extract: If provided, only extract these fields (for incremental updates).
                           If None, extract all fields.
    Returns:
        {"extracted_fields": {field_name: {value, confidence, ...}}, "document_summary": str}
    """
    target_fields = fields_to_extract or [f["name"] for f in RESEARCH_FIELDS]
    fields_info = [f for f in RESEARCH_FIELDS if f["name"] in target_fields]
    fields_json = json.dumps({f["name"]: f["desc"] for f in fields_info}, indent=2)

    # Truncate text to avoid token limit (Gemini Flash: ~1M tokens)
    if len(text) > 120_000:
        text = text[:120_000] + "\n\n[DOCUMENT TRUNCATED]"

    prompt = EXTRACTION_PROMPT.format(
        company_name=company_name,
        isin=isin,
        doc_type=doc_type,
        fiscal_period=fiscal_period,
        fields_json=fields_json,
        text=text,
    )

    model_client = genai.GenerativeModel(model)
    response = await model_client.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_extraction(text, target_fields)

    # Validate structure
    if "extracted_fields" not in result:
        return _fallback_extraction(text, target_fields)

    return result


def _fallback_extraction(text: str, target_fields: list[str]) -> dict[str, Any]:
    """Minimal regex-based fallback when LLM fails."""
    extracted = {}
    for field in target_fields:
        extracted[field] = {"value": None, "confidence": 0.0, "fiscal_period": None, "key_quote": None}

    # Try to extract margins
    margin_match = re.search(r"EBITDA margin[^0-9]*([0-9.]+)\s*%", text, re.IGNORECASE)
    if margin_match and "margins" in target_fields:
        extracted["margins"] = {
            "value": f"EBITDA margin: {margin_match.group(1)}%",
            "confidence": 0.4,
            "fiscal_period": None,
            "key_quote": margin_match.group(0)[:100],
        }

    return {"extracted_fields": extracted, "document_summary": "Extraction fallback — limited data."}


def fields_needing_update(
    existing_fields: dict[str, dict],  # {field_name: {version, source_doc_ids, ...}}
    new_doc_id: str,
    new_doc_type: str,
) -> list[str]:
    """
    Determine which fields need re-extraction given a new document.
    A field needs update if:
      - It doesn't exist yet, OR
      - The new doc type is MORE authoritative than its current source, OR
      - It was marked stale
    Returns list of field names to re-extract.
    """
    # Authority order: ANNUAL_REPORT > INVESTOR_PRESENTATION > CONCALL_TRANSCRIPT
    #                  > QUARTERLY_RESULTS > BSE_ANNOUNCEMENT > NEWS
    authority = {
        "ANNUAL_REPORT": 6,
        "INVESTOR_PRESENTATION": 5,
        "CONCALL_TRANSCRIPT": 4,
        "QUARTERLY_RESULTS": 3,
        "MANAGEMENT_INTERVIEW": 3,
        "BSE_ANNOUNCEMENT": 2,
        "NEWS": 1,
    }
    new_auth = authority.get(new_doc_type, 1)

    to_update = []
    for field_def in RESEARCH_FIELDS:
        fname = field_def["name"]
        if fname not in existing_fields:
            to_update.append(fname)
            continue
        existing = existing_fields[fname]
        if existing.get("is_stale"):
            to_update.append(fname)
            continue
        current_auth = authority.get(existing.get("primary_source", "NEWS"), 1)
        # Re-extract if new source is more authoritative or same level
        if new_auth >= current_auth:
            to_update.append(fname)

    return to_update
