"""
Graph Traversal — Subcontract Opportunity Worker.

PostgreSQL-based graph queries using recursive CTEs.
No Neo4j needed — adjacency list + CTE handles N-hop traversals efficiently.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Find all suppliers up to N hops from a prime contractor ─────────────────
SUPPLIER_CTE_SQL = """
WITH RECURSIVE supply_chain AS (
    -- Base case: direct (tier-1) suppliers of the prime contractor
    SELECT
        r.source_isin,
        r.source_name,
        r.target_isin,
        r.target_name,
        r.rel_type,
        r.product_category,
        r.strength,
        r.revenue_share_pct,
        r.disclosed_rev_cr,
        r.confidence,
        1                           AS hops,
        ARRAY[r.source_isin]        AS path_isins,
        jsonb_build_array(
            jsonb_build_object(
                'from_isin',    r.source_isin,
                'from_name',    r.source_name,
                'to_isin',      r.target_isin,
                'to_name',      r.target_name,
                'rel_type',     r.rel_type,
                'strength',     r.strength
            )
        )                           AS path_json

    FROM sc_relationships r
    WHERE r.target_isin = :prime_isin
      AND r.is_active = true
      AND r.strength >= :min_strength

    UNION ALL

    -- Recursive case: suppliers of suppliers (tier-2+)
    SELECT
        r.source_isin,
        r.source_name,
        r.target_isin,
        r.target_name,
        r.rel_type,
        r.product_category,
        r.strength * sc.strength    AS strength,   -- compound strength
        r.revenue_share_pct,
        r.disclosed_rev_cr,
        r.confidence * sc.confidence AS confidence,
        sc.hops + 1                 AS hops,
        sc.path_isins || r.source_isin,
        sc.path_json || jsonb_build_object(
            'from_isin',    r.source_isin,
            'from_name',    r.source_name,
            'to_isin',      r.target_isin,
            'to_name',      r.target_name,
            'rel_type',     r.rel_type,
            'strength',     r.strength
        )

    FROM sc_relationships r
    JOIN supply_chain sc ON r.target_isin = sc.source_isin
    WHERE sc.hops < :max_hops
      AND r.is_active = true
      AND r.strength >= :min_strength
      AND NOT (r.source_isin = ANY(sc.path_isins))   -- cycle guard
)
SELECT DISTINCT ON (source_isin, product_category)
    sc.source_isin,
    sc.source_name,
    sc.rel_type,
    sc.product_category,
    sc.strength,
    sc.revenue_share_pct,
    sc.disclosed_rev_cr,
    sc.confidence,
    sc.hops,
    sc.path_json,
    n.sector          AS beneficiary_sector,
    n.market_cap_cr   AS beneficiary_mcap_cr,
    n.product_categories AS node_products
FROM supply_chain sc
LEFT JOIN sc_nodes n ON n.isin = sc.source_isin
ORDER BY source_isin, product_category, hops ASC, strength DESC
"""


async def find_suppliers(
    db: AsyncSession,
    prime_isin: str,
    max_hops: int = 2,
    min_strength: float = 0.3,
) -> list[dict]:
    """
    Find all companies that supply to the prime contractor, up to max_hops.
    Returns list of supplier dicts with path information.
    """
    result = await db.execute(
        text(SUPPLIER_CTE_SQL),
        {"prime_isin": prime_isin, "max_hops": max_hops, "min_strength": min_strength},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


# ─── Find all customers of a supplier ────────────────────────────────────────
async def find_customers(
    db: AsyncSession,
    supplier_isin: str,
    min_strength: float = 0.2,
) -> list[dict]:
    """Return all prime contractors that a given supplier serves."""
    result = await db.execute(
        text("""
        SELECT
            r.target_isin, r.target_name,
            r.rel_type, r.product_category,
            r.strength, r.revenue_share_pct,
            r.disclosed_rev_cr, r.confidence,
            n.sector, n.market_cap_cr
        FROM sc_relationships r
        LEFT JOIN sc_nodes n ON n.isin = r.target_isin
        WHERE r.source_isin = :supplier_isin
          AND r.is_active = true
          AND r.strength >= :min_strength
        ORDER BY r.strength DESC
        """),
        {"supplier_isin": supplier_isin, "min_strength": min_strength},
    )
    return [dict(r) for r in result.mappings().all()]


# ─── Shortest path between two companies ─────────────────────────────────────
SHORTEST_PATH_SQL = """
WITH RECURSIVE path_search AS (
    SELECT
        r.source_isin, r.target_isin,
        r.rel_type, r.product_category, r.strength,
        1 AS hops,
        ARRAY[r.source_isin, r.target_isin] AS visited,
        jsonb_build_array(
            jsonb_build_object('from', r.source_isin, 'to', r.target_isin,
                               'rel', r.rel_type, 'strength', r.strength)
        ) AS path
    FROM sc_relationships r
    WHERE r.source_isin = :from_isin AND r.is_active = true

    UNION ALL

    SELECT
        r.source_isin, r.target_isin,
        r.rel_type, r.product_category,
        ps.strength * r.strength,
        ps.hops + 1,
        ps.visited || r.target_isin,
        ps.path || jsonb_build_object(
            'from', r.source_isin, 'to', r.target_isin,
            'rel', r.rel_type, 'strength', r.strength
        )
    FROM sc_relationships r
    JOIN path_search ps ON r.source_isin = ps.target_isin
    WHERE NOT r.target_isin = ANY(ps.visited)
      AND ps.hops < 4
      AND r.is_active = true
)
SELECT path, hops, strength
FROM path_search
WHERE target_isin = :to_isin
ORDER BY hops ASC, strength DESC
LIMIT 1
"""


async def find_shortest_path(
    db: AsyncSession,
    from_isin: str,
    to_isin: str,
) -> dict | None:
    """Find shortest supply-chain path between two companies."""
    result = await db.execute(
        text(SHORTEST_PATH_SQL),
        {"from_isin": from_isin, "to_isin": to_isin},
    )
    row = result.mappings().first()
    return dict(row) if row else None


# ─── Graph statistics for a company ──────────────────────────────────────────
async def get_node_stats(db: AsyncSession, isin: str) -> dict:
    """Return degree, centrality, and relationship breakdown for a company."""
    result = await db.execute(
        text("""
        SELECT
            COUNT(*) FILTER (WHERE target_isin = :isin) AS in_degree,
            COUNT(*) FILTER (WHERE source_isin = :isin) AS out_degree,
            COUNT(DISTINCT CASE WHEN target_isin = :isin THEN source_isin END) AS supplier_count,
            COUNT(DISTINCT CASE WHEN source_isin = :isin THEN target_isin END) AS customer_count,
            AVG(CASE WHEN target_isin = :isin THEN strength END) AS avg_supplier_strength,
            json_agg(DISTINCT product_category) FILTER (WHERE target_isin = :isin) AS products_received
        FROM sc_relationships
        WHERE (source_isin = :isin OR target_isin = :isin) AND is_active = true
        """),
        {"isin": isin},
    )
    row = result.mappings().first()
    return dict(row) if row else {}


# ─── Update node degree counts ────────────────────────────────────────────────
async def refresh_node_degrees(db: AsyncSession) -> None:
    """Recompute in_degree and out_degree for all nodes from edge data."""
    await db.execute(text("""
    UPDATE sc_nodes n SET
        in_degree  = (SELECT COUNT(*) FROM sc_relationships WHERE target_isin = n.isin AND is_active),
        out_degree = (SELECT COUNT(*) FROM sc_relationships WHERE source_isin = n.isin AND is_active),
        last_graph_update = NOW()
    """))
    await db.commit()


# ─── PageRank-style centrality (simplified iterative) ────────────────────────
async def compute_centrality(db: AsyncSession, iterations: int = 10) -> None:
    """
    Simple iterative centrality approximation.
    High centrality = many companies depend on or supply to this node.
    """
    # Initialize
    await db.execute(text("UPDATE sc_nodes SET centrality_score = 1.0"))

    for _ in range(iterations):
        await db.execute(text("""
        UPDATE sc_nodes n SET centrality_score = (
            SELECT COALESCE(SUM(r.strength * src.centrality_score / NULLIF(src.out_degree, 1)), 0)
            FROM sc_relationships r
            JOIN sc_nodes src ON src.isin = r.source_isin
            WHERE r.target_isin = n.isin AND r.is_active = true
        ) * 0.85 + 0.15
        """))

    await db.commit()
