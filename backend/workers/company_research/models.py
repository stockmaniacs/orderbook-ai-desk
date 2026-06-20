"""
Company Research Worker — SQLAlchemy Models
Permanent, incremental research repository for all NSE/BSE listed companies.

Design philosophy:
  - NEVER delete; only append or update.
  - Each extracted field is a separate versioned row (ResearchField).
  - A research report is assembled from current field values, not regenerated wholesale.
  - Only changed sections are rewritten after each quarter.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. Companies master (one row per listed company, never deleted)
# ─────────────────────────────────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "research_companies"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), unique=True, nullable=False, index=True)
    symbol_nse      = Column(String(20), index=True)
    symbol_bse      = Column(String(20), index=True)
    bse_code        = Column(String(10))
    company_name    = Column(String(255), nullable=False)
    short_name      = Column(String(100))
    sector          = Column(String(100))
    industry        = Column(String(100))
    sub_industry    = Column(String(100))
    market_cap_cr   = Column(Numeric(20, 2))
    market_cap_cat  = Column(String(10))  # LARGE | MID | SMALL | MICRO
    listing_date    = Column(Date)
    face_value      = Column(Numeric(10, 2))
    website_url     = Column(Text)
    ir_url          = Column(Text)        # investor relations page
    is_active       = Column(Boolean, default=True)

    # Research coverage flags
    research_priority     = Column(SmallInteger, default=2)  # 1=HIGH 2=MED 3=LOW
    last_research_date    = Column(DateTime(timezone=True))
    next_research_due     = Column(DateTime(timezone=True))
    research_status       = Column(String(20), default="PENDING")
    # PENDING | IN_PROGRESS | DONE | ERROR

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at      = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Source documents (every document ever fetched, immutable)
# ─────────────────────────────────────────────────────────────────────────────
class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False, index=True)
    doc_type        = Column(String(50), nullable=False)
    # ANNUAL_REPORT | INVESTOR_PRESENTATION | CONCALL_TRANSCRIPT | BSE_ANNOUNCEMENT
    # MANAGEMENT_INTERVIEW | NEWS | WEBSITE_CONTENT | CREDIT_RATING | ANALYST_REPORT

    title           = Column(Text)
    source          = Column(String(50))   # BSE | NSE | COMPANY | NEWS_FEED | YOUTUBE
    source_url      = Column(Text)
    object_store_key= Column(Text)         # Oracle Object Storage key for raw file
    fiscal_year     = Column(Integer)
    quarter         = Column(String(10))   # Q1FY26 | ANNUAL
    published_date  = Column(Date)
    page_count      = Column(Integer)
    file_size_bytes = Column(BigInteger)
    content_hash    = Column(String(64), unique=True)  # SHA-256 dedup

    # Processing state
    text_extracted  = Column(Boolean, default=False)
    ai_extracted    = Column(Boolean, default=False)
    extract_errors  = Column(JSONB)
    processed_at    = Column(DateTime(timezone=True))

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Document text chunks + embeddings (for RAG)
# ─────────────────────────────────────────────────────────────────────────────
class DocumentChunk(Base):
    __tablename__ = "research_doc_chunks"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id     = Column(UUID(as_uuid=True), nullable=False, index=True)
    isin            = Column(String(12), nullable=False, index=True)
    chunk_index     = Column(Integer, nullable=False)
    text            = Column(Text, nullable=False)
    token_count     = Column(Integer)
    # embedding stored as pgvector — declared in migration
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_idx"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Research fields — CORE TABLE
# One row per (isin, field_name). Updated incrementally; history tracked.
# ─────────────────────────────────────────────────────────────────────────────
class ResearchField(Base):
    """
    A single extracted research data point for a company.
    Examples: growth_drivers, risks, capex_plans, margins, guidance, debt_level...

    Key design: we NEVER re-extract everything. When a new document arrives,
    only fields whose source documents have changed are re-extracted.
    """
    __tablename__ = "research_fields"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False, index=True)
    field_name      = Column(String(100), nullable=False)
    # growth_drivers | risks | capex_plans | order_book | margins | guidance |
    # market_share | export_exposure | debt | promoters | pledging | subsidiaries |
    # competitive_moat | management_quality | regulatory_risks | esg_highlights |
    # recent_developments | key_metrics | business_segments | customer_concentration

    field_category  = Column(String(50))
    # FUNDAMENTALS | MANAGEMENT | MARKET | RISK | STRATEGY | GOVERNANCE

    # Current value
    value_json      = Column(JSONB)    # structured value (list, dict)
    value_text      = Column(Text)     # human-readable narrative

    # Source provenance
    source_doc_ids  = Column(JSONB)    # [uuid, ...] of supporting documents
    source_types    = Column(JSONB)    # ["annual_report", "concall", ...]
    primary_source  = Column(String(50))  # most authoritative source for this field
    as_of_date      = Column(Date)     # when the data was current
    fiscal_period   = Column(String(10))  # Q3FY26 or FY26

    # Quality
    confidence      = Column(Numeric(4, 3), default=0.5)  # 0.000 - 1.000
    is_stale        = Column(Boolean, default=False)  # True if source doc outdated

    # Versioning
    version         = Column(Integer, default=1)
    last_updated    = Column(DateTime(timezone=True), default=datetime.utcnow)
    update_reason   = Column(Text)  # why this version was created
    model_version   = Column(String(100))

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("isin", "field_name", name="uq_field_isin_name"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Research field history (append-only audit log)
# ─────────────────────────────────────────────────────────────────────────────
class ResearchFieldHistory(Base):
    __tablename__ = "research_field_history"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id        = Column(UUID(as_uuid=True), nullable=False, index=True)
    isin            = Column(String(12), nullable=False, index=True)
    field_name      = Column(String(100), nullable=False)
    version         = Column(Integer, nullable=False)
    value_text      = Column(Text)
    value_json      = Column(JSONB)
    confidence      = Column(Numeric(4, 3))
    source_types    = Column(JSONB)
    update_reason   = Column(Text)
    recorded_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Investment thesis (one per company, updated in-place)
# ─────────────────────────────────────────────────────────────────────────────
class InvestmentThesis(Base):
    __tablename__ = "investment_theses"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), unique=True, nullable=False, index=True)
    company_name    = Column(String(255))

    # Core thesis
    one_liner       = Column(Text)   # max 30-word verdict
    thesis_text     = Column(Text)   # 3-5 paragraph narrative

    # SWOT (stored as JSONB arrays)
    strengths       = Column(JSONB)  # [{point, evidence, confidence}]
    weaknesses      = Column(JSONB)
    opportunities   = Column(JSONB)
    threats         = Column(JSONB)

    # Scenarios
    bull_case       = Column(Text)
    bull_cagr_pct   = Column(Numeric(6, 2))
    bull_target_cr  = Column(Numeric(20, 2))   # target market cap

    base_case       = Column(Text)
    base_cagr_pct   = Column(Numeric(6, 2))
    base_target_cr  = Column(Numeric(20, 2))

    bear_case       = Column(Text)
    bear_cagr_pct   = Column(Numeric(6, 2))
    bear_target_cr  = Column(Numeric(20, 2))

    # Scenario probabilities
    bull_probability= Column(Numeric(5, 2))   # %
    base_probability= Column(Numeric(5, 2))
    bear_probability= Column(Numeric(5, 2))

    # Valuation
    current_price   = Column(Numeric(12, 2))
    fair_value_low  = Column(Numeric(12, 2))
    fair_value_mid  = Column(Numeric(12, 2))
    fair_value_high = Column(Numeric(12, 2))
    target_price_12m= Column(Numeric(12, 2))
    expected_cagr_3y= Column(Numeric(6, 2))

    # Rating
    rating          = Column(String(20))
    # STRONG_BUY | BUY | ACCUMULATE | HOLD | REDUCE | SELL | AVOID
    confidence_score= Column(Numeric(5, 2))  # 0-100 overall research quality score

    # Change tracking
    version         = Column(Integer, default=1)
    sections_updated= Column(JSONB)  # which sections changed this version
    last_updated    = Column(DateTime(timezone=True), default=datetime.utcnow)
    update_trigger  = Column(Text)   # "Q3FY26 results published"
    model_version   = Column(String(100))

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Research reports (markdown, versioned, never deleted)
# ─────────────────────────────────────────────────────────────────────────────
class ResearchReport(Base):
    __tablename__ = "research_reports"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False, index=True)
    company_name    = Column(String(255))
    report_version  = Column(Integer, nullable=False, default=1)
    is_current      = Column(Boolean, default=True, index=True)

    # Report content (full markdown)
    markdown_content= Column(Text, nullable=False)
    object_store_key= Column(Text)   # also stored in Oracle for durability

    # What triggered this version
    trigger         = Column(Text)   # "Q3FY26 concall processed"
    sections_changed= Column(JSONB)  # ["thesis", "risks", "valuation"]
    sections_added  = Column(JSONB)
    diff_summary    = Column(Text)   # one-line delta description

    # Metadata
    word_count      = Column(Integer)
    source_doc_count= Column(Integer)
    confidence_score= Column(Numeric(5, 2))

    generated_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("isin", "report_version", name="uq_report_isin_version"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Company financials (quarterly, authoritative numbers)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyFinancials(Base):
    __tablename__ = "research_financials"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False, index=True)
    period_type     = Column(String(10), nullable=False)  # QUARTERLY | ANNUAL
    fiscal_year     = Column(Integer, nullable=False)
    quarter         = Column(String(10))
    period_end_date = Column(Date)
    is_consolidated = Column(Boolean, default=True)

    # P&L (₹ Cr)
    revenue         = Column(Numeric(20, 4))
    gross_profit    = Column(Numeric(20, 4))
    ebitda          = Column(Numeric(20, 4))
    ebitda_margin   = Column(Numeric(8, 4))
    pat             = Column(Numeric(20, 4))
    pat_margin      = Column(Numeric(8, 4))
    eps             = Column(Numeric(12, 4))

    # Balance sheet
    total_debt      = Column(Numeric(20, 4))
    net_debt        = Column(Numeric(20, 4))
    cash            = Column(Numeric(20, 4))
    total_equity    = Column(Numeric(20, 4))

    # Cash flow
    cfo             = Column(Numeric(20, 4))
    capex           = Column(Numeric(20, 4))
    free_cash_flow  = Column(Numeric(20, 4))

    # Ratios
    roe             = Column(Numeric(8, 4))
    roce            = Column(Numeric(8, 4))
    debt_equity     = Column(Numeric(8, 4))
    interest_coverage = Column(Numeric(8, 4))

    source_doc_id   = Column(UUID(as_uuid=True))
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "isin", "period_type", "fiscal_year", "quarter", "is_consolidated",
            name="uq_financials_period",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Document processing queue (tracks what needs to be done)
# ─────────────────────────────────────────────────────────────────────────────
class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin            = Column(String(12), nullable=False, index=True)
    task_type       = Column(String(50), nullable=False)
    # FETCH_DOCUMENTS | EXTRACT_FIELDS | GENERATE_THESIS | BUILD_REPORT | UPDATE_VALUATION

    status          = Column(String(20), default="PENDING", index=True)
    priority        = Column(SmallInteger, default=5)  # 1=highest
    trigger         = Column(Text)   # what caused this task
    document_id     = Column(UUID(as_uuid=True))  # if task is doc-specific
    payload         = Column(JSONB)
    error           = Column(Text)
    attempts        = Column(Integer, default=0)

    scheduled_at    = Column(DateTime(timezone=True))
    started_at      = Column(DateTime(timezone=True))
    completed_at    = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
