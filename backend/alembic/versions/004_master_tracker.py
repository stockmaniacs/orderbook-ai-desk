"""Create master tracker tables

Revision ID: 004_master_tracker
Revises: 003_subcontract_opportunity
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004_master_tracker"
down_revision = "003_subcontract_opportunity"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── mt_stocks ──────────────────────────────────────────────────────────────
    op.create_table(
        "mt_stocks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), unique=True, nullable=False),
        sa.Column("symbol_nse", sa.String(20)),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("market_cap_cr", sa.Numeric(20, 2)),
        sa.Column("market_cap_cat", sa.String(10)),
        sa.Column("cmp", sa.Numeric(12, 2)),
        sa.Column("price_updated_at", sa.DateTime(timezone=True)),
        sa.Column("thesis_summary", sa.Text),
        sa.Column("thesis_quality", sa.String(10), server_default="YELLOW"),
        sa.Column("thesis_updated_at", sa.DateTime(timezone=True)),
        sa.Column("expected_cagr_3y", sa.Float),
        sa.Column("fair_value", sa.Numeric(12, 2)),
        sa.Column("target_price_12m", sa.Numeric(12, 2)),
        sa.Column("upside_pct", sa.Float),
        sa.Column("rating", sa.String(20), server_default="NEUTRAL"),
        sa.Column("risk_reward_score", sa.Float),
        sa.Column("conviction_score", sa.Float),
        sa.Column("technical_trend", sa.String(20)),
        sa.Column("technical_score", sa.Float),
        sa.Column("tracking_status", sa.String(20), server_default="ACTIVE"),
        sa.Column("tracking_priority", sa.SmallInteger, server_default="2"),
        sa.Column("added_date", sa.Date),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        sa.Column("overall_signal", sa.String(10), server_default="YELLOW"),
        sa.Column("consecutive_red", sa.SmallInteger, server_default="0"),
        sa.Column("tags", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_mts_isin",     "mt_stocks", ["isin"])
    op.create_index("idx_mts_sector",   "mt_stocks", ["sector"])
    op.create_index("idx_mts_rating",   "mt_stocks", ["rating"])
    op.create_index("idx_mts_signal",   "mt_stocks", ["overall_signal"])
    op.create_index("idx_mts_cagr",     "mt_stocks", ["expected_cagr_3y"])
    op.create_index("idx_mts_status",   "mt_stocks", ["tracking_status"])
    op.create_index("idx_mts_mcap",     "mt_stocks", ["market_cap_cr"])
    op.create_index("idx_mts_rr_score", "mt_stocks", ["risk_reward_score"])
    op.create_index("idx_mts_tech",     "mt_stocks", ["technical_score"])

    # ── mt_thesis ─────────────────────────────────────────────────────────────
    op.create_table(
        "mt_thesis",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean, server_default="true"),
        sa.Column("thesis_text", sa.Text),
        sa.Column("growth_drivers", JSONB),
        sa.Column("key_risks", JSONB),
        sa.Column("moat", sa.Text),
        sa.Column("management_quality", sa.String(20)),
        sa.Column("expected_revenue_cagr_3y", sa.Float),
        sa.Column("expected_ebitda_margin", sa.Float),
        sa.Column("expected_pat_cagr_3y", sa.Float),
        sa.Column("expected_pe_entry", sa.Float),
        sa.Column("expected_pe_exit", sa.Float),
        sa.Column("expected_ev_ebitda", sa.Float),
        sa.Column("bull_case", JSONB),
        sa.Column("base_case", JSONB),
        sa.Column("bear_case", JSONB),
        sa.Column("authored_by", sa.String(100), server_default="AI_SYSTEM"),
        sa.Column("authored_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_mtt_isin",    "mt_thesis", ["isin"])
    op.create_index("idx_mtt_current", "mt_thesis", ["isin", "is_current"])

    # ── mt_quarterly_targets ──────────────────────────────────────────────────
    op.create_table(
        "mt_quarterly_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.String(3), nullable=False),
        sa.Column("expected_revenue_cr", sa.Numeric(20, 2)),
        sa.Column("expected_ebitda_cr", sa.Numeric(20, 2)),
        sa.Column("expected_ebitda_margin", sa.Float),
        sa.Column("expected_pat_cr", sa.Numeric(20, 2)),
        sa.Column("expected_pat_margin", sa.Float),
        sa.Column("expected_order_book_cr", sa.Numeric(20, 2)),
        sa.Column("expected_order_inflow_cr", sa.Numeric(20, 2)),
        sa.Column("expected_capex_cr", sa.Numeric(20, 2)),
        sa.Column("expected_debt_cr", sa.Numeric(20, 2)),
        sa.Column("mgmt_revenue_guidance", sa.Numeric(20, 2)),
        sa.Column("mgmt_margin_guidance", sa.Float),
        sa.Column("guidance_notes", sa.Text),
        sa.Column("set_by", sa.String(50), server_default="AI_SYSTEM"),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("confidence", sa.Float, server_default="0.7"),
        sa.Column("notes", sa.Text),
        sa.UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_qt_period"),
    )
    op.create_index("idx_mtqt_isin",   "mt_quarterly_targets", ["isin"])
    op.create_index("idx_mtqt_period", "mt_quarterly_targets", ["isin", "fiscal_year", "quarter"])

    # ── mt_quarterly_actuals ──────────────────────────────────────────────────
    op.create_table(
        "mt_quarterly_actuals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.String(3), nullable=False),
        sa.Column("result_date", sa.Date),
        sa.Column("revenue_cr", sa.Numeric(20, 2)),
        sa.Column("ebitda_cr", sa.Numeric(20, 2)),
        sa.Column("ebitda_margin", sa.Float),
        sa.Column("pat_cr", sa.Numeric(20, 2)),
        sa.Column("pat_margin", sa.Float),
        sa.Column("eps", sa.Float),
        sa.Column("revenue_yoy_pct", sa.Float),
        sa.Column("ebitda_yoy_pct", sa.Float),
        sa.Column("pat_yoy_pct", sa.Float),
        sa.Column("revenue_qoq_pct", sa.Float),
        sa.Column("order_book_cr", sa.Numeric(20, 2)),
        sa.Column("order_inflow_cr", sa.Numeric(20, 2)),
        sa.Column("capex_cr", sa.Numeric(20, 2)),
        sa.Column("debt_cr", sa.Numeric(20, 2)),
        sa.Column("cash_cr", sa.Numeric(20, 2)),
        sa.Column("promoter_holding_pct", sa.Float),
        sa.Column("promoter_pledged_pct", sa.Float),
        sa.Column("fii_holding_pct", sa.Float),
        sa.Column("dii_holding_pct", sa.Float),
        sa.Column("mgmt_guidance_revenue", sa.Numeric(20, 2)),
        sa.Column("mgmt_guidance_margin", sa.Float),
        sa.Column("mgmt_commentary", sa.Text),
        sa.Column("guidance_revised", sa.Boolean, server_default="false"),
        sa.Column("guidance_revision_pct", sa.Float),
        sa.Column("source", sa.String(50), server_default="BSE_RESULT"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_qa_period"),
    )
    op.create_index("idx_mtqa_isin",   "mt_quarterly_actuals", ["isin"])
    op.create_index("idx_mtqa_period", "mt_quarterly_actuals", ["isin", "fiscal_year", "quarter"])
    op.create_index("idx_mtqa_date",   "mt_quarterly_actuals", ["result_date"])

    # ── mt_comparisons ────────────────────────────────────────────────────────
    op.create_table(
        "mt_comparisons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.String(3), nullable=False),
        sa.Column("revenue_signal", sa.String(10), server_default="NA"),
        sa.Column("ebitda_signal", sa.String(10), server_default="NA"),
        sa.Column("margin_signal", sa.String(10), server_default="NA"),
        sa.Column("pat_signal", sa.String(10), server_default="NA"),
        sa.Column("order_book_signal", sa.String(10), server_default="NA"),
        sa.Column("capex_signal", sa.String(10), server_default="NA"),
        sa.Column("guidance_signal", sa.String(10), server_default="NA"),
        sa.Column("promoter_signal", sa.String(10), server_default="NA"),
        sa.Column("overall_signal", sa.String(10), server_default="NA"),
        sa.Column("revenue_beat_pct", sa.Float),
        sa.Column("ebitda_beat_pct", sa.Float),
        sa.Column("margin_delta_bps", sa.Float),
        sa.Column("pat_beat_pct", sa.Float),
        sa.Column("order_book_beat_pct", sa.Float),
        sa.Column("beat_count", sa.SmallInteger, server_default="0"),
        sa.Column("miss_count", sa.SmallInteger, server_default="0"),
        sa.Column("in_line_count", sa.SmallInteger, server_default="0"),
        sa.Column("verdict", sa.String(30)),
        sa.Column("ai_summary", sa.Text),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_comp_period"),
    )
    op.create_index("idx_mtc_isin",   "mt_comparisons", ["isin"])
    op.create_index("idx_mtc_signal", "mt_comparisons", ["overall_signal"])
    op.create_index("idx_mtc_verdict","mt_comparisons", ["verdict"])

    # ── mt_alerts ─────────────────────────────────────────────────────────────
    op.create_table(
        "mt_alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), server_default="MEDIUM"),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("data_snapshot", JSONB),
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("quarter", sa.String(3)),
        sa.Column("is_read", sa.Boolean, server_default="false"),
        sa.Column("is_actioned", sa.Boolean, server_default="false"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_mta_isin",     "mt_alerts", ["isin"])
    op.create_index("idx_mta_type",     "mt_alerts", ["alert_type"])
    op.create_index("idx_mta_severity", "mt_alerts", ["severity"])
    op.create_index("idx_mta_unread",   "mt_alerts", ["is_read", "triggered_at"])

    # ── mt_scenarios ──────────────────────────────────────────────────────────
    op.create_table(
        "mt_scenarios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("scenario_type", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("is_current", sa.Boolean, server_default="true"),
        sa.Column("target_price", sa.Numeric(12, 2)),
        sa.Column("target_date", sa.Date),
        sa.Column("expected_cagr", sa.Float),
        sa.Column("probability", sa.Float),
        sa.Column("revenue_cagr", sa.Float),
        sa.Column("ebitda_margin", sa.Float),
        sa.Column("exit_pe", sa.Float),
        sa.Column("exit_ev_ebitda", sa.Float),
        sa.Column("description", sa.Text),
        sa.Column("key_triggers", JSONB),
        sa.Column("key_risks", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "scenario_type", "version", name="uq_scenario"),
    )
    op.create_index("idx_mtsc_isin", "mt_scenarios", ["isin"])
    op.create_index("idx_mtsc_curr", "mt_scenarios", ["isin", "is_current"])

    # ── mt_technical_snapshots ────────────────────────────────────────────────
    op.create_table(
        "mt_technical_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("close_price", sa.Numeric(12, 2)),
        sa.Column("volume", sa.Numeric(20, 0)),
        sa.Column("volume_ma20", sa.Numeric(20, 0)),
        sa.Column("sma_20", sa.Float),
        sa.Column("sma_50", sa.Float),
        sa.Column("sma_200", sa.Float),
        sa.Column("ema_20", sa.Float),
        sa.Column("above_sma_50", sa.Boolean),
        sa.Column("above_sma_200", sa.Boolean),
        sa.Column("golden_cross", sa.Boolean),
        sa.Column("death_cross", sa.Boolean),
        sa.Column("rsi_14", sa.Float),
        sa.Column("macd", sa.Float),
        sa.Column("macd_signal", sa.Float),
        sa.Column("macd_histogram", sa.Float),
        sa.Column("pct_from_52w_high", sa.Float),
        sa.Column("pct_from_52w_low", sa.Float),
        sa.Column("trend", sa.String(20)),
        sa.Column("technical_score", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "snapshot_date", name="uq_tech_date"),
    )
    op.create_index("idx_mtts_isin", "mt_technical_snapshots", ["isin"])
    op.create_index("idx_mtts_date", "mt_technical_snapshots", ["isin", "snapshot_date"])

    # ── mt_promoter_tracking ──────────────────────────────────────────────────
    op.create_table(
        "mt_promoter_tracking",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.String(3), nullable=False),
        sa.Column("promoter_holding_pct", sa.Float),
        sa.Column("promoter_pledged_pct", sa.Float),
        sa.Column("promoter_pledged_abs_pct", sa.Float),
        sa.Column("fii_pct", sa.Float),
        sa.Column("dii_pct", sa.Float),
        sa.Column("public_pct", sa.Float),
        sa.Column("promoter_change_pct", sa.Float),
        sa.Column("pledged_change_pct", sa.Float),
        sa.Column("signal", sa.String(10), server_default="YELLOW"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "fiscal_year", "quarter", name="uq_prom_period"),
    )
    op.create_index("idx_mtpt_isin", "mt_promoter_tracking", ["isin"])


def downgrade() -> None:
    op.drop_table("mt_promoter_tracking")
    op.drop_table("mt_technical_snapshots")
    op.drop_table("mt_scenarios")
    op.drop_table("mt_alerts")
    op.drop_table("mt_comparisons")
    op.drop_table("mt_quarterly_actuals")
    op.drop_table("mt_quarterly_targets")
    op.drop_table("mt_thesis")
    op.drop_table("mt_stocks")
