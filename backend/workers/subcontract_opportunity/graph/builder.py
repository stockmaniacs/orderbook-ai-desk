"""
Graph Builder — Subcontract Opportunity Worker.

Builds and continuously updates the supply-chain relationship graph by:
1. Reading all company annual reports (customer concentration tables)
2. Reading concall transcripts for vendor/supplier mentions
3. Reading investor presentations for supply chain disclosures
4. Using AI to extract relationships from free text
5. Upserting edges with conflict resolution (evidence accumulation)
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CompanyRelationship, RelationshipEvidence, SupplyChainNode
from ..ai.relationship_extractor import (
    extract_relationships,
    extract_customer_concentration,
    resolve_company_isin,
)


# ─── Node upsert ──────────────────────────────────────────────────────────────
async def upsert_node(
    db: AsyncSession,
    isin: str,
    company_name: str,
    **kwargs: Any,
) -> None:
    """Create or update a supply-chain graph node."""
    stmt = pg_insert(SupplyChainNode).values(
        isin=isin,
        company_name=company_name,
        **kwargs,
    ).on_conflict_do_update(
        index_elements=["isin"],
        set_={
            "company_name": company_name,
            "updated_at": datetime.utcnow(),
            **{k: v for k, v in kwargs.items() if v is not None},
        },
    )
    await db.execute(stmt)


# ─── Edge upsert with evidence accumulation ───────────────────────────────────
async def upsert_relationship(
    db: AsyncSession,
    source_isin: str,
    source_name: str,
    target_isin: str,
    target_name: str,
    rel_type: str,
    product_category: str | None,
    strength: float,
    confidence: float,
    revenue_share_pct: float | None = None,
    disclosed_rev_cr: float | None = None,
    discovery_method: str = "AI_EXTRACTION",
    evidence_text: str | None = None,
    doc_type: str | None = None,
    doc_url: str | None = None,
    fiscal_year: int | None = None,
) -> str | None:
    """
    Upsert a supply-chain relationship.
    On conflict: accumulate evidence, strengthen the edge, update last_confirmed.
    Returns relationship UUID.
    """
    today = date.today()

    stmt = pg_insert(CompanyRelationship).values(
        source_isin=source_isin,
        source_name=source_name,
        target_isin=target_isin,
        target_name=target_name,
        rel_type=rel_type,
        product_category=product_category,
        strength=strength,
        revenue_share_pct=revenue_share_pct,
        disclosed_rev_cr=disclosed_rev_cr,
        confidence=confidence,
        discovery_method=discovery_method,
        evidence_count=1,
        first_seen=today,
        last_confirmed=today,
        is_active=True,
    ).on_conflict_do_update(
        constraint="uq_relationship",
        set_={
            # Increase strength when more evidence arrives (Bayesian update)
            "strength": text(
                "GREATEST(sc_relationships.strength, EXCLUDED.strength)"
                " + (1 - GREATEST(sc_relationships.strength, EXCLUDED.strength)) * 0.1"
            ),
            "confidence": text(
                "GREATEST(sc_relationships.confidence, EXCLUDED.confidence)"
            ),
            "evidence_count": text("sc_relationships.evidence_count + 1"),
            "last_confirmed": today,
            "revenue_share_pct": text(
                "COALESCE(EXCLUDED.revenue_share_pct, sc_relationships.revenue_share_pct)"
            ),
            "disclosed_rev_cr": text(
                "COALESCE(EXCLUDED.disclosed_rev_cr, sc_relationships.disclosed_rev_cr)"
            ),
            "is_active": True,
            "updated_at": datetime.utcnow(),
        },
    ).returning(CompanyRelationship.id)

    result = await db.execute(stmt)
    row = result.fetchone()
    rel_id = str(row[0]) if row else None

    # Add evidence record
    if rel_id and evidence_text:
        db.add(RelationshipEvidence(
            relationship_id=rel_id,
            source_isin=source_isin,
            target_isin=target_isin,
            doc_type=doc_type,
            doc_url=doc_url,
            fiscal_year=fiscal_year,
            evidence_text=evidence_text[:400],
            extraction_conf=confidence,
        ))

    return rel_id


# ─── Process a document for relationship extraction ───────────────────────────
async def process_document_for_graph(
    db: AsyncSession,
    isin: str,
    company_name: str,
    doc_text: str,
    doc_type: str,
    doc_url: str | None = None,
    fiscal_year: int | None = None,
    known_isins: dict[str, str] | None = None,
) -> dict:
    """
    Extract relationships from a document and upsert into graph.
    Returns stats: {extracted, upserted, skipped}.
    """
    stats = {"extracted": 0, "upserted": 0, "skipped": 0}

    # Use specialized extractor for annual reports (customer concentration)
    if doc_type in ("ANNUAL_REPORT", "QUARTERLY_RESULTS"):
        rels = await extract_customer_concentration(doc_text, company_name, isin)
    else:
        rels = await extract_relationships(doc_text, company_name, isin, doc_type)

    stats["extracted"] = len(rels)

    # Try to resolve unresolved ISINs
    for rel in rels:
        if not rel.get("source_isin") and rel.get("source_name") and known_isins:
            rel["source_isin"] = await resolve_company_isin(rel["source_name"], known_isins)
        if not rel.get("target_isin") and rel.get("target_name") and known_isins:
            rel["target_isin"] = await resolve_company_isin(rel["target_name"], known_isins)

    for rel in rels:
        # Skip relationships where we can't resolve at least one ISIN
        src_isin = rel.get("source_isin")
        tgt_isin = rel.get("target_isin")
        if not src_isin and not tgt_isin:
            stats["skipped"] += 1
            continue

        # Use placeholder ISIN for unresolved names
        src_isin = src_isin or f"UNKNOWN_{_name_hash(rel.get('source_name', ''))}"
        tgt_isin = tgt_isin or f"UNKNOWN_{_name_hash(rel.get('target_name', ''))}"

        # Ensure both nodes exist
        await upsert_node(db, src_isin, rel.get("source_name", "Unknown"))
        await upsert_node(db, tgt_isin, rel.get("target_name", "Unknown"))

        await upsert_relationship(
            db=db,
            source_isin=src_isin,
            source_name=rel.get("source_name", ""),
            target_isin=tgt_isin,
            target_name=rel.get("target_name", ""),
            rel_type=rel.get("rel_type", "SUPPLIES_TO"),
            product_category=rel.get("product_category"),
            strength=float(rel.get("strength", rel.get("confidence", 0.5))),
            confidence=float(rel.get("confidence", 0.5)),
            revenue_share_pct=rel.get("revenue_share_pct"),
            disclosed_rev_cr=rel.get("disclosed_rev_cr"),
            discovery_method="AI_EXTRACTION",
            evidence_text=rel.get("evidence_text"),
            doc_type=doc_type,
            doc_url=doc_url,
            fiscal_year=fiscal_year,
        )
        stats["upserted"] += 1

    await db.commit()
    return stats


def _name_hash(name: str) -> str:
    return hashlib.md5(name.lower().encode()).hexdigest()[:8].upper()


# ─── Seed known relationships from customer concentration ─────────────────────
async def seed_from_instruments_master(db: AsyncSession) -> int:
    """
    Bootstrap graph nodes from the instruments_master table.
    Also infer product categories from sector/industry tags.
    """
    result = await db.execute(text("""
    SELECT isin, symbol_nse, company_name, sector, industry, market_cap_cr, market_cap_cat
    FROM instruments_master
    WHERE is_active = true
    """))
    rows = result.fetchall()
    count = 0

    # Sector → product category heuristics
    sector_product_map = {
        "Cables": ["cables"],
        "Transformers": ["transformers"],
        "Switchgear": ["switchgear"],
        "Pipes": ["pipes"],
        "Valves": ["valves"],
        "Pumps": ["pumps"],
        "Compressors": ["compressors_industrial"],
        "Steel": ["structural_steel", "fabrication"],
        "Forgings": ["forgings", "castings"],
        "Construction": ["civil_construction"],
        "Electronics": ["electronics", "instrumentation"],
        "Software": ["IT_systems", "software"],
        "Logistics": ["logistics", "shipping"],
    }

    for row in rows:
        products = []
        for key, cats in sector_product_map.items():
            if key.lower() in (row.industry or "").lower() or key.lower() in (row.sector or "").lower():
                products.extend(cats)

        await upsert_node(
            db, row.isin, row.company_name,
            symbol_nse=row.symbol_nse,
            sector=row.sector,
            industry=row.industry,
            market_cap_cr=row.market_cap_cr,
            market_cap_cat=row.market_cap_cat,
            product_categories=products or None,
            supply_chain_tier=1 if (row.market_cap_cr or 0) > 50000 else 2,
        )
        count += 1

    await db.commit()
    return count


# ─── Infer tier-1 relationships from market structure ────────────────────────
async def infer_structural_relationships(db: AsyncSession) -> int:
    """
    For companies whose product categories overlap with known prime contractors,
    create inferred (low-confidence) SUPPLIES_TO relationships.
    Used as baseline before AI extraction runs.
    """
    PRIME_CONTRACTORS = {
        "INE018A01030": ("L&T", ["POWER_T&D", "RAILWAYS", "HYDROCARBON", "DEFENCE"]),
        "INE257F01010": ("BHEL", ["POWER_T&D", "HYDROCARBON"]),
        "INE053F01010": ("NCC Ltd", ["ROADS_HIGHWAYS", "URBAN_INFRA"]),
        "INE200A01026": ("Kalpataru Power", ["POWER_T&D", "RAILWAYS"]),
    }

    CATEGORY_TO_SECTOR = {
        "cables":        ["Cables"],
        "transformers":  ["Transformers", "Heavy Electrical"],
        "pipes":         ["Pipes", "Steel"],
        "switchgear":    ["Switchgear", "Electrical Equipment"],
        "fabrication":   ["Steel", "Metal Fabrication"],
        "civil_construction": ["Construction"],
    }

    inserted = 0
    for prime_isin, (prime_name, themes) in PRIME_CONTRACTORS.items():
        await upsert_node(db, prime_isin, prime_name, supply_chain_tier=1)

        for cat, sectors in CATEGORY_TO_SECTOR.items():
            for sector in sectors:
                result = await db.execute(text("""
                SELECT isin, company_name FROM sc_nodes
                WHERE (sector ILIKE :sector OR industry ILIKE :sector)
                  AND isin != :prime_isin
                  AND market_cap_cr BETWEEN 100 AND 30000
                LIMIT 20
                """), {"sector": f"%{sector}%", "prime_isin": prime_isin})
                suppliers = result.fetchall()

                for sup in suppliers:
                    await upsert_relationship(
                        db=db,
                        source_isin=sup.isin,
                        source_name=sup.company_name,
                        target_isin=prime_isin,
                        target_name=prime_name,
                        rel_type="SUPPLIES_TO",
                        product_category=cat,
                        strength=0.35,   # low confidence until AI confirms
                        confidence=0.35,
                        discovery_method="INDUSTRY_INFERENCE",
                        evidence_text=f"Inferred: {sector} sector company likely supplies {cat} to {prime_name}",
                    )
                    inserted += 1

    await db.commit()
    return inserted
