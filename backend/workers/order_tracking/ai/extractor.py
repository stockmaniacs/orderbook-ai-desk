"""
AI Order Extractor
Uses Google Gemini to extract structured order details from announcement text.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are an expert financial analyst specialising in Indian equity markets.
Your task: extract structured order information from a BSE/NSE corporate announcement.

ANNOUNCEMENT TEXT:
\"\"\"
{text}
\"\"\"

Extract the following fields. Return ONLY valid JSON — no markdown, no explanation.
If a field cannot be determined, use null.

{{
  "company_name": "string — announcing company's full name",
  "customer_name": "string — client/buyer who placed the order (null if undisclosed)",
  "order_amount_cr": number — order value in Indian Rupees CRORES (convert if in other units; null if not mentioned),
  "order_amount_raw": "string — original amount text as stated, e.g. '₹ 2,345 Crore'",
  "order_currency": "INR | USD | EUR — currency of order (default INR)",
  "order_type": "DOMESTIC | EXPORT | MIXED — domestic India customer or export/international",
  "project_description": "string — 1-2 sentence description of what the order is for",
  "execution_start": "YYYY-MM-DD | null — when work is expected to begin",
  "execution_end": "YYYY-MM-DD | null — when work is expected to be completed",
  "duration_months": number | null — duration in months (derive from start/end if available),
  "sector_category": "INFRASTRUCTURE | DEFENSE | POWER | RAILWAYS | OIL_GAS | RENEWABLE | TELECOM | INDUSTRIAL | CHEMICAL | OTHER",
  "project_type": "EPC | SUPPLY | SERVICE | TURNKEY | MAINTENANCE | MIXED | OTHER",
  "is_repeat_order": boolean — is this a repeat/follow-on from same customer,
  "is_framework_contract": boolean — is this a framework/rate contract (multiple orders possible),
  "extraction_confidence": number between 0 and 1 — your confidence in the extraction,
  "extraction_notes": "string — anything unusual or uncertain about this announcement"
}}

IMPORTANT RULES:
- Convert all amounts to CRORES INR. 1 Crore = 10 Million INR. 1 USD ≈ 83 INR.
- If amount is in USD Million, multiply by 83 and divide by 10 to get Crores.
- "Large" without a number = null for order_amount_cr.
- If duration is "24 months" or "2 years", set duration_months accordingly.
- If customer is a government entity (NTPC, ONGC, Railways, Defence), set order_type = DOMESTIC.
- If customer is overseas company or "export", set order_type = EXPORT.
"""


async def extract_order_details(
    text: str,
    model: str = "gemini-1.5-flash",
) -> dict[str, Any]:
    """
    Send announcement text to Gemini and return structured order data.
    Returns empty dict on failure.
    """
    try:
        import google.generativeai as genai
        from ..core.config import settings
        genai.configure(api_key=settings.GEMINI_API_KEY)
    except ImportError:
        logger.error("google-generativeai not installed")
        return _fallback_extraction(text)

    prompt = EXTRACTION_PROMPT.format(text=text[:6000])  # cap at 6k chars

    try:
        genai_model = genai.GenerativeModel(model)
        response = genai_model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "top_p": 0.8,
                "response_mime_type": "application/json",
            },
        )
        raw = response.text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        data["extraction_model"] = model
        return data

    except json.JSONDecodeError as e:
        logger.error("Gemini returned invalid JSON: %s", e)
        return _fallback_extraction(text)
    except Exception as e:
        logger.error("Gemini extraction error: %s", e)
        return _fallback_extraction(text)


def _fallback_extraction(text: str) -> dict[str, Any]:
    """
    Rule-based fallback when AI is unavailable.
    Covers the most common patterns in Indian exchange filings.
    """
    result: dict[str, Any] = {
        "extraction_model": "rule_based_fallback",
        "extraction_confidence": 0.4,
        "extraction_notes": "AI unavailable; rule-based extraction used",
    }

    # Amount extraction — covers ₹ X Cr / Rs. X Crore / INR X Crore
    amount_patterns = [
        r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:Cr(?:ore)?s?|Lakh)",
        r"([\d,]+(?:\.\d+)?)\s*(?:Cr(?:ore)?s?)\s+(?:order|contract|project)",
        r"order\s+(?:value\s+)?(?:of\s+)?(?:approximately\s+)?(?:₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s*(?:Cr|Lakh)",
    ]

    for pat in amount_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw_num = m.group(1).replace(",", "")
            amount = float(raw_num)
            if "lakh" in m.group(0).lower():
                amount = amount / 100  # convert lakhs to crores
            result["order_amount_cr"] = round(amount, 2)
            result["order_amount_raw"] = m.group(0).strip()
            break

    # Order type
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["export", "overseas", "international", "foreign"]):
        result["order_type"] = "EXPORT"
    elif any(kw in text_lower for kw in ["domestic", "india", "indian"]):
        result["order_type"] = "DOMESTIC"

    # Duration
    dur_match = re.search(r"(\d+)\s*(?:months?|years?)", text, re.IGNORECASE)
    if dur_match:
        val = int(dur_match.group(1))
        if "year" in dur_match.group(0).lower():
            val *= 12
        result["duration_months"] = val

    # Sector heuristics
    sector_map = {
        "RAILWAYS": ["railway", "rail", "metro", "train", "ircon", "rites"],
        "DEFENSE": ["defence", "defense", "army", "navy", "air force", "ordnance"],
        "POWER": ["power", "electricity", "thermal", "ntpc", "genco"],
        "RENEWABLE": ["solar", "wind", "renewable", "green energy"],
        "OIL_GAS": ["oil", "gas", "refinery", "ongc", "iocl", "bpcl", "hpcl"],
        "INFRASTRUCTURE": ["highway", "road", "bridge", "nhai", "airport"],
        "TELECOM": ["telecom", "bsnl", "airtel", "jio", "5g", "tower"],
    }
    for sector, keywords in sector_map.items():
        if any(kw in text_lower for kw in keywords):
            result["sector_category"] = sector
            break
    else:
        result["sector_category"] = "INDUSTRIAL"

    return result


def is_valid_order_extraction(data: dict) -> bool:
    """Check if extraction produced meaningful results."""
    # Must have at least an amount or a description
    has_amount = data.get("order_amount_cr") is not None
    has_description = bool(data.get("project_description", ""))
    confidence = data.get("extraction_confidence", 0)
    return (has_amount or has_description) and confidence >= 0.3
