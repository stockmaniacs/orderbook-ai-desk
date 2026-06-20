"""
Pydantic v2 schemas — Subcontract Opportunity Worker.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Graph node ──────────────────────────────────────────────────────────────
class SupplyChainNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isin: str
    company_name: str
    symbol_nse: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    market_cap_cat: str | None = None
    product_categories: list[str] | None = None
    supply_chain_tier: int = 2
    in_degree: int = 0
    out_degree: int = 0
    centrality_score: float = 0.0
    top_customers: list[dict] | None = None
    end_market_mix: dict | None = None
    last_graph_update: datetime | None = None


# ─── Graph edge ───────────────────────────────────────────────────────────────
class CompanyRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_isin: str
    source_name: str
    target_isin: str
    target_name: str
    rel_type: str
    product_category: str | None = None
    strength: float
    revenue_share_pct: float | None = None
    disclosed_rev_cr: float | None = None
    confidence: float
    evidence_count: int = 1
    discovery_method: str | None = None
    first_seen: date | None = None
    last_confirmed: date | None = None
    is_active: bool = True


class RelationshipEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doc_type: str | None = None
    doc_url: str | None = None
    fiscal_year: int | None = None
    evidence_text: str | None = None
    extraction_conf: float | None = None
    created_at: datetime


# ─── Path through the graph ───────────────────────────────────────────────────
class PathHop(BaseModel):
    from_isin: str
    from_name: str
    to_isin: str
    to_name: str
    rel_type: str
    strength: float


class SupplyChainPath(BaseModel):
    hops: int
    path: list[PathHop]
    compound_strength: float


# ─── Supplier result from graph traversal ─────────────────────────────────────
class SupplierResult(BaseModel):
    source_isin: str
    source_name: str
    rel_type: str
    product_category: str | None = None
    strength: float
    revenue_share_pct: float | None = None
    disclosed_rev_cr: float | None = None
    confidence: float
    hops: int
    path_json: list[dict] | None = None
    beneficiary_sector: str | None = None
    beneficiary_mcap_cr: float | None = None
    node_products: list[str] | None = None


# ─── Opportunity beneficiary ──────────────────────────────────────────────────
class ScoreBreakdown(BaseModel):
    relationship_strength: float
    category_fit: float
    revenue_materiality: float
    order_size_factor: float
    historical_accuracy: float
    hop_penalty: float
    subcontract_ratio: float


class BeneficiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    beneficiary_isin: str
    beneficiary_name: str | None = None
    beneficiary_sector: str | None = None
    beneficiary_mcap_cr: float | None = None
    relationship_type: str | None = None
    product_category: str | None = None
    supply_chain_hops: int = 1
    probability_score: float
    revenue_impact_cr: float
    revenue_impact_pct: float
    confidence_score: float
    overall_score: float
    rank: int
    score_breakdown: ScoreBreakdown | None = None
    rationale: str | None = None
    key_risks: list[str] | None = None
    key_catalysts: list[str] | None = None
    investment_action: str
    relationship_path: list[PathHop] | None = None


# ─── Opportunity ──────────────────────────────────────────────────────────────
class SubcontractOpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prime_contractor_isin: str
    prime_contractor_name: str | None = None
    order_amount_cr: float
    order_customer: str | None = None
    order_sector: str | None = None
    order_description: str | None = None
    announced_date: date | None = None
    theme: str
    sub_themes: list[str] | None = None
    estimated_subcontract_cr: float | None = None
    subcontract_ratio: float | None = None
    beneficiary_count: int = 0
    status: str = "ACTIVE"
    analysis_version: int = 1
    created_at: datetime

    # Populated on detail fetch
    beneficiaries: list[BeneficiaryOut] | None = None


class OpportunityListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prime_contractor_isin: str
    prime_contractor_name: str | None = None
    order_amount_cr: float
    order_customer: str | None = None
    theme: str
    announced_date: date | None = None
    estimated_subcontract_cr: float | None = None
    beneficiary_count: int = 0
    status: str
    created_at: datetime
    # Top beneficiary for preview
    top_beneficiary_name: str | None = None
    top_beneficiary_action: str | None = None
    top_beneficiary_score: float | None = None


# ─── Graph view for a company ─────────────────────────────────────────────────
class CompanyGraphOut(BaseModel):
    isin: str
    company_name: str
    sector: str | None = None
    stats: dict[str, Any]
    suppliers: list[CompanyRelationshipOut]
    customers: list[CompanyRelationshipOut]
    centrality_score: float | None = None
    supply_chain_tier: int | None = None


# ─── Trigger / admin requests ─────────────────────────────────────────────────
class TriggerOpportunityIn(BaseModel):
    order_announcement_id: str | None = None
    prime_contractor_isin: str
    prime_contractor_name: str
    order_amount_cr: float = Field(gt=0)
    order_customer: str | None = None
    order_sector: str | None = None
    order_description: str | None = None
    announced_date: date | None = None


class ProcessCompanyIn(BaseModel):
    isin: str
    doc_types: list[str] | None = None  # None = all types


class RebuildGraphIn(BaseModel):
    isins: list[str] | None = None   # None = all companies
    batch_size: int = 50


# ─── Universe listing ─────────────────────────────────────────────────────────
class GraphUniverseItem(BaseModel):
    isin: str
    company_name: str
    sector: str | None = None
    market_cap_cat: str | None = None
    supply_chain_tier: int
    in_degree: int
    out_degree: int
    centrality_score: float
    product_categories: list[str] | None = None


class GraphUniverseOut(BaseModel):
    total: int
    items: list[GraphUniverseItem]


# ─── Sector theme ─────────────────────────────────────────────────────────────
class SectorThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    theme_name: str
    description: str | None = None
    typical_subcontract_categories: list[str] | None = None
    typical_subcontract_ratio: float | None = None
    beneficiary_sectors: list[str] | None = None


# ─── Admin / stats ────────────────────────────────────────────────────────────
class GraphStatsOut(BaseModel):
    total_nodes: int
    total_relationships: int
    active_relationships: int
    avg_in_degree: float
    avg_out_degree: float
    top_suppliers: list[dict]   # [{isin, name, in_degree, centrality}]
    top_primes: list[dict]      # [{isin, name, out_degree}]
    theme_breakdown: dict[str, int]  # theme → opportunity count


class JobResultOut(BaseModel):
    status: str  # "queued" | "ok" | "error"
    task_id: str | None = None
    message: str | None = None
