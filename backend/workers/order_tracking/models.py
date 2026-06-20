"""
Order Tracking Worker — SQLAlchemy Models
Tracks corporate order wins announced on BSE/NSE by Indian companies.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 1. Individual order announcements (raw + AI-enriched)
# ---------------------------------------------------------------------------
class OrderAnnouncement(Base):
    __tablename__ = "order_announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Source ──────────────────────────────────────────────────────────────
    source = Column(String(20), nullable=False)       # BSE | NSE
    source_id = Column(String(255), nullable=False)   # exchange-assigned filing ID
    source_url = Column(Text)
    pdf_object_key = Column(Text)                     # Oracle Object Storage key

    # ── Company ─────────────────────────────────────────────────────────────
    isin = Column(String(12), nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    symbol_nse = Column(String(20))
    symbol_bse = Column(String(20))
    sector = Column(String(100))

    # ── Order Details (AI-extracted) ─────────────────────────────────────────
    customer_name = Column(String(255))
    order_amount_cr = Column(Numeric(20, 4))     # normalised to ₹ crores
    order_amount_raw = Column(String(200))       # original string, e.g. "₹ 2,345 Cr"
    order_currency = Column(String(10), default="INR")
    order_type = Column(String(20))              # DOMESTIC | EXPORT | MIXED
    project_description = Column(Text)

    # ── Timeline ─────────────────────────────────────────────────────────────
    announced_date = Column(Date, nullable=False, index=True)
    execution_start = Column(Date)
    execution_end = Column(Date)
    duration_months = Column(Integer)

    # ── Classification ───────────────────────────────────────────────────────
    sector_category = Column(String(100))  # INFRASTRUCTURE | DEFENSE | POWER | RAILWAYS...
    project_type = Column(String(100))     # EPC | SUPPLY | SERVICE | TURNKEY
    is_repeat_order = Column(Boolean, default=False)
    is_framework_contract = Column(Boolean, default=False)

    # ── Fiscal Period ────────────────────────────────────────────────────────
    fiscal_year = Column(Integer)      # 2026 for FY26
    quarter = Column(String(10))       # Q1FY26

    # ── AI Extraction Metadata ───────────────────────────────────────────────
    raw_text = Column(Text)
    extraction_confidence = Column(Numeric(4, 3))  # 0.000 – 1.000
    extraction_model = Column(String(100))
    extraction_notes = Column(Text)

    # ── Processing ───────────────────────────────────────────────────────────
    processing_status = Column(String(20), default="PENDING", index=True)
    # PENDING | PROCESSING | DONE | FAILED
    content_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 dedup

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_order_source_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrderAnnouncement {self.company_name} "
            f"₹{self.order_amount_cr}Cr {self.announced_date}>"
        )


# ---------------------------------------------------------------------------
# 2. Quarterly order book snapshot (carry-in + new orders - executed)
# ---------------------------------------------------------------------------
class OrderBookSnapshot(Base):
    __tablename__ = "order_book_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin = Column(String(12), nullable=False, index=True)
    company_name = Column(String(255))

    # Period
    quarter = Column(String(10), nullable=False)     # Q1FY26
    fiscal_year = Column(Integer, nullable=False)
    quarter_num = Column(Integer, nullable=False)    # 1 | 2 | 3 | 4
    snapshot_date = Column(Date, nullable=False)

    # Order book build-up (₹ crores)
    opening_order_book_cr = Column(Numeric(20, 4))   # carry from last quarter
    new_orders_cr = Column(Numeric(20, 4))           # won this quarter
    revenue_executed_cr = Column(Numeric(20, 4))     # revenue from order book
    closing_order_book_cr = Column(Numeric(20, 4))   # = opening + new − executed

    # Counts
    order_count = Column(Integer, default=0)
    large_order_count = Column(Integer, default=0)   # > ₹500 Cr

    # Mix
    domestic_orders_cr = Column(Numeric(20, 4), default=0)
    export_orders_cr = Column(Numeric(20, 4), default=0)

    # Reference revenue (linked from Fundamental Worker)
    quarterly_revenue_cr = Column(Numeric(20, 4))
    annual_revenue_ttm_cr = Column(Numeric(20, 4))

    # Flags
    is_estimated = Column(Boolean, default=False)    # AI estimate vs reported
    estimation_method = Column(String(100))

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("isin", "quarter", name="uq_snapshot_isin_quarter"),
    )


# ---------------------------------------------------------------------------
# 3. Computed metrics (updated after every new order or quarterly close)
# ---------------------------------------------------------------------------
class OrderBookMetrics(Base):
    __tablename__ = "order_book_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin = Column(String(12), nullable=False, unique=True, index=True)
    company_name = Column(String(255))

    # ── Current State ────────────────────────────────────────────────────────
    current_order_book_cr = Column(Numeric(20, 4))
    last_order_date = Column(Date)
    total_orders_count = Column(Integer, default=0)
    ttm_orders_won_cr = Column(Numeric(20, 4))      # trailing 12-month inflows

    # ── Growth ───────────────────────────────────────────────────────────────
    order_inflow_growth_yoy_pct = Column(Numeric(10, 4))  # TTM vs prior TTM
    order_book_growth_yoy_pct = Column(Numeric(10, 4))    # closing OB YoY
    order_book_cagr_3y = Column(Numeric(10, 4))
    order_book_cagr_5y = Column(Numeric(10, 4))

    # ── Ratios ───────────────────────────────────────────────────────────────
    order_book_to_sales = Column(Numeric(10, 4))        # OB ÷ TTM revenue
    order_book_to_sales_prev = Column(Numeric(10, 4))   # last year (for trend)
    bill_to_book_ratio = Column(Numeric(10, 4))         # order intake ÷ revenue
    order_to_sales_trend = Column(String(20))           # IMPROVING | STABLE | DETERIORATING

    # ── Acceleration Score (0–100) ───────────────────────────────────────────
    # Composite of: QoQ growth acceleration, Bill-to-Book > 1, improving OB/Sales
    order_acceleration_score = Column(Numeric(5, 2))
    order_momentum = Column(String(20))  # ACCELERATING | STABLE | DECELERATING

    # ── Scenario Projections ─────────────────────────────────────────────────
    bull_case_ob_cr = Column(Numeric(20, 4))
    base_case_ob_cr = Column(Numeric(20, 4))
    bear_case_ob_cr = Column(Numeric(20, 4))
    scenario_horizon_quarters = Column(Integer, default=4)  # projection window
    scenario_assumptions = Column(JSONB)  # {bull: {...}, base: {...}, bear: {...}}

    # ── Mix ──────────────────────────────────────────────────────────────────
    domestic_pct = Column(Numeric(6, 3))
    export_pct = Column(Numeric(6, 3))
    sector_breakdown = Column(JSONB)   # {"POWER": 45.2, "RAILWAYS": 30.1, ...}
    customer_concentration = Column(JSONB)  # top customers by share

    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ---------------------------------------------------------------------------
# 4. AI-generated analysis summary per company
# ---------------------------------------------------------------------------
class OrderAISummary(Base):
    __tablename__ = "order_ai_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isin = Column(String(12), nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    # Overall verdict
    trend = Column(String(20))           # IMPROVING | STABLE | DETERIORATING
    trend_confidence = Column(Numeric(4, 3))

    # Narrative sections
    executive_summary = Column(Text)
    pipeline_analysis = Column(Text)
    customer_concentration_note = Column(Text)
    geographic_mix_note = Column(Text)

    # Structured signals
    risk_factors = Column(JSONB)         # [{"risk": "...", "severity": "HIGH"}]
    positive_signals = Column(JSONB)     # [{"signal": "...", "impact": "HIGH"}]
    key_customers = Column(JSONB)        # [{"name": "...", "pct": 35}]

    # Scenario narratives
    bull_narrative = Column(Text)
    base_narrative = Column(Text)
    bear_narrative = Column(Text)

    # One-liner verdict
    ai_verdict = Column(Text)

    model_version = Column(String(100))
    prompt_version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
