"""Create company research tables

Revision ID: 002_company_research
Revises: 001_order_tracking
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "002_company_research"
down_revision = "001_order_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector if not already done
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── research_companies ────────────────────────────────────────────────────
    op.create_table(
        "research_companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), unique=True, nullable=False),
        sa.Column("symbol_nse", sa.String(20)),
        sa.Column("symbol_bse", sa.String(20)),
        sa.Column("bse_code", sa.String(10)),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(100)),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("sub_industry", sa.String(100)),
        sa.Column("market_cap_cr", sa.Numeric(20, 2)),
        sa.Column("market_cap_cat", sa.String(10)),
        sa.Column("listing_date", sa.Date),
        sa.Column("face_value", sa.Numeric(10, 2)),
        sa.Column("website_url", sa.Text),
        sa.Column("ir_url", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("research_priority", sa.SmallInteger, server_default="2"),
        sa.Column("last_research_date", sa.DateTime(timezone=True)),
        sa.Column("next_research_due", sa.DateTime(timezone=True)),
        sa.Column("research_status", sa.String(20), server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_rc_isin", "research_companies", ["isin"])
    op.create_index("idx_rc_symbol_nse", "research_companies", ["symbol_nse"])
    op.create_index("idx_rc_status", "research_companies", ["research_status"])
    op.create_index("idx_rc_priority", "research_companies", ["research_priority"])

    # ── research_documents ────────────────────────────────────────────────────
    op.create_table(
        "research_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("source", sa.String(50)),
        sa.Column("source_url", sa.Text),
        sa.Column("object_store_key", sa.Text),
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("quarter", sa.String(10)),
        sa.Column("published_date", sa.Date),
        sa.Column("page_count", sa.Integer),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("content_hash", sa.String(64), unique=True),
        sa.Column("text_extracted", sa.Boolean, server_default="false"),
        sa.Column("ai_extracted", sa.Boolean, server_default="false"),
        sa.Column("extract_errors", JSONB),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_rd_isin", "research_documents", ["isin"])
    op.create_index("idx_rd_doc_type", "research_documents", ["doc_type"])
    op.create_index("idx_rd_isin_type", "research_documents", ["isin", "doc_type"])
    op.create_index("idx_rd_ai_extracted", "research_documents", ["ai_extracted"])

    # ── research_doc_chunks (with pgvector embedding) ─────────────────────────
    op.create_table(
        "research_doc_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_idx"),
    )
    # Add pgvector column (768 dims for text-embedding-004)
    op.execute("ALTER TABLE research_doc_chunks ADD COLUMN embedding vector(768)")
    op.create_index("idx_chunk_document_id", "research_doc_chunks", ["document_id"])
    op.create_index("idx_chunk_isin", "research_doc_chunks", ["isin"])
    # HNSW index for fast ANN search
    op.execute(
        "CREATE INDEX idx_chunk_embedding ON research_doc_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── research_fields ───────────────────────────────────────────────────────
    op.create_table(
        "research_fields",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("field_category", sa.String(50)),
        sa.Column("value_json", JSONB),
        sa.Column("value_text", sa.Text),
        sa.Column("source_doc_ids", JSONB),
        sa.Column("source_types", JSONB),
        sa.Column("primary_source", sa.String(50)),
        sa.Column("as_of_date", sa.Date),
        sa.Column("fiscal_period", sa.String(10)),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="0.5"),
        sa.Column("is_stale", sa.Boolean, server_default="false"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("update_reason", sa.Text),
        sa.Column("model_version", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "field_name", name="uq_field_isin_name"),
    )
    op.create_index("idx_rf_isin", "research_fields", ["isin"])
    op.create_index("idx_rf_field_name", "research_fields", ["field_name"])
    op.create_index("idx_rf_stale", "research_fields", ["is_stale"])

    # ── research_field_history ────────────────────────────────────────────────
    op.create_table(
        "research_field_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("field_id", UUID(as_uuid=True), nullable=False),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("value_text", sa.Text),
        sa.Column("value_json", JSONB),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("source_types", JSONB),
        sa.Column("update_reason", sa.Text),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_rfh_field_id", "research_field_history", ["field_id"])
    op.create_index("idx_rfh_isin", "research_field_history", ["isin"])

    # ── investment_theses ─────────────────────────────────────────────────────
    op.create_table(
        "investment_theses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), unique=True, nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("one_liner", sa.Text),
        sa.Column("thesis_text", sa.Text),
        sa.Column("strengths", JSONB),
        sa.Column("weaknesses", JSONB),
        sa.Column("opportunities", JSONB),
        sa.Column("threats", JSONB),
        sa.Column("bull_case", sa.Text),
        sa.Column("bull_cagr_pct", sa.Numeric(6, 2)),
        sa.Column("bull_target_cr", sa.Numeric(20, 2)),
        sa.Column("base_case", sa.Text),
        sa.Column("base_cagr_pct", sa.Numeric(6, 2)),
        sa.Column("base_target_cr", sa.Numeric(20, 2)),
        sa.Column("bear_case", sa.Text),
        sa.Column("bear_cagr_pct", sa.Numeric(6, 2)),
        sa.Column("bear_target_cr", sa.Numeric(20, 2)),
        sa.Column("bull_probability", sa.Numeric(5, 2)),
        sa.Column("base_probability", sa.Numeric(5, 2)),
        sa.Column("bear_probability", sa.Numeric(5, 2)),
        sa.Column("current_price", sa.Numeric(12, 2)),
        sa.Column("fair_value_low", sa.Numeric(12, 2)),
        sa.Column("fair_value_mid", sa.Numeric(12, 2)),
        sa.Column("fair_value_high", sa.Numeric(12, 2)),
        sa.Column("target_price_12m", sa.Numeric(12, 2)),
        sa.Column("expected_cagr_3y", sa.Numeric(6, 2)),
        sa.Column("rating", sa.String(20)),
        sa.Column("confidence_score", sa.Numeric(5, 2)),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("sections_updated", JSONB),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("update_trigger", sa.Text),
        sa.Column("model_version", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_it_isin", "investment_theses", ["isin"])
    op.create_index("idx_it_rating", "investment_theses", ["rating"])
    op.create_index("idx_it_confidence", "investment_theses", ["confidence_score"])

    # ── research_reports ──────────────────────────────────────────────────────
    op.create_table(
        "research_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("report_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean, server_default="true"),
        sa.Column("markdown_content", sa.Text, nullable=False),
        sa.Column("object_store_key", sa.Text),
        sa.Column("trigger", sa.Text),
        sa.Column("sections_changed", JSONB),
        sa.Column("sections_added", JSONB),
        sa.Column("diff_summary", sa.Text),
        sa.Column("word_count", sa.Integer),
        sa.Column("source_doc_count", sa.Integer),
        sa.Column("confidence_score", sa.Numeric(5, 2)),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "report_version", name="uq_report_isin_version"),
    )
    op.create_index("idx_rr_isin", "research_reports", ["isin"])
    op.create_index("idx_rr_is_current", "research_reports", ["is_current"])

    # ── research_financials ───────────────────────────────────────────────────
    op.create_table(
        "research_financials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.String(10)),
        sa.Column("period_end_date", sa.Date),
        sa.Column("is_consolidated", sa.Boolean, server_default="true"),
        sa.Column("revenue", sa.Numeric(20, 4)),
        sa.Column("gross_profit", sa.Numeric(20, 4)),
        sa.Column("ebitda", sa.Numeric(20, 4)),
        sa.Column("ebitda_margin", sa.Numeric(8, 4)),
        sa.Column("pat", sa.Numeric(20, 4)),
        sa.Column("pat_margin", sa.Numeric(8, 4)),
        sa.Column("eps", sa.Numeric(12, 4)),
        sa.Column("total_debt", sa.Numeric(20, 4)),
        sa.Column("net_debt", sa.Numeric(20, 4)),
        sa.Column("cash", sa.Numeric(20, 4)),
        sa.Column("total_equity", sa.Numeric(20, 4)),
        sa.Column("cfo", sa.Numeric(20, 4)),
        sa.Column("capex", sa.Numeric(20, 4)),
        sa.Column("free_cash_flow", sa.Numeric(20, 4)),
        sa.Column("roe", sa.Numeric(8, 4)),
        sa.Column("roce", sa.Numeric(8, 4)),
        sa.Column("debt_equity", sa.Numeric(8, 4)),
        sa.Column("interest_coverage", sa.Numeric(8, 4)),
        sa.Column("source_doc_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "isin", "period_type", "fiscal_year", "quarter", "is_consolidated",
            name="uq_financials_period",
        ),
    )
    op.create_index("idx_fin_isin", "research_financials", ["isin"])
    op.create_index("idx_fin_period", "research_financials", ["isin", "period_type", "fiscal_year"])

    # ── research_tasks ────────────────────────────────────────────────────────
    op.create_table(
        "research_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("priority", sa.SmallInteger, server_default="5"),
        sa.Column("trigger", sa.Text),
        sa.Column("document_id", UUID(as_uuid=True)),
        sa.Column("payload", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_rt_isin", "research_tasks", ["isin"])
    op.create_index("idx_rt_status", "research_tasks", ["status"])
    op.create_index("idx_rt_type_status", "research_tasks", ["task_type", "status"])


def downgrade() -> None:
    op.drop_table("research_tasks")
    op.drop_table("research_financials")
    op.drop_table("research_reports")
    op.drop_table("investment_theses")
    op.drop_table("research_field_history")
    op.drop_table("research_fields")
    op.drop_table("research_doc_chunks")
    op.drop_table("research_documents")
    op.drop_table("research_companies")
