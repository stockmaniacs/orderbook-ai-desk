"""
Subcontract Opportunity AI Worker — SQLAlchemy Models.

Graph structure stored in PostgreSQL (adjacency list).
No Neo4j required — recursive CTEs handle multi-hop traversals.

Core concept:
  When Company A (e.g. L&T) wins a large order, traverse the supply-chain
  graph to find all companies that SUPPLY to / FABRICATE for / CONTRACT to A,
  score them by relationship strength × category fit × order size, and
  produce a ranked list of likely subcontract beneficiaries.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float,
    Integer, Numeric, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. Supply-chain graph NODES
#    One row per listed company; mirrors instruments_master but enriched with
#    supply-chain metadata (what they make, who they sell to).
# ─────────────────────────────────────────────────────────────────────────────
class SupplyChainNode(Base):
    __tablename__ = "sc_nodes"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin           = Column(String(12), unique=True, nullable=False, index=True)
    symbol_nse     = Column(String(20), index=True)
    company_name   = Column(String(255), nullable=False)
    sector         = Column(String(100))
    industry       = Column(String(100))
    market_cap_cr  = Column(Numeric(20, 2))
    market_cap_cat = Column(String(10))

    # What this company makes / does (for category-fit scoring)
    product_categories = Column(JSONB)
    # e.g. ["cables", "power_transformers", "switchgear"]

    supply_chain_tier  = Column(SmallInteger, default=2)
    # 1 = prime contractor (L&T, BHEL), 2 = tier-1 supplier, 3 = tier-2 etc.

    # Customer concentration from latest annual report
    top_customers      = Column(JSONB)
    # [{name, isin_or_null, revenue_pct, year}]

    # Revenue breakdown by end-market
    end_market_mix     = Column(JSONB)
    # {infra:40, power:30, defence:20, oil_gas:10}

    # Graph metadata
    in_degree          = Column(Integer, default=0)   # how many companies supply TO this
    out_degree         = Column(Integer, default=0)   # how many companies this supplies TO
    centrality_score   = Column(Float, default=0.0)   # PageRank-style importance

    last_graph_update  = Column(DateTime(timezone=True))
    created_at         = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at         = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Supply-chain graph EDGES (directed relationships)
#    source --[rel_type]--> target
#    e.g. "KEI Industries" --[CABLE_SUPPLIER_TO]--> "L&T"
# ─────────────────────────────────────────────────────────────────────────────
class CompanyRelationship(Base):
    __tablename__ = "sc_relationships"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source node (the SUPPLIER / VENDOR / FABRICATOR)
    source_isin     = Column(String(12), nullable=False, index=True)
    source_name     = Column(String(255))

    # Target node (the PRIME CONTRACTOR receiving the order)
    target_isin     = Column(String(12), nullable=False, index=True)
    target_name     = Column(String(255))

    # Relationship type
    rel_type        = Column(String(50), nullable=False)
    # SUPPLIES_TO | FABRICATES_FOR | EPC_SUBCONTRACTOR_TO | CABLE_SUPPLIER_TO
    # TRANSFORMER_SUPPLIER_TO | PIPE_SUPPLIER_TO | COMPONENT_MAKER_FOR
    # INSTALLS_FOR | LOGISTICS_FOR | SERVICE_PROVIDER_TO
    # COMPETES_WITH | SUBSIDIARY_OF | PEER_OF | JV_PARTNER_WITH

    # Product / service category of this relationship
    product_category = Column(String(100))
    # cables | transformers | pipes | fabrication | civil | electrical |
    # instrumentation | compressors | valves | pumps | switchgear | etc.

    # Edge weights
    strength        = Column(Float, default=0.5)
    # 0.0–1.0: 1.0 = explicitly stated in filing with revenue figures
    #           0.7 = mentioned multiple times across sources
    #           0.5 = single mention / inferred
    #           0.3 = industry inference only

    revenue_share_pct = Column(Float)
    # % of source company's revenue from this relationship (if disclosed)

    disclosed_rev_cr  = Column(Numeric(20, 4))
    # actual ₹ Cr value if disclosed in customer concentration table

    # How was this relationship discovered?
    discovery_method  = Column(String(50))
    # AI_EXTRACTION | CUSTOMER_CONCENTRATION | MANUAL | INDUSTRY_REPORT | CONCALL

    # Evidence sources
    evidence_count    = Column(Integer, default=1)
    first_seen        = Column(Date)
    last_confirmed    = Column(Date)
    is_active         = Column(Boolean, default=True)

    # Confidence in this edge
    confidence        = Column(Float, default=0.5)   # 0–1
    confidence_reason = Column(Text)

    created_at        = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at        = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source_isin", "target_isin", "rel_type", "product_category",
            name="uq_relationship",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Relationship evidence (what documents support each edge)
# ─────────────────────────────────────────────────────────────────────────────
class RelationshipEvidence(Base):
    __tablename__ = "sc_relationship_evidence"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relationship_id  = Column(UUID(as_uuid=True), nullable=False, index=True)
    source_isin      = Column(String(12), nullable=False)
    target_isin      = Column(String(12), nullable=False)

    # Source document
    doc_type         = Column(String(50))
    doc_url          = Column(Text)
    doc_title        = Column(Text)
    fiscal_year      = Column(Integer)
    quarter          = Column(String(10))

    # Exact text that supports this relationship
    evidence_text    = Column(Text)   # verbatim excerpt (max ~300 chars)
    extraction_model = Column(String(100))
    extraction_conf  = Column(Float)

    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Subcontract Opportunities
#    Generated when a large order win is detected for a prime contractor.
#    One record per (order_announcement, analysis_run).
# ─────────────────────────────────────────────────────────────────────────────
class SubcontractOpportunity(Base):
    __tablename__ = "sc_opportunities"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Triggering order
    order_announcement_id = Column(UUID(as_uuid=True), index=True)
    prime_contractor_isin = Column(String(12), nullable=False, index=True)
    prime_contractor_name = Column(String(255))

    # Order details
    order_amount_cr     = Column(Numeric(20, 4))
    order_customer      = Column(String(255))
    order_sector        = Column(String(100))
    order_description   = Column(Text)
    announced_date      = Column(Date)

    # Opportunity classification
    theme               = Column(String(100))
    # INFRASTRUCTURE | POWER_T&D | DEFENCE | RAILWAYS | ROADS | PORTS |
    # HYDROCARBON | WATER | URBAN_INFRA | GREEN_ENERGY | DATA_CENTRES

    sub_themes          = Column(JSONB)   # ["metro_rail", "signalling", "civil"]

    # Estimated subcontract pool
    estimated_subcontract_cr = Column(Numeric(20, 4))
    # Typically 30–60% of order value goes to subcontractors

    subcontract_ratio   = Column(Float)   # e.g. 0.45 = 45% subcontracted

    # Analysis metadata
    beneficiary_count   = Column(Integer, default=0)
    analysis_version    = Column(Integer, default=1)
    analysis_model      = Column(String(100))

    status              = Column(String(20), default="ACTIVE")
    # ACTIVE | SUPERSEDED | CLOSED

    created_at          = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at          = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Opportunity Beneficiaries (the ranked output)
#    One row per (opportunity, candidate_company).
# ─────────────────────────────────────────────────────────────────────────────
class OpportunityBeneficiary(Base):
    __tablename__ = "sc_beneficiaries"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id       = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Beneficiary company
    beneficiary_isin     = Column(String(12), nullable=False, index=True)
    beneficiary_name     = Column(String(255))
    beneficiary_sector   = Column(String(100))
    beneficiary_mcap_cr  = Column(Numeric(20, 4))

    # Supply chain position
    relationship_type    = Column(String(50))    # e.g. CABLE_SUPPLIER_TO
    product_category     = Column(String(100))   # e.g. cables
    supply_chain_hops    = Column(Integer, default=1)  # 1=direct, 2=tier-2

    # Scoring (all 0–100)
    probability_score    = Column(Float)
    # P(this company wins subcontract work from this order)

    revenue_impact_cr    = Column(Numeric(20, 4))
    # Estimated ₹ Cr revenue this company could receive

    revenue_impact_pct   = Column(Float)
    # % of beneficiary's TTM revenue

    confidence_score     = Column(Float)
    # How confident we are in this estimate (based on evidence quality)

    overall_score        = Column(Float)
    # Composite score for ranking:
    # probability × confidence × min(revenue_impact_pct/10, 1) × 100

    rank                 = Column(Integer)   # 1 = best opportunity

    # Breakdown of scoring
    score_breakdown      = Column(JSONB)
    # {relationship_strength, category_fit, order_size_factor,
    #  historical_accuracy, revenue_materiality}

    # AI narrative
    rationale            = Column(Text)
    key_risks            = Column(JSONB)   # [str]
    key_catalysts        = Column(JSONB)   # [str]
    investment_action    = Column(String(50))
    # STRONG_BUY_TRIGGER | BUY_TRIGGER | MONITOR | WATCH | UNLIKELY

    # Relationship path from beneficiary to prime contractor
    relationship_path    = Column(JSONB)
    # [{from_isin, to_isin, rel_type, strength}, ...]

    created_at           = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("opportunity_id", "beneficiary_isin", name="uq_opp_beneficiary"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Sector themes (classify orders into supply-chain themes)
# ─────────────────────────────────────────────────────────────────────────────
class SectorTheme(Base):
    __tablename__ = "sc_sector_themes"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    theme_name      = Column(String(100), unique=True, nullable=False)
    description     = Column(Text)

    # Which product categories are typically subcontracted for this theme
    typical_subcontract_categories = Column(JSONB)
    # ["cables", "transformers", "switchgear", "pipes"]

    # Typical subcontract ratio for this theme
    typical_subcontract_ratio = Column(Float)

    # Which sectors benefit from this theme
    beneficiary_sectors = Column(JSONB)
    # ["electrical", "capital_goods", "metals", "logistics"]

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Relationship accuracy tracking (learn from past predictions)
# ─────────────────────────────────────────────────────────────────────────────
class PredictionOutcome(Base):
    __tablename__ = "sc_prediction_outcomes"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id   = Column(UUID(as_uuid=True), nullable=False, index=True)
    beneficiary_isin = Column(String(12), nullable=False)
    predicted_prob   = Column(Float)
    predicted_rev_cr = Column(Numeric(20, 4))

    # Outcome (filled in after next quarter results)
    was_correct      = Column(Boolean)
    actual_rev_impact_cr = Column(Numeric(20, 4))
    actual_rev_growth_pct = Column(Float)
    outcome_source   = Column(String(100))  # "Q2FY27 results"
    outcome_notes    = Column(Text)

    outcome_date     = Column(Date)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
