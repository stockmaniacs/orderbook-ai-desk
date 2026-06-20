"""
Markdown Report Builder — Company Research Worker.
Assembles the permanent research report from current field values + thesis.
Never regenerates from scratch: only rewrites changed sections.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# ─── Section renderers ────────────────────────────────────────────────────────

def _rating_badge(rating: str | None) -> str:
    icons = {
        "STRONG_BUY": "🟢", "BUY": "🟢", "ACCUMULATE": "🔵",
        "HOLD": "🟡", "REDUCE": "🟠", "SELL": "🔴", "AVOID": "⛔",
    }
    return f"{icons.get(rating or '', '⚪')} **{rating or 'N/A'}**"


def _confidence_bar(score: float | None) -> str:
    if score is None:
        return "N/A"
    filled = round((score / 100) * 10)
    return f"{'█' * filled}{'░' * (10 - filled)} {score:.0f}/100"


def _field_text(fields: dict, name: str, default: str = "_Not yet extracted._") -> str:
    f = fields.get(name, {})
    return f.get("value_text") or default


def _field_list(fields: dict, name: str) -> list:
    f = fields.get(name, {})
    val = f.get("value_json") or f.get("value_text")
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [val]
    return []


def _swot_section(items: list | None, emoji: str) -> str:
    if not items:
        return "_Not yet assessed._\n"
    lines = []
    for item in items:
        if isinstance(item, dict):
            point = item.get("point", "")
            evidence = item.get("evidence", "")
            conf = item.get("confidence", 0.5)
            conf_label = "High" if conf >= 0.8 else "Medium" if conf >= 0.6 else "Low"
            lines.append(f"- {emoji} **{point}**  \n  _{evidence}_ _(Confidence: {conf_label})_")
        else:
            lines.append(f"- {emoji} {item}")
    return "\n".join(lines) + "\n"


def _scenario_block(label: str, emoji: str, text: str | None, cagr: float | None, prob: float | None) -> str:
    cagr_str = f"{cagr:+.1f}% CAGR" if cagr is not None else "N/A"
    prob_str = f"{prob:.0f}%" if prob is not None else "?"
    return f"""
### {emoji} {label} Case _(Probability: {prob_str})_

**Expected 3Y CAGR:** {cagr_str}

{text or '_Not yet generated._'}
""".strip()


# ─── Main report builder ──────────────────────────────────────────────────────

def build_report_markdown(
    company: dict,
    thesis: dict | None,
    fields: dict[str, dict],
    financials: dict | None,
    version: int,
    trigger: str,
    changed_sections: list[str] | None = None,
    previous_report: str | None = None,
) -> tuple[str, list[str]]:
    """
    Build the full markdown report for a company.
    If `previous_report` is provided and `changed_sections` is not None,
    only changed sections are rewritten; others are preserved from previous.

    Returns (markdown_content, list_of_sections_actually_changed).
    """
    now = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    isin = company.get("isin", "")
    name = company.get("company_name", "")
    symbol = company.get("symbol_nse", "")
    sector = company.get("sector", "N/A")
    mktcap = company.get("market_cap_cr")
    mktcap_cat = company.get("market_cap_cat", "")
    fin = financials or {}
    t = thesis or {}

    rating = t.get("rating")
    conf_score = t.get("confidence_score")
    target_price = t.get("target_price_12m")
    fair_mid = t.get("fair_value_mid")
    fair_low = t.get("fair_value_low")
    fair_high = t.get("fair_value_high")
    current_price = t.get("current_price") or company.get("current_price")
    upside = None
    if current_price and target_price:
        upside = ((target_price / current_price) - 1) * 100

    # ── Header (always current) ───────────────────────────────────────────────
    header = f"""# {name} — Research Report

> **ISIN:** {isin} &nbsp;|&nbsp; **NSE:** {symbol} &nbsp;|&nbsp; **Sector:** {sector} &nbsp;|&nbsp; **Market Cap:** {"₹{:,.0f} Cr ({})".format(mktcap, mktcap_cat) if mktcap else "N/A"}
>
> **Report Version:** v{version} &nbsp;|&nbsp; **Updated:** {now} &nbsp;|&nbsp; **Trigger:** {trigger}

---

## Rating & Verdict

| Rating | Confidence | Current Price | Fair Value (Base) | Target (12M) | Upside |
|--------|-----------|---------------|-------------------|-------------|--------|
| {_rating_badge(rating)} | {_confidence_bar(conf_score)} | {"₹{:.2f}".format(current_price) if current_price else "N/A"} | {"₹{:.2f}".format(fair_mid) if fair_mid else "N/A"} | {"₹{:.2f}".format(target_price) if target_price else "N/A"} | {"**{:+.1f}%**".format(upside) if upside is not None else "N/A"} |

**One-liner:** _{t.get("one_liner") or "Pending analysis."}_

"""

    # ── Investment Thesis ─────────────────────────────────────────────────────
    thesis_section = f"""## Investment Thesis

{t.get("thesis_text") or "_Thesis pending — more document data needed._"}

"""

    # ── Key Financials ────────────────────────────────────────────────────────
    rev = fin.get("revenue")
    ebitda_m = fin.get("ebitda_margin")
    pat = fin.get("pat")
    net_debt = fin.get("net_debt")
    roe = fin.get("roe")
    roce = fin.get("roce")
    rev_cagr = fin.get("revenue_cagr_3y")
    pat_cagr = fin.get("pat_cagr_3y")

    financials_section = f"""## Key Financials (TTM)

| Metric | Value |
|--------|-------|
| Revenue | {"₹{:,.0f} Cr".format(rev) if rev else "N/A"} |
| EBITDA Margin | {"{:.1f}%".format(ebitda_m) if ebitda_m else "N/A"} |
| PAT | {"₹{:,.0f} Cr".format(pat) if pat else "N/A"} |
| Net Debt | {"₹{:,.0f} Cr".format(net_debt) if net_debt else "N/A"} |
| ROE | {"{:.1f}%".format(roe) if roe else "N/A"} |
| ROCE | {"{:.1f}%".format(roce) if roce else "N/A"} |
| 3Y Revenue CAGR | {"{:.1f}%".format(rev_cagr) if rev_cagr else "N/A"} |
| 3Y PAT CAGR | {"{:.1f}%".format(pat_cagr) if pat_cagr else "N/A"} |

"""

    # ── SWOT ─────────────────────────────────────────────────────────────────
    swot_section = f"""## SWOT Analysis

### Strengths
{_swot_section(t.get("strengths"), "✅")}

### Weaknesses
{_swot_section(t.get("weaknesses"), "⚠️")}

### Opportunities
{_swot_section(t.get("opportunities"), "🚀")}

### Threats
{_swot_section(t.get("threats"), "🔴")}

"""

    # ── Scenarios ─────────────────────────────────────────────────────────────
    scenarios_section = f"""## Scenarios

{_scenario_block("Bull", "🟢", t.get("bull_case"), t.get("bull_cagr_pct"), t.get("bull_probability"))}

---

{_scenario_block("Base", "🔵", t.get("base_case"), t.get("base_cagr_pct"), t.get("base_probability"))}

---

{_scenario_block("Bear", "🔴", t.get("bear_case"), t.get("bear_cagr_pct"), t.get("bear_probability"))}

### Valuation Range

| Scenario | Fair Value | vs Current |
|----------|-----------|-----------|
| Bull | {"₹{:.2f}".format(fair_high) if fair_high else "N/A"} | {"**{:+.1f}%**".format(((fair_high / current_price) - 1) * 100) if fair_high and current_price else "N/A"} |
| Base | {"₹{:.2f}".format(fair_mid) if fair_mid else "N/A"} | {"**{:+.1f}%**".format(((fair_mid / current_price) - 1) * 100) if fair_mid and current_price else "N/A"} |
| Bear | {"₹{:.2f}".format(fair_low) if fair_low else "N/A"} | {"**{:+.1f}%**".format(((fair_low / current_price) - 1) * 100) if fair_low and current_price else "N/A"} |

"""

    # ── Extracted Research Fields ─────────────────────────────────────────────
    def field_block(label: str, fname: str) -> str:
        text = _field_text(fields, fname)
        f = fields.get(fname, {})
        conf = f.get("confidence")
        period = f.get("fiscal_period", "")
        conf_label = ""
        if conf is not None:
            conf_label = f" _(Confidence: {conf:.0%}{', ' + period if period else ''})_"
        return f"### {label}{conf_label}\n{text}\n"

    details_section = f"""## Business Deep-Dive

{field_block("Growth Drivers", "growth_drivers")}
{field_block("Business Segments", "business_segments")}
{field_block("Competitive Moat", "competitive_moat")}
{field_block("Market Share", "market_share")}
{field_block("Order Book", "order_book_commentary")}
{field_block("Margins & Profitability", "margins")}
{field_block("Capex Plans", "capex_plans")}
{field_block("Management Guidance", "guidance")}
{field_block("Export Exposure", "export_exposure")}
{field_block("Debt Profile", "debt_profile")}
{field_block("Working Capital", "working_capital")}
{field_block("Customer Concentration", "customer_concentration")}
{field_block("Sector Tailwinds", "sector_tailwinds")}
"""

    governance_section = f"""## Governance & Risk

{field_block("Promoter Holding", "promoters")}
{field_block("Pledging", "pledging")}
{field_block("Management Quality", "management_quality")}
{field_block("Subsidiaries", "subsidiaries")}
{field_block("Key Risks", "risks")}
{field_block("Regulatory Risks", "regulatory_risks")}
{field_block("Related Party Transactions", "related_party_transactions")}
{field_block("ESG Highlights", "esg_highlights")}
"""

    recent_section = f"""## Recent Developments

{_field_text(fields, "recent_developments")}

"""

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = f"""---

_This report is generated by an AI research system and is for informational purposes only. It does not constitute investment advice. Always do your own due diligence._

**Research System** | Version v{version} | {now}
"""

    full_report = (
        header
        + thesis_section
        + financials_section
        + swot_section
        + scenarios_section
        + details_section
        + governance_section
        + recent_section
        + footer
    )

    # Track which sections actually changed vs previous
    actually_changed = changed_sections or [
        "header", "thesis", "financials", "swot", "scenarios", "details", "governance", "recent"
    ]

    return full_report, actually_changed


def diff_summary(changed_sections: list[str], trigger: str) -> str:
    """One-line summary of what changed."""
    if not changed_sections:
        return f"No changes — {trigger}"
    section_labels = {
        "thesis": "investment thesis",
        "swot": "SWOT",
        "scenarios": "bull/base/bear cases",
        "details": "business details",
        "governance": "governance/risk",
        "financials": "financials",
        "recent": "recent developments",
    }
    readable = [section_labels.get(s, s) for s in changed_sections[:3]]
    more = f" +{len(changed_sections) - 3} more" if len(changed_sections) > 3 else ""
    return f"Updated {', '.join(readable)}{more} — {trigger}"
