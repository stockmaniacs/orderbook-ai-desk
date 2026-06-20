"""Create order tracking tables

Revision ID: 001_order_tracking
Revises:
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "001_order_tracking"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── order_announcements ───────────────────────────────────────────────────
    op.create_table(
        "order_announcements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Source
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("pdf_object_key", sa.Text),
        # Company
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("symbol_nse", sa.String(20)),
        sa.Column("symbol_bse", sa.String(20)),
        sa.Column("sector", sa.String(100)),
        # Order details
        sa.Column("customer_name", sa.String(255)),
        sa.Column("order_amount_cr", sa.Numeric(20, 4)),
        sa.Column("order_amount_raw", sa.String(200)),
        sa.Column("order_currency", sa.String(10), server_default="INR"),
        sa.Column("order_type", sa.String(20)),
        sa.Column("project_description", sa.Text),
        # Timeline
        sa.Column("announced_date", sa.Date, nullable=False),
        sa.Column("execution_start", sa.Date),
        sa.Column("execution_end", sa.Date),
        sa.Column("duration_months", sa.Integer),
        # Classification
        sa.Column("sector_category", sa.String(100)),
        sa.Column("project_type", sa.String(100)),
        sa.Column("is_repeat_order", sa.Boolean, server_default="false"),
        sa.Column("is_framework_contract", sa.Boolean, server_default="false"),
        # Fiscal period
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("quarter", sa.String(10)),
        # AI
        sa.Column("raw_text", sa.Text),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column("extraction_model", sa.String(100)),
        sa.Column("extraction_notes", sa.Text),
        # Processing
        sa.Column("processing_status", sa.String(20), server_default="PENDING"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        # Constraints
        sa.UniqueConstraint("source", "source_id", name="uq_order_source_id"),
        sa.UniqueConstraint("content_hash", name="uq_order_content_hash"),
    )
    op.create_index("idx_order_isin", "order_announcements", ["isin"])
    op.create_index("idx_order_announced_date", "order_announcements", ["announced_date"])
    op.create_index("idx_order_processing_status", "order_announcements", ["processing_status"])
    op.create_index("idx_order_sector_category", "order_announcements", ["sector_category"])
    op.create_index("idx_order_amount_cr", "order_announcements", ["order_amount_cr"])

    # ── order_book_snapshots ──────────────────────────────────────────────────
    op.create_table(
        "order_book_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("quarter", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter_num", sa.Integer, nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("opening_order_book_cr", sa.Numeric(20, 4)),
        sa.Column("new_orders_cr", sa.Numeric(20, 4)),
        sa.Column("revenue_executed_cr", sa.Numeric(20, 4)),
        sa.Column("closing_order_book_cr", sa.Numeric(20, 4)),
        sa.Column("order_count", sa.Integer, server_default="0"),
        sa.Column("large_order_count", sa.Integer, server_default="0"),
        sa.Column("domestic_orders_cr", sa.Numeric(20, 4), server_default="0"),
        sa.Column("export_orders_cr", sa.Numeric(20, 4), server_default="0"),
        sa.Column("quarterly_revenue_cr", sa.Numeric(20, 4)),
        sa.Column("annual_revenue_ttm_cr", sa.Numeric(20, 4)),
        sa.Column("is_estimated", sa.Boolean, server_default="false"),
        sa.Column("estimation_method", sa.String(100)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "quarter", name="uq_snapshot_isin_quarter"),
    )
    op.create_index("idx_snapshot_isin", "order_book_snapshots", ["isin"])
    op.create_index("idx_snapshot_fiscal_year", "order_book_snapshots", ["fiscal_year", "quarter_num"])

    # ── order_book_metrics ────────────────────────────────────────────────────
    op.create_table(
        "order_book_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False, unique=True),
        sa.Column("company_name", sa.String(255)),
        sa.Column("current_order_book_cr", sa.Numeric(20, 4)),
        sa.Column("last_order_date", sa.Date),
        sa.Column("total_orders_count", sa.Integer, server_default="0"),
        sa.Column("ttm_orders_won_cr", sa.Numeric(20, 4)),
        sa.Column("order_inflow_growth_yoy_pct", sa.Numeric(10, 4)),
        sa.Column("order_book_growth_yoy_pct", sa.Numeric(10, 4)),
        sa.Column("order_book_cagr_3y", sa.Numeric(10, 4)),
        sa.Column("order_book_cagr_5y", sa.Numeric(10, 4)),
        sa.Column("order_book_to_sales", sa.Numeric(10, 4)),
        sa.Column("order_book_to_sales_prev", sa.Numeric(10, 4)),
        sa.Column("bill_to_book_ratio", sa.Numeric(10, 4)),
        sa.Column("order_to_sales_trend", sa.String(20)),
        sa.Column("order_acceleration_score", sa.Numeric(5, 2)),
        sa.Column("order_momentum", sa.String(20)),
        sa.Column("bull_case_ob_cr", sa.Numeric(20, 4)),
        sa.Column("base_case_ob_cr", sa.Numeric(20, 4)),
        sa.Column("bear_case_ob_cr", sa.Numeric(20, 4)),
        sa.Column("scenario_horizon_quarters", sa.Integer, server_default="4"),
        sa.Column("scenario_assumptions", JSONB),
        sa.Column("domestic_pct", sa.Numeric(6, 3)),
        sa.Column("export_pct", sa.Numeric(6, 3)),
        sa.Column("sector_breakdown", JSONB),
        sa.Column("customer_concentration", JSONB),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_metrics_isin", "order_book_metrics", ["isin"])
    op.create_index("idx_metrics_score", "order_book_metrics", ["order_acceleration_score"])

    # ── order_ai_summaries ────────────────────────────────────────────────────
    op.create_table(
        "order_ai_summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("trend", sa.String(20)),
        sa.Column("trend_confidence", sa.Numeric(4, 3)),
        sa.Column("executive_summary", sa.Text),
        sa.Column("pipeline_analysis", sa.Text),
        sa.Column("customer_concentration_note", sa.Text),
        sa.Column("geographic_mix_note", sa.Text),
        sa.Column("risk_factors", JSONB),
        sa.Column("positive_signals", JSONB),
        sa.Column("key_customers", JSONB),
        sa.Column("bull_narrative", sa.Text),
        sa.Column("base_narrative", sa.Text),
        sa.Column("bear_narrative", sa.Text),
        sa.Column("ai_verdict", sa.Text),
        sa.Column("model_version", sa.String(100)),
        sa.Column("prompt_version", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ai_summary_isin", "order_ai_summaries", ["isin"])
    op.create_index("idx_ai_summary_generated_at", "order_ai_summaries", ["generated_at"])


def downgrade() -> None:
    op.drop_table("order_ai_summaries")
    op.drop_table("order_book_metrics")
    op.drop_table("order_book_snapshots")
    op.drop_table("order_announcements")
