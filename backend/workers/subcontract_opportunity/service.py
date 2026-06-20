"""
Subcontract Opportunity Service — main pipeline.

Flow:
  order win detected
    → classify_order_theme()
    → find_suppliers() via recursive CTE
    → score_beneficiary() for each supplier
    → generate_beneficiary_narratives() for top candidates
    → save SubcontractOpportunity + ranked OpportunityBeneficiary rows
    → return opportunity_id
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyRelationship,
    OpportunityBeneficiary,
    PredictionOutcome,
    SectorTheme,
    SubcontractOpportunity,
    SupplyChainNode,
)
from .graph.traversal import (
    find_customers,
    find_suppliers,
    get_node_stats,
    refresh_node_degrees,
    compute_centrality,
)
from .graph.builder import (
    process_document_for_graph,
    seed_from_instruments_master,
    upsert_node,
)
from .ai.opportunity_analyzer import (
    classify_order_theme,
    generate_beneficiary_narratives,
    score_beneficiary,
    THEME_SUBCONTRACT_RATIOS,
)

log = logging.getLogger(__name__)


# ─── Main pipeline: order win → ranked beneficiary list ──────────────────────
async def analyze_order_opportunity(
    db: AsyncSession,
    *,
    prime_contractor_isin: str,
    prime_contractor_name: str,
    order_amount_cr: float,
    order_customer: str | None,
    order_sector: str | None,
    order_description: str | None,
    announced_date: date | None = None,
    order_announcement_id: str | None = None,
    max_hops: int = 2,
    min_strength: float = 0.25,
) -> str:
    """
    Full pipeline: classify → traverse graph → score → narrate → persist.
    Returns opportunity_id (UUID str).
    """
    # 1. Classify theme
    theme, sub_themes = classify_order_theme(
        order_description or "",
        order_sector,
        order_customer,
    )
    subcontract_ratio = THEME_SUBCONTRACT_RATIOS.get(theme, 0.45)
    estimated_sub_cr = order_amount_cr * subcontract_ratio

    log.info(
        "Opportunity: %s ₹%.0f Cr | theme=%s | est_sub=₹%.0f Cr",
        prime_contractor_name, order_amount_cr, theme, estimated_sub_cr,
    )

    # 2. Ensure prime contractor node exists
    await upsert_node(db, prime_contractor_isin, prime_contractor_name, supply_chain_tier=1)

    # 3. Find all suppliers up to max_hops
    suppliers = await find_suppliers(
        db, prime_contractor_isin,
        max_hops=max_hops,
        min_strength=min_strength,
    )
    log.info("Found %d supplier candidates for %s", len(suppliers), prime_contractor_name)

    if not suppliers:
        log.warning("No suppliers found for %s — check graph data", prime_contractor_isin)

    # 4. Fetch beneficiary TTM revenue from company financials (or fallback to market cap proxy)
    ttm_revenues = await _get_ttm_revenues(db, [s["source_isin"] for s in suppliers])

    # 5. Score each supplier
    scored: list[dict] = []
    for sup in suppliers:
        isin = sup["source_isin"]
        ttm_rev = ttm_revenues.get(isin) or _mcap_to_revenue_estimate(sup.get("beneficiary_mcap_cr"))

        result = score_beneficiary(
            relationship_strength=float(sup["strength"]),
            revenue_share_pct=sup.get("revenue_share_pct"),
            product_category=sup.get("product_category"),
            order_theme=theme,
            order_amount_cr=order_amount_cr,
            beneficiary_ttm_rev_cr=ttm_rev,
            supply_chain_hops=int(sup.get("hops", 1)),
            historical_accuracy=await _get_historical_accuracy(db, isin, prime_contractor_isin),
        )

        scored.append({
            "beneficiary_isin": isin,
            "beneficiary_name": sup.get("source_name", ""),
            "beneficiary_sector": sup.get("beneficiary_sector"),
            "beneficiary_mcap_cr": sup.get("beneficiary_mcap_cr"),
            "relationship_type": sup.get("rel_type"),
            "product_category": sup.get("product_category"),
            "supply_chain_hops": int(sup.get("hops", 1)),
            "relationship_path": sup.get("path_json"),
            **result,
        })

    # 6. Sort by overall_score DESC, deduplicate by isin (keep best)
    seen: dict[str, dict] = {}
    for s in sorted(scored, key=lambda x: x["overall_score"], reverse=True):
        if s["beneficiary_isin"] not in seen:
            seen[s["beneficiary_isin"]] = s
    ranked = list(seen.values())

    # 7. AI narratives for top beneficiaries
    order_context = {
        "prime_contractor_name": prime_contractor_name,
        "order_amount_cr": order_amount_cr,
        "theme": theme,
        "order_customer": order_customer or "",
        "order_description": order_description or "",
    }
    ranked = await generate_beneficiary_narratives(ranked, order_context)

    # 8. Persist opportunity
    opp_stmt = pg_insert(SubcontractOpportunity).values(
        order_announcement_id=order_announcement_id,
        prime_contractor_isin=prime_contractor_isin,
        prime_contractor_name=prime_contractor_name,
        order_amount_cr=order_amount_cr,
        order_customer=order_customer,
        order_sector=order_sector,
        order_description=order_description,
        announced_date=announced_date or date.today(),
        theme=theme,
        sub_themes=sub_themes,
        estimated_subcontract_cr=estimated_sub_cr,
        subcontract_ratio=subcontract_ratio,
        beneficiary_count=len(ranked),
        analysis_version=1,
        status="ACTIVE",
    ).returning(SubcontractOpportunity.id)

    result = await db.execute(opp_stmt)
    opp_id = str(result.scalar_one())

    # 9. Persist beneficiaries with ranks
    for rank, ben in enumerate(ranked, start=1):
        stmt = pg_insert(OpportunityBeneficiary).values(
            opportunity_id=opp_id,
            beneficiary_isin=ben["beneficiary_isin"],
            beneficiary_name=ben.get("beneficiary_name"),
            beneficiary_sector=ben.get("beneficiary_sector"),
            beneficiary_mcap_cr=ben.get("beneficiary_mcap_cr"),
            relationship_type=ben.get("relationship_type"),
            product_category=ben.get("product_category"),
            supply_chain_hops=ben.get("supply_chain_hops", 1),
            probability_score=ben["probability_score"],
            revenue_impact_cr=ben["revenue_impact_cr"],
            revenue_impact_pct=ben["revenue_impact_pct"],
            confidence_score=ben["confidence_score"],
            overall_score=ben["overall_score"],
            rank=rank,
            score_breakdown=ben.get("score_breakdown"),
            rationale=ben.get("rationale"),
            key_risks=ben.get("key_risks", []),
            key_catalysts=ben.get("key_catalysts", []),
            investment_action=ben["investment_action"],
            relationship_path=ben.get("relationship_path"),
        ).on_conflict_do_update(
            constraint="uq_opp_beneficiary",
            set_={
                "probability_score": ben["probability_score"],
                "overall_score": ben["overall_score"],
                "rank": rank,
                "investment_action": ben["investment_action"],
                "rationale": ben.get("rationale"),
                "key_risks": ben.get("key_risks", []),
                "key_catalysts": ben.get("key_catalysts", []),
            },
        )
        await db.execute(stmt)

    await db.commit()
    log.info("Opportunity %s saved with %d beneficiaries", opp_id, len(ranked))
    return opp_id


# ─── Process a company's documents to build graph ────────────────────────────
async def process_company_supply_chain(
    db: AsyncSession,
    isin: str,
    doc_types: list[str] | None = None,
) -> dict:
    """
    Fetch documents for a company and extract supply-chain relationships.
    Integrates with Company Research worker's ResearchDocument table.
    """
    # Load instruments_master lookup for ISIN resolution
    result = await db.execute(text("""
    SELECT LOWER(TRIM(company_name)) AS name_key, isin
    FROM instruments_master
    WHERE is_active = true
    """))
    known_isins = {row.name_key: row.isin for row in result.fetchall()}

    # Fetch company name
    company_result = await db.execute(text("""
    SELECT company_name FROM instruments_master WHERE isin = :isin
    """), {"isin": isin})
    company_row = company_result.fetchone()
    company_name = company_row.company_name if company_row else isin

    # Pull documents from research worker's table
    doc_filter = ""
    params: dict[str, Any] = {"isin": isin}
    if doc_types:
        doc_filter = "AND doc_type = ANY(:doc_types)"
        params["doc_types"] = doc_types

    doc_result = await db.execute(text(f"""
    SELECT id, doc_type, url, text_extracted, fiscal_year
    FROM research_documents
    WHERE isin = :isin {doc_filter}
      AND text_extracted IS NOT NULL
      AND LENGTH(text_extracted) > 100
    ORDER BY
      CASE doc_type
        WHEN 'ANNUAL_REPORT' THEN 1
        WHEN 'CONCALL_TRANSCRIPT' THEN 2
        WHEN 'INVESTOR_PRESENTATION' THEN 3
        ELSE 4
      END
    LIMIT 20
    """), params)
    docs = doc_result.fetchall()

    total_stats = {"extracted": 0, "upserted": 0, "skipped": 0}

    for doc in docs:
        stats = await process_document_for_graph(
            db=db,
            isin=isin,
            company_name=company_name,
            doc_text=doc.text_extracted,
            doc_type=doc.doc_type,
            doc_url=doc.url,
            fiscal_year=doc.fiscal_year,
            known_isins=known_isins,
        )
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

    return {"isin": isin, "docs_processed": len(docs), **total_stats}


# ─── Batch rebuild graph for all companies ────────────────────────────────────
async def rebuild_graph(
    db: AsyncSession,
    isins: list[str] | None = None,
) -> dict:
    """
    Seeds nodes from instruments_master and processes all listed companies.
    """
    # Seed nodes first
    node_count = await seed_from_instruments_master(db)

    # Get ISINs to process
    if isins is None:
        result = await db.execute(text("SELECT isin FROM instruments_master WHERE is_active = true"))
        isins = [r.isin for r in result.fetchall()]

    return {"nodes_seeded": node_count, "companies_queued": len(isins), "isins": isins}


# ─── Get opportunity detail ───────────────────────────────────────────────────
async def get_opportunity(db: AsyncSession, opp_id: str) -> dict | None:
    result = await db.execute(
        select(SubcontractOpportunity).where(SubcontractOpportunity.id == opp_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        return None

    bens_result = await db.execute(
        select(OpportunityBeneficiary)
        .where(OpportunityBeneficiary.opportunity_id == opp_id)
        .order_by(OpportunityBeneficiary.rank)
    )
    beneficiaries = bens_result.scalars().all()

    return {"opportunity": opp, "beneficiaries": list(beneficiaries)}


# ─── Get opportunities feed ───────────────────────────────────────────────────
async def get_opportunities_feed(
    db: AsyncSession,
    theme: str | None = None,
    prime_isin: str | None = None,
    min_amount_cr: float | None = None,
    action_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return paginated list of opportunities with top beneficiary preview."""
    q = select(SubcontractOpportunity).where(SubcontractOpportunity.status == "ACTIVE")
    if theme:
        q = q.where(SubcontractOpportunity.theme == theme)
    if prime_isin:
        q = q.where(SubcontractOpportunity.prime_contractor_isin == prime_isin)
    if min_amount_cr:
        q = q.where(SubcontractOpportunity.order_amount_cr >= min_amount_cr)
    q = q.order_by(SubcontractOpportunity.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    opps = result.scalars().all()

    # Count
    count_result = await db.execute(
        select(func.count()).select_from(SubcontractOpportunity).where(SubcontractOpportunity.status == "ACTIVE")
    )
    total = count_result.scalar()

    # Attach top beneficiary for each opportunity
    items = []
    for opp in opps:
        top_q = (
            select(OpportunityBeneficiary)
            .where(OpportunityBeneficiary.opportunity_id == str(opp.id))
            .order_by(OpportunityBeneficiary.rank)
            .limit(1)
        )
        top_result = await db.execute(top_q)
        top_ben = top_result.scalar_one_or_none()

        item = {
            "id": str(opp.id),
            "prime_contractor_isin": opp.prime_contractor_isin,
            "prime_contractor_name": opp.prime_contractor_name,
            "order_amount_cr": float(opp.order_amount_cr or 0),
            "order_customer": opp.order_customer,
            "theme": opp.theme,
            "announced_date": opp.announced_date.isoformat() if opp.announced_date else None,
            "estimated_subcontract_cr": float(opp.estimated_subcontract_cr or 0),
            "beneficiary_count": opp.beneficiary_count,
            "status": opp.status,
            "created_at": opp.created_at.isoformat() if opp.created_at else None,
            "top_beneficiary_name": top_ben.beneficiary_name if top_ben else None,
            "top_beneficiary_action": top_ben.investment_action if top_ben else None,
            "top_beneficiary_score": top_ben.overall_score if top_ben else None,
        }
        items.append(item)

    return {"total": total, "items": items}


# ─── Get company graph view ───────────────────────────────────────────────────
async def get_company_graph(db: AsyncSession, isin: str) -> dict:
    # Node
    node_result = await db.execute(select(SupplyChainNode).where(SupplyChainNode.isin == isin))
    node = node_result.scalar_one_or_none()

    # Suppliers (companies that supply TO this company)
    suppliers_result = await db.execute(
        select(CompanyRelationship)
        .where(CompanyRelationship.target_isin == isin, CompanyRelationship.is_active.is_(True))
        .order_by(CompanyRelationship.strength.desc())
        .limit(50)
    )
    suppliers = suppliers_result.scalars().all()

    # Customers (companies this company supplies TO)
    customers_result = await db.execute(
        select(CompanyRelationship)
        .where(CompanyRelationship.source_isin == isin, CompanyRelationship.is_active.is_(True))
        .order_by(CompanyRelationship.strength.desc())
        .limit(50)
    )
    customers = customers_result.scalars().all()

    stats = await get_node_stats(db, isin)

    return {
        "isin": isin,
        "company_name": node.company_name if node else isin,
        "sector": node.sector if node else None,
        "centrality_score": node.centrality_score if node else None,
        "supply_chain_tier": node.supply_chain_tier if node else None,
        "stats": stats,
        "suppliers": list(suppliers),
        "customers": list(customers),
    }


# ─── Graph-wide statistics ────────────────────────────────────────────────────
async def get_graph_stats(db: AsyncSession) -> dict:
    nodes_result = await db.execute(text("SELECT COUNT(*) FROM sc_nodes"))
    total_nodes = nodes_result.scalar()

    rels_result = await db.execute(text(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE is_active) FROM sc_relationships"
    ))
    total_rels, active_rels = rels_result.fetchone()

    degree_result = await db.execute(text("""
    SELECT AVG(in_degree)::float, AVG(out_degree)::float FROM sc_nodes
    """))
    avg_in, avg_out = degree_result.fetchone()

    top_sup = await db.execute(text("""
    SELECT isin, company_name, in_degree, centrality_score
    FROM sc_nodes ORDER BY in_degree DESC LIMIT 10
    """))
    top_suppliers = [dict(r._mapping) for r in top_sup.fetchall()]

    top_prime = await db.execute(text("""
    SELECT isin, company_name, out_degree FROM sc_nodes ORDER BY out_degree DESC LIMIT 10
    """))
    top_primes = [dict(r._mapping) for r in top_prime.fetchall()]

    theme_result = await db.execute(text("""
    SELECT theme, COUNT(*) FROM sc_opportunities WHERE status='ACTIVE' GROUP BY theme
    """))
    theme_breakdown = {r.theme: r.count for r in theme_result.fetchall()}

    return {
        "total_nodes": total_nodes or 0,
        "total_relationships": total_rels or 0,
        "active_relationships": active_rels or 0,
        "avg_in_degree": round(avg_in or 0, 2),
        "avg_out_degree": round(avg_out or 0, 2),
        "top_suppliers": top_suppliers,
        "top_primes": top_primes,
        "theme_breakdown": theme_breakdown,
    }


# ─── Graph universe listing ───────────────────────────────────────────────────
async def get_graph_universe(
    db: AsyncSession,
    sector: str | None = None,
    tier: int | None = None,
    min_degree: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    q = select(SupplyChainNode)
    if sector:
        q = q.where(SupplyChainNode.sector.ilike(f"%{sector}%"))
    if tier:
        q = q.where(SupplyChainNode.supply_chain_tier == tier)
    if min_degree:
        q = q.where(SupplyChainNode.in_degree >= min_degree)

    count_q = select(func.count()).select_from(SupplyChainNode)
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    q = q.order_by(SupplyChainNode.centrality_score.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    nodes = result.scalars().all()
    return {"total": total, "items": list(nodes)}


# ─── Record prediction outcome ────────────────────────────────────────────────
async def record_prediction_outcome(
    db: AsyncSession,
    opportunity_id: str,
    beneficiary_isin: str,
    was_correct: bool,
    actual_rev_impact_cr: float | None = None,
    actual_rev_growth_pct: float | None = None,
    outcome_source: str | None = None,
    outcome_notes: str | None = None,
) -> None:
    ben_result = await db.execute(
        select(OpportunityBeneficiary)
        .where(
            OpportunityBeneficiary.opportunity_id == opportunity_id,
            OpportunityBeneficiary.beneficiary_isin == beneficiary_isin,
        )
    )
    ben = ben_result.scalar_one_or_none()

    db.add(PredictionOutcome(
        opportunity_id=opportunity_id,
        beneficiary_isin=beneficiary_isin,
        predicted_prob=ben.probability_score if ben else None,
        predicted_rev_cr=ben.revenue_impact_cr if ben else None,
        was_correct=was_correct,
        actual_rev_impact_cr=actual_rev_impact_cr,
        actual_rev_growth_pct=actual_rev_growth_pct,
        outcome_source=outcome_source,
        outcome_notes=outcome_notes,
        outcome_date=date.today(),
    ))
    await db.commit()


# ─── Helper: TTM revenue from company financials ──────────────────────────────
async def _get_ttm_revenues(db: AsyncSession, isins: list[str]) -> dict[str, float]:
    if not isins:
        return {}
    result = await db.execute(text("""
    SELECT isin, revenue_cr FROM company_financials
    WHERE isin = ANY(:isins)
      AND period_type = 'ANNUAL'
      AND is_latest = true
    """), {"isins": isins})
    return {r.isin: float(r.revenue_cr) for r in result.fetchall() if r.revenue_cr}


def _mcap_to_revenue_estimate(mcap_cr: float | None) -> float:
    """Fallback: estimate revenue using median 2x market cap assumption."""
    if not mcap_cr:
        return 500.0  # ₹500 Cr default for unknown small-cap
    return max(50.0, mcap_cr / 2)


async def _get_historical_accuracy(
    db: AsyncSession,
    beneficiary_isin: str,
    prime_isin: str,
) -> float:
    """Compute historical prediction accuracy for this supplier-prime pair."""
    result = await db.execute(text("""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE was_correct = true) AS correct
    FROM sc_prediction_outcomes po
    JOIN sc_opportunities opp ON opp.id = po.opportunity_id
    WHERE po.beneficiary_isin = :b_isin
      AND opp.prime_contractor_isin = :p_isin
    """), {"b_isin": beneficiary_isin, "p_isin": prime_isin})
    row = result.fetchone()
    if not row or row.total == 0:
        return 0.5  # neutral prior with no data
    return row.correct / row.total
