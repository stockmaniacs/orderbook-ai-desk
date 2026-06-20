"""
AI Relationship Extractor — Subcontract Opportunity Worker.

Extracts supply-chain relationships from:
  - Annual report customer concentration tables
  - Concall transcripts (management mentioning vendors/suppliers)
  - Investor presentations (supply chain slides)
  - Export disclosures
  - Industry reports

Output: directed graph edges (source → target, rel_type, product_category, strength)
"""
from __future__ import annotations

import json
import re
from typing import Any

import google.generativeai as genai

# ─── Relationship taxonomy ────────────────────────────────────────────────────
RELATIONSHIP_TYPES = {
    "SUPPLIES_TO":               "Generic supplier relationship",
    "CABLE_SUPPLIER_TO":         "Supplies cables/wires",
    "TRANSFORMER_SUPPLIER_TO":   "Supplies power transformers",
    "SWITCHGEAR_SUPPLIER_TO":    "Supplies switchgear/panels",
    "PIPE_SUPPLIER_TO":          "Supplies pipes/piping systems",
    "VALVE_SUPPLIER_TO":         "Supplies valves and actuators",
    "PUMP_SUPPLIER_TO":          "Supplies industrial pumps",
    "FABRICATES_FOR":            "Does steel/structural fabrication",
    "CIVIL_CONTRACTOR_TO":       "Civil construction subcontractor",
    "EPC_SUBCONTRACTOR_TO":      "EPC subcontract work",
    "INSTALLS_FOR":              "Installation/erection subcontractor",
    "COMPONENT_MAKER_FOR":       "Manufactures specific components",
    "FORGING_SUPPLIER_TO":       "Supplies forgings/castings",
    "ELECTRONICS_SUPPLIER_TO":   "Supplies electronic systems",
    "LOGISTICS_FOR":             "Logistics/transport partner",
    "SERVICE_PROVIDER_TO":       "Technical services provider",
    "JV_PARTNER_WITH":           "Joint venture partnership",
}

PRODUCT_CATEGORIES = [
    "cables", "transformers", "switchgear", "conductors", "insulators",
    "pipes", "valves", "pumps", "compressors", "heat_exchangers",
    "structural_steel", "fabrication", "forgings", "castings",
    "signalling", "instrumentation", "sensors", "electronics",
    "solar_modules", "wind_components", "inverters", "UPS",
    "civil_construction", "precast_concrete", "earthmoving",
    "logistics", "shipping", "crane_services",
    "IT_systems", "software", "SCADA",
    "chemicals", "coatings", "insulation",
    "compressors_industrial", "generators", "cooling_systems",
]

# ─── Extraction prompt ────────────────────────────────────────────────────────
RELATIONSHIP_EXTRACTION_PROMPT = """You are an expert supply-chain analyst for Indian listed companies.

Extract ALL supplier, vendor, subcontractor, and partner relationships mentioned in the document below.
The document is from company: {company_name} (ISIN: {isin})
Document type: {doc_type}

For EACH relationship found, extract:
1. source_company: the SUPPLIER / VENDOR / SUBCONTRACTOR (company that provides goods/services)
2. target_company: the BUYER / CLIENT (company that receives goods/services)
3. rel_type: one of {rel_types}
4. product_category: one of {product_cats} (or a specific term if none fit)
5. revenue_share_pct: % of source company's revenue from this relationship (if disclosed)
6. disclosed_rev_cr: actual ₹ Cr value (if mentioned)
7. confidence: 0.0–1.0 (1.0 = explicitly stated with figures; 0.5 = clearly implied)
8. evidence_text: exact quote from document supporting this (max 200 chars)

IMPORTANT RULES:
- The document's company ({company_name}) can appear as EITHER source OR target depending on context.
  - If document says "our top customer is L&T" → {company_name} is source, L&T is target
  - If document says "our key vendor is Polycab" → Polycab is source, {company_name} is target
- Only extract relationships involving LISTED Indian companies where possible.
- A relationship disclosed in customer concentration = high confidence (0.85–0.95).
- A vendor mentioned in passing = lower confidence (0.4–0.6).
- Include ALL tiers: direct customers, major suppliers, key subcontractors.
- Convert all amounts to ₹ Crores.

Return ONLY valid JSON:
{{
  "relationships": [
    {{
      "source_isin": "<ISIN or null if unknown>",
      "source_name": "<company name>",
      "target_isin": "<ISIN or null if unknown>",
      "target_name": "<company name>",
      "rel_type": "<from taxonomy>",
      "product_category": "<category>",
      "revenue_share_pct": <number or null>,
      "disclosed_rev_cr": <number or null>,
      "confidence": <0.0–1.0>,
      "evidence_text": "<exact quote>"
    }}
  ],
  "extraction_notes": "<any relevant context about supply chain>"
}}

Document text:
{text}
"""

# ─── Customer concentration prompt (structured table extraction) ──────────────
CUSTOMER_CONC_PROMPT = """Extract the customer concentration table from this annual report text for {company_name}.

For each customer listed, extract:
- customer_name
- customer_isin (if identifiable)
- revenue_pct (% of revenue)
- revenue_cr (₹ Cr if disclosed)
- fiscal_year

This company is a SUPPLIER to these customers. Create SUPPLIES_TO relationships.

Return JSON:
{{
  "customers": [
    {{
      "customer_name": "<name>",
      "customer_isin": "<ISIN or null>",
      "revenue_pct": <number or null>,
      "revenue_cr": <number or null>,
      "fiscal_year": <year or null>
    }}
  ]
}}

Text:
{text}
"""


async def extract_relationships(
    text: str,
    company_name: str,
    isin: str,
    doc_type: str,
    model: str = "gemini-1.5-flash",
) -> list[dict]:
    """
    Extract supply-chain relationships from document text.
    Returns list of relationship dicts ready to upsert into sc_relationships.
    """
    if len(text) > 100_000:
        text = text[:100_000] + "\n[TRUNCATED]"

    rel_types_str = json.dumps(list(RELATIONSHIP_TYPES.keys()))
    prod_cats_str = json.dumps(PRODUCT_CATEGORIES[:20])  # keep prompt manageable

    prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
        company_name=company_name,
        isin=isin,
        doc_type=doc_type,
        rel_types=rel_types_str,
        product_cats=prod_cats_str,
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
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE)

    try:
        result = json.loads(raw)
        rels = result.get("relationships", [])
    except json.JSONDecodeError:
        rels = _fallback_extraction(text, company_name, isin)

    return _validate_and_normalize(rels)


async def extract_customer_concentration(
    text: str,
    company_name: str,
    isin: str,
    model: str = "gemini-1.5-flash",
) -> list[dict]:
    """
    Specialized extraction for customer concentration tables.
    These are the most reliable source of supply-chain relationships.
    """
    prompt = CUSTOMER_CONC_PROMPT.format(
        company_name=company_name,
        text=text[:30_000],
    )

    model_client = genai.GenerativeModel(model)
    response = await model_client.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.text.strip(), flags=re.MULTILINE)
    try:
        result = json.loads(raw)
        customers = result.get("customers", [])
    except json.JSONDecodeError:
        return []

    # Convert to relationship dicts (source=this company, target=customer)
    rels = []
    for cust in customers:
        rels.append({
            "source_isin": isin,
            "source_name": company_name,
            "target_isin": cust.get("customer_isin"),
            "target_name": cust.get("customer_name", ""),
            "rel_type": "SUPPLIES_TO",
            "product_category": None,  # to be inferred from sector
            "revenue_share_pct": cust.get("revenue_pct"),
            "disclosed_rev_cr": cust.get("revenue_cr"),
            "confidence": 0.90,  # customer concentration = very reliable
            "evidence_text": f"Customer concentration: {cust.get('revenue_pct', '?')}% revenue",
        })
    return rels


def _validate_and_normalize(rels: list[dict]) -> list[dict]:
    """Validate and clean extracted relationships."""
    valid = []
    for r in rels:
        # Must have at least names for both parties
        if not r.get("source_name") or not r.get("target_name"):
            continue
        # Must have a rel_type
        if not r.get("rel_type"):
            r["rel_type"] = "SUPPLIES_TO"
        # Confidence bounds
        r["confidence"] = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
        # Strength = confidence (can diverge later with evidence accumulation)
        r["strength"] = r["confidence"]
        valid.append(r)
    return valid


def _fallback_extraction(text: str, company_name: str, isin: str) -> list[dict]:
    """Regex fallback: look for explicit percentage disclosures."""
    rels = []
    # Pattern: "XYZ Ltd contributed 32% of revenue" or "revenue from ABC Corp: ₹450 Cr"
    patterns = [
        r"([A-Z][A-Za-z\s&\.]+(?:Ltd|Limited|Corp|Corporation|Industries))[^0-9]*?(\d+\.?\d*)\s*%\s*(?:of\s*)?(?:total\s*)?revenue",
        r"revenue\s+from\s+([A-Z][A-Za-z\s&\.]+(?:Ltd|Limited|Corp))[^0-9]*?(\d+\.?\d*)\s*%",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            customer_name = m.group(1).strip()
            pct = float(m.group(2))
            if pct < 1 or pct > 99:
                continue
            rels.append({
                "source_isin": isin,
                "source_name": company_name,
                "target_isin": None,
                "target_name": customer_name,
                "rel_type": "SUPPLIES_TO",
                "product_category": None,
                "revenue_share_pct": pct,
                "disclosed_rev_cr": None,
                "confidence": 0.55,
                "evidence_text": m.group(0)[:200],
                "strength": 0.55,
            })
    return rels


# ─── ISIN resolution helper ───────────────────────────────────────────────────
async def resolve_company_isin(
    company_name: str,
    known_isins: dict[str, str],  # name → isin from instruments_master
) -> str | None:
    """
    Try to match a company name to a known ISIN using fuzzy matching.
    known_isins: {normalized_name: isin}
    """
    # Exact match first
    normalized = company_name.lower().strip()
    if normalized in known_isins:
        return known_isins[normalized]

    # Remove common suffixes and retry
    for suffix in [" limited", " ltd", " corp", " corporation", " industries", " pvt"]:
        stripped = normalized.removesuffix(suffix).strip()
        if stripped in known_isins:
            return known_isins[stripped]

    # Partial match — check if any known name is a substring
    for known, isin in known_isins.items():
        if known in normalized or normalized in known:
            return isin

    return None
