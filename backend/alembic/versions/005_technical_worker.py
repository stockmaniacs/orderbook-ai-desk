"""005 — Technical Analysis AI Worker tables

Revision ID: 005_technical_worker
Revises: 004_master_tracker
Create Date: 2025-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_technical_worker"
down_revision = "004_master_tracker"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── 1. ta_profiles ────────────────────────────────────────────────────────
    op.create_table(
        "ta_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",         sa.String(12),  nullable=False, unique=True),
        sa.Column("symbol_nse",   sa.String(30)),
        sa.Column("symbol_bse",   sa.String(20)),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("sector",       sa.String(100)),
        sa.Column("industry",     sa.String(100)),
        sa.Column("exchange",     sa.String(10),  server_default="NSE"),
        sa.Column("market_cap_cr",  sa.Float),
        sa.Column("market_cap_cat", sa.String(10)),
        # Scores
        sa.Column("trend_score",      sa.Float),
        sa.Column("rs_score",         sa.Float),
        sa.Column("momentum_score",   sa.Float),
        sa.Column("volume_score",     sa.Float),
        sa.Column("pattern_score",    sa.Float),
        sa.Column("technical_score",  sa.Float),
        sa.Column("conviction_score", sa.Float),
        # Rankings
        sa.Column("rs_rating",          sa.Integer),
        sa.Column("sector_rank",        sa.Integer),
        sa.Column("industry_rank",      sa.Integer),
        sa.Column("market_leader_rank", sa.Integer),
        # Classification
        sa.Column("classification",  sa.String(30),  server_default="WATCHLIST"),
        sa.Column("signal",          sa.String(20),  server_default="HOLD"),
        sa.Column("stage",           sa.Integer),
        sa.Column("minervini_count", sa.Integer,     server_default="0"),
        # Key levels
        sa.Column("cmp",               sa.Float),
        sa.Column("pivot_price",       sa.Float),
        sa.Column("entry_price",       sa.Float),
        sa.Column("ideal_buy_zone_lo", sa.Float),
        sa.Column("ideal_buy_zone_hi", sa.Float),
        sa.Column("breakout_level",    sa.Float),
        sa.Column("stop_loss",         sa.Float),
        sa.Column("atr_stop",          sa.Float),
        sa.Column("trailing_stop",     sa.Float),
        sa.Column("target_price",      sa.Float),
        sa.Column("expected_upside_pct", sa.Float),
        sa.Column("risk_reward_ratio",   sa.Float),
        # Risk
        sa.Column("atr_14",              sa.Float),
        sa.Column("atr_pct",             sa.Float),
        sa.Column("volatility_20d",      sa.Float),
        sa.Column("risk_score",          sa.Float),
        sa.Column("position_size_pct",   sa.Float),
        sa.Column("max_portfolio_alloc", sa.Float),
        # Pattern
        sa.Column("active_pattern",   sa.String(40)),
        sa.Column("pattern_maturity", sa.Float),
        # Timestamps
        sa.Column("scores_updated_at", sa.DateTime(timezone=True)),
        sa.Column("price_date",  sa.Date),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ta_profile_score", "ta_profiles", ["technical_score"])
    op.create_index("idx_ta_profile_signal", "ta_profiles", ["signal"])
    op.create_index("idx_ta_profile_class",  "ta_profiles", ["classification"])
    op.create_index("idx_ta_profile_rs",     "ta_profiles", ["rs_rating"])
    op.create_index("idx_ta_profile_stage",  "ta_profiles", ["stage"])

    # ── 2. ta_daily_snapshots ─────────────────────────────────────────────────
    op.create_table(
        "ta_daily_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",      sa.String(12), nullable=False),
        sa.Column("snap_date", sa.Date,       nullable=False),
        sa.Column("open",   sa.Float), sa.Column("high",  sa.Float),
        sa.Column("low",    sa.Float), sa.Column("close", sa.Float),
        sa.Column("volume", sa.BigInteger),
        sa.Column("delivery_pct", sa.Float),
        sa.Column("sma_10",  sa.Float), sa.Column("sma_20",  sa.Float),
        sa.Column("sma_50",  sa.Float), sa.Column("sma_150", sa.Float),
        sa.Column("sma_200", sa.Float), sa.Column("ema_20",  sa.Float),
        sa.Column("ema_50",  sa.Float), sa.Column("wma_30w", sa.Float),
        sa.Column("above_sma_50",  sa.Boolean),
        sa.Column("above_sma_150", sa.Boolean),
        sa.Column("above_sma_200", sa.Boolean),
        sa.Column("sma_50_vs_150",   sa.Float),
        sa.Column("sma_150_vs_200",  sa.Float),
        sa.Column("sma_200_slope_8w", sa.Float),
        sa.Column("high_52w", sa.Float), sa.Column("low_52w",  sa.Float),
        sa.Column("pct_from_52w_high", sa.Float),
        sa.Column("pct_from_52w_low",  sa.Float),
        sa.Column("new_52w_high", sa.Boolean, server_default="false"),
        sa.Column("new_52w_low",  sa.Boolean, server_default="false"),
        sa.Column("rsi_14",     sa.Float), sa.Column("rsi_weekly", sa.Float),
        sa.Column("adx_14",     sa.Float), sa.Column("di_plus",    sa.Float),
        sa.Column("di_minus",   sa.Float),
        sa.Column("macd",       sa.Float), sa.Column("macd_signal", sa.Float),
        sa.Column("macd_hist",  sa.Float),
        sa.Column("macd_hist_expanding", sa.Boolean),
        sa.Column("roc_10",  sa.Float), sa.Column("roc_20", sa.Float),
        sa.Column("roc_60",  sa.Float),
        sa.Column("vol_sma_20",  sa.BigInteger),
        sa.Column("vol_sma_50",  sa.BigInteger),
        sa.Column("vol_ratio",   sa.Float),
        sa.Column("up_vol_ratio", sa.Float),
        sa.Column("accum_dist",  sa.Float), sa.Column("obv", sa.Float),
        sa.Column("is_pocket_pivot",      sa.Boolean, server_default="false"),
        sa.Column("is_accumulation_day",  sa.Boolean, server_default="false"),
        sa.Column("is_distribution_day",  sa.Boolean, server_default="false"),
        sa.Column("distribution_days_20", sa.Integer, server_default="0"),
        sa.Column("tight_action_5d",      sa.Boolean, server_default="false"),
        sa.Column("atr_14",       sa.Float),
        sa.Column("volatility_20d", sa.Float),
        sa.Column("trend_score",    sa.Float),
        sa.Column("rs_score",       sa.Float),
        sa.Column("momentum_score", sa.Float),
        sa.Column("volume_score",   sa.Float),
        sa.Column("technical_score", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "snap_date", name="uq_ta_snap_isin_date"),
    )
    op.create_index("idx_ta_snap_date",  "ta_daily_snapshots", ["snap_date"])
    op.create_index("idx_ta_snap_score", "ta_daily_snapshots", ["technical_score"])
    op.create_index("idx_ta_snap_isin",  "ta_daily_snapshots", ["isin"])

    # ── 3. ta_relative_strength ───────────────────────────────────────────────
    op.create_table(
        "ta_relative_strength",
        sa.Column("id",      postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",    sa.String(12), nullable=False),
        sa.Column("rs_date", sa.Date,       nullable=False),
        sa.Column("rs_vs_nifty500_1m",  sa.Float),
        sa.Column("rs_vs_nifty500_3m",  sa.Float),
        sa.Column("rs_vs_nifty500_6m",  sa.Float),
        sa.Column("rs_vs_nifty500_12m", sa.Float),
        sa.Column("rs_vs_sector_1m",    sa.Float),
        sa.Column("rs_vs_sector_3m",    sa.Float),
        sa.Column("rs_vs_sector_6m",    sa.Float),
        sa.Column("rs_rating",          sa.Integer),
        sa.Column("rs_trend_slope",     sa.Float),
        sa.Column("rs_trend",           sa.String(20)),
        sa.Column("rs_breakout",        sa.Boolean, server_default="false"),
        sa.Column("rs_new_high",        sa.Boolean, server_default="false"),
        sa.Column("sector_rs_rank",     sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("isin", "rs_date", name="uq_ta_rs_isin_date"),
    )
    op.create_index("idx_ta_rs_rating", "ta_relative_strength", ["rs_rating"])

    # ── 4. ta_patterns ────────────────────────────────────────────────────────
    op.create_table(
        "ta_patterns",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",         sa.String(12), nullable=False),
        sa.Column("pattern_type", sa.String(30), nullable=False),
        sa.Column("status",       sa.String(20), server_default="FORMING"),
        sa.Column("detected_date", sa.Date, nullable=False),
        sa.Column("breakout_date", sa.Date),
        sa.Column("failed_date",   sa.Date),
        sa.Column("depth_pct",     sa.Float),
        sa.Column("duration_days", sa.Integer),
        sa.Column("tight_pct",     sa.Float),
        sa.Column("contractions",  sa.Integer),
        sa.Column("pivot_price",   sa.Float),
        sa.Column("buy_zone_lo",   sa.Float),
        sa.Column("buy_zone_hi",   sa.Float),
        sa.Column("pattern_stop",  sa.Float),
        sa.Column("pattern_target", sa.Float),
        sa.Column("quality_score", sa.Float),
        sa.Column("pattern_data",  postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["isin"], ["ta_profiles.isin"], ondelete="CASCADE"),
    )
    op.create_index("idx_ta_pat_isin",   "ta_patterns", ["isin"])
    op.create_index("idx_ta_pat_status", "ta_patterns", ["status"])
    op.create_index("idx_ta_pat_type",   "ta_patterns", ["pattern_type"])
    op.create_index("idx_ta_pat_date",   "ta_patterns", ["detected_date"])

    # ── 5. ta_breakout_levels ─────────────────────────────────────────────────
    op.create_table(
        "ta_breakout_levels",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",       sa.String(12), nullable=False),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True)),
        sa.Column("calc_date",  sa.Date,       nullable=False),
        sa.Column("is_current", sa.Boolean,    server_default="true"),
        sa.Column("cmp",              sa.Float),
        sa.Column("entry_price",      sa.Float),
        sa.Column("ideal_buy_zone_lo", sa.Float),
        sa.Column("ideal_buy_zone_hi", sa.Float),
        sa.Column("breakout_level",   sa.Float),
        sa.Column("pivot_price",      sa.Float),
        sa.Column("stop_loss",        sa.Float),
        sa.Column("atr_stop",         sa.Float),
        sa.Column("trailing_stop",    sa.Float),
        sa.Column("target_price",     sa.Float),
        sa.Column("expected_upside_pct", sa.Float),
        sa.Column("risk_pct",         sa.Float),
        sa.Column("risk_reward_ratio", sa.Float),
        sa.Column("position_size_pct", sa.Float),
        sa.Column("max_portfolio_alloc", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── 6. ta_alerts ─────────────────────────────────────────────────────────
    op.create_table(
        "ta_alerts",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",        sa.String(12), nullable=False),
        sa.Column("company_name", sa.String(200)),
        sa.Column("alert_date",  sa.Date,       nullable=False),
        sa.Column("alert_type",  sa.String(40), nullable=False),
        sa.Column("severity",    sa.String(10), server_default="MEDIUM"),
        sa.Column("title",       sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("price_at_alert",     sa.Float),
        sa.Column("classification_at",  sa.String(30)),
        sa.Column("signal_at",          sa.String(20)),
        sa.Column("tech_score_at",      sa.Float),
        sa.Column("rs_rating_at",       sa.Integer),
        sa.Column("data_snapshot",      postgresql.JSONB),
        sa.Column("is_read",     sa.Boolean, server_default="false"),
        sa.Column("is_actioned", sa.Boolean, server_default="false"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ta_alert_isin",   "ta_alerts", ["isin"])
    op.create_index("idx_ta_alert_type",   "ta_alerts", ["alert_type"])
    op.create_index("idx_ta_alert_date",   "ta_alerts", ["alert_date"])
    op.create_index("idx_ta_alert_unread", "ta_alerts", ["is_read"])

    # ── 7. ta_signal_history ─────────────────────────────────────────────────
    op.create_table(
        "ta_signal_history",
        sa.Column("id",        postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("isin",      sa.String(12), nullable=False),
        sa.Column("signal_date", sa.Date,     nullable=False),
        sa.Column("signal",       sa.String(20), nullable=False),
        sa.Column("classification", sa.String(30)),
        sa.Column("pattern_type",   sa.String(30)),
        sa.Column("alert_type",     sa.String(40)),
        sa.Column("technical_score", sa.Float),
        sa.Column("rs_rating",       sa.Integer),
        sa.Column("trend_score",     sa.Float),
        sa.Column("momentum_score",  sa.Float),
        sa.Column("volume_score",    sa.Float),
        sa.Column("conviction_score", sa.Float),
        sa.Column("price_at_signal",  sa.Float),
        sa.Column("entry_price",      sa.Float),
        sa.Column("stop_loss",        sa.Float),
        sa.Column("target_price",     sa.Float),
        sa.Column("risk_reward_ratio", sa.Float),
        sa.Column("price_7d",   sa.Float), sa.Column("price_30d",  sa.Float),
        sa.Column("price_60d",  sa.Float), sa.Column("price_90d",  sa.Float),
        sa.Column("return_7d",  sa.Float), sa.Column("return_30d", sa.Float),
        sa.Column("return_60d", sa.Float), sa.Column("return_90d", sa.Float),
        sa.Column("hit_target",   sa.Boolean),
        sa.Column("hit_stop",     sa.Boolean),
        sa.Column("max_gain_pct", sa.Float),
        sa.Column("max_loss_pct", sa.Float),
        sa.Column("outcome",    sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ta_sig_hist_date",    "ta_signal_history", ["signal_date"])
    op.create_index("idx_ta_sig_hist_signal",  "ta_signal_history", ["signal"])
    op.create_index("idx_ta_sig_hist_outcome", "ta_signal_history", ["outcome"])

    # ── 8. ta_market_breadth ─────────────────────────────────────────────────
    op.create_table(
        "ta_market_breadth",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("breadth_date", sa.Date, unique=True, nullable=False),
        sa.Column("total_stocks", sa.Integer),
        sa.Column("pct_above_sma_50",  sa.Float),
        sa.Column("pct_above_sma_150", sa.Float),
        sa.Column("pct_above_sma_200", sa.Float),
        sa.Column("new_highs",   sa.Integer),
        sa.Column("new_lows",    sa.Integer),
        sa.Column("nh_nl_ratio", sa.Float),
        sa.Column("advances",    sa.Integer),
        sa.Column("declines",    sa.Integer),
        sa.Column("unchanged",   sa.Integer),
        sa.Column("ad_ratio",    sa.Float),
        sa.Column("ad_line",     sa.Float),
        sa.Column("elite_leaders_count",    sa.Integer, server_default="0"),
        sa.Column("strong_structure_count", sa.Integer, server_default="0"),
        sa.Column("emerging_leaders_count", sa.Integer, server_default="0"),
        sa.Column("avoid_count",            sa.Integer, server_default="0"),
        sa.Column("top_sectors",   postgresql.JSONB),
        sa.Column("sector_scores", postgresql.JSONB),
        sa.Column("market_regime", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_ta_breadth_date", "ta_market_breadth", ["breadth_date"])


def downgrade() -> None:
    for tbl in [
        "ta_market_breadth", "ta_signal_history", "ta_alerts",
        "ta_breakout_levels", "ta_patterns", "ta_relative_strength",
        "ta_daily_snapshots", "ta_profiles",
    ]:
        op.drop_table(tbl)
