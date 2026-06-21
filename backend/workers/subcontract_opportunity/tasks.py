"""
Celery tasks — Subcontract Opportunity Worker.

Tasks:
  - analyze_order_opportunity_task: triggered when a new large order win is detected
  - process_company_supply_chain_task: build graph from one company's docs
  - batch_graph_rebuild_task: nightly full graph rebuild
  - refresh_graph_metrics_task: recompute degrees + centrality weekly
  - update_prediction_outcomes_task: track accuracy of past predictions
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import text

from database import get_async_session_context
from .service import (
    analyze_order_opportunity,
    get_graph_stats,
    process_company_supply_chain,
    rebuild_graph,
    record_prediction_outcome,
)
from .graph.traversal import compute_centrality, refresh_node_degrees

log = logging.getLogger(__name__)

# Orders above this threshold trigger subcontract analysis
MINIMUM_ORDER_CR_FOR_ANALYSIS = 500.0


# ─── On order win: full analysis pipeline ────────────────────────────────────
@shared_task(
    name="subcontract.analyze_order_opportunity",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="subcontract_high",
)
def analyze_order_opportunity_task(
    self,
    *,
    prime_contractor_isin: str,
    prime_contractor_name: str,
    order_amount_cr: float,
    order_customer: str | None = None,
    order_sector: str | None = None,
    order_description: str | None = None,
    announced_date: str | None = None,
    order_announcement_id: str | None = None,
) -> dict:
    """
    Triggered by Order Tracking Worker when a large order win is detected.
    """
    if order_amount_cr < MINIMUM_ORDER_CR_FOR_ANALYSIS:
        return {"status": "skipped", "reason": f"Order ₹{order_amount_cr:.0f} Cr below threshold"}

    try:
        opp_id = asyncio.run(_run_analysis(
            prime_contractor_isin=prime_contractor_isin,
            prime_contractor_name=prime_contractor_name,
            order_amount_cr=order_amount_cr,
            order_customer=order_customer,
            order_sector=order_sector,
            order_description=order_description,
            announced_date=date.fromisoformat(announced_date) if announced_date else None,
            order_announcement_id=order_announcement_id,
        ))
        return {"status": "ok", "opportunity_id": opp_id}
    except Exception as exc:
        log.exception("analyze_order_opportunity_task failed: %s", exc)
        raise self.retry(exc=exc)


async def _run_analysis(**kwargs: Any) -> str:
    async with get_async_session_context() as db:
        return await analyze_order_opportunity(db, **kwargs)


# ─── Process one company's documents for graph ───────────────────────────────
@shared_task(
    name="subcontract.process_company_supply_chain",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="subcontract_normal",
)
def process_company_supply_chain_task(
    self,
    isin: str,
    doc_types: list[str] | None = None,
) -> dict:
    try:
        return asyncio.run(_run_company_processing(isin, doc_types))
    except Exception as exc:
        log.exception("process_company_supply_chain_task failed for %s: %s", isin, exc)
        raise self.retry(exc=exc)


async def _run_company_processing(isin: str, doc_types: list[str] | None) -> dict:
    async with get_async_session_context() as db:
        return await process_company_supply_chain(db, isin, doc_types)


# ─── Batch: rebuild graph for all / specified companies ──────────────────────
@shared_task(
    name="subcontract.batch_graph_rebuild",
    bind=True,
    queue="subcontract_normal",
    time_limit=7200,    # 2 hours max
)
def batch_graph_rebuild_task(
    self,
    isins: list[str] | None = None,
    batch_size: int = 50,
) -> dict:
    """
    Nightly batch: rebuilds supply-chain graph for all companies.
    Queues individual process_company_supply_chain_task per company.
    """
    try:
        result = asyncio.run(_rebuild_graph_prepare(isins))
        target_isins = result["isins"]
        total = len(target_isins)

        # Queue individual tasks in batches to avoid overwhelming the broker
        queued = 0
        for isin in target_isins:
            process_company_supply_chain_task.apply_async(
                kwargs={"isin": isin},
                countdown=queued * 2,  # stagger 2s apart
                queue="subcontract_normal",
            )
            queued += 1

        return {
            "status": "queued",
            "nodes_seeded": result["nodes_seeded"],
            "companies_queued": total,
        }
    except Exception as exc:
        log.exception("batch_graph_rebuild_task failed: %s", exc)
        raise


async def _rebuild_graph_prepare(isins: list[str] | None) -> dict:
    async with get_async_session_context() as db:
        return await rebuild_graph(db, isins)


# ─── Weekly: refresh graph metrics (degrees + centrality) ────────────────────
@shared_task(
    name="subcontract.refresh_graph_metrics",
    queue="subcontract_normal",
)
def refresh_graph_metrics_task() -> dict:
    """Recomputes in_degree, out_degree, and centrality for all nodes."""
    return asyncio.run(_refresh_metrics())


async def _refresh_metrics() -> dict:
    async with get_async_session_context() as db:
        await refresh_node_degrees(db)
        await compute_centrality(db, iterations=10)
        stats = await get_graph_stats(db)
    return {"status": "ok", "nodes": stats.get("total_nodes"), "rels": stats.get("active_relationships")}


# ─── Monthly: update prediction outcomes from actual results ─────────────────
@shared_task(
    name="subcontract.update_prediction_outcomes",
    queue="subcontract_normal",
)
def update_prediction_outcomes_task() -> dict:
    """
    Checks whether companies flagged as STRONG_BUY/BUY actually showed
    revenue uplift in the subsequent 2 quarters (from company financials).
    """
    return asyncio.run(_update_outcomes())


async def _update_outcomes() -> dict:
    async with get_async_session_context() as db:
        # Find predictions made 2+ quarters ago without outcomes
        result = await db.execute(text("""
        SELECT b.opportunity_id, b.beneficiary_isin, b.probability_score,
               b.investment_action, opp.announced_date, opp.prime_contractor_name
        FROM sc_beneficiaries b
        JOIN sc_opportunities opp ON opp.id = b.opportunity_id
        WHERE b.investment_action IN ('STRONG_BUY_TRIGGER', 'BUY_TRIGGER')
          AND opp.announced_date < CURRENT_DATE - INTERVAL '180 days'
          AND NOT EXISTS (
              SELECT 1 FROM sc_prediction_outcomes po
              WHERE po.opportunity_id = b.opportunity_id
                AND po.beneficiary_isin = b.beneficiary_isin
          )
        LIMIT 100
        """))
        pending = result.fetchall()
        evaluated = 0

        for row in pending:
            # Check if beneficiary's revenue grew after the order
            rev_result = await db.execute(text("""
            SELECT
                AVG(revenue_cr) FILTER (WHERE period_end > :announced_date) AS post_rev,
                AVG(revenue_cr) FILTER (WHERE period_end <= :announced_date) AS pre_rev
            FROM company_financials
            WHERE isin = :isin AND period_type = 'QUARTERLY'
            """), {"isin": row.beneficiary_isin, "announced_date": row.announced_date})
            rev_row = rev_result.fetchone()

            if not rev_row or not rev_row.post_rev or not rev_row.pre_rev:
                continue

            growth_pct = (float(rev_row.post_rev) - float(rev_row.pre_rev)) / float(rev_row.pre_rev) * 100
            was_correct = growth_pct > 5  # > 5% revenue growth = correct prediction

            await record_prediction_outcome(
                db,
                opportunity_id=str(row.opportunity_id),
                beneficiary_isin=row.beneficiary_isin,
                was_correct=was_correct,
                actual_rev_growth_pct=growth_pct,
                outcome_source="AUTOMATED_FINANCIAL_CHECK",
                outcome_notes=f"Post-order revenue growth: {growth_pct:.1f}%",
            )
            evaluated += 1

    return {"status": "ok", "evaluated": evaluated}


# ─── Celery Beat schedule ─────────────────────────────────────────────────────
CELERYBEAT_SCHEDULE = {
    "subcontract-nightly-graph-rebuild": {
        "task": "subcontract.batch_graph_rebuild",
        "schedule": "0 2 * * *",   # 2 AM daily
    },
    "subcontract-weekly-metrics": {
        "task": "subcontract.refresh_graph_metrics",
        "schedule": "0 3 * * 0",   # Sunday 3 AM
    },
    "subcontract-monthly-outcomes": {
        "task": "subcontract.update_prediction_outcomes",
        "schedule": "0 4 1 * *",   # 1st of month 4 AM
    },
}
