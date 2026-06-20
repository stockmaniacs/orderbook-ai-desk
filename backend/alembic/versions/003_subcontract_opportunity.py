"""Create subcontract opportunity tables

Revision ID: 003_subcontract_opportunity
Revises: 002_company_research
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "003_subcontract_opportunity"
down_revision = "002_company_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── sc_nodes ──────────────────────────────────────────────────────────────
    op.create_table(
        "sc_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("isin", sa.String(12), unique=True, nullable=False),
        sa.Column("symbol_nse", sa.String(20)),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("market_cap_cr", sa.Numeric(20, 2)),
        sa.Column("market_cap_cat", sa.String(10)),
        sa.Column("product_categories", JSONB),
        sa.Column("supply_chain_tier", sa.SmallInteger, server_default="2"),
        sa.Column("top_customers", JSONB),
        sa.Column("end_market_mix", JSONB),
        sa.Column("in_degree", sa.Integer, server_default="0"),
        sa.Column("out_degree", sa.Integer, server_default="0"),
        sa.Column("centrality_score", sa.Float, server_default="0"),
        sa.Column("last_graph_update", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_scn_isin", "sc_nodes", ["isin"])
    op.create_index("idx_scn_sector", "sc_nodes", ["sector"])
    op.create_index("idx_scn_tier", "sc_nodes", ["supply_chain_tier"])
    op.create_index("idx_scn_centrality", "sc_nodes", ["centrality_score"])
    # GIN index for product category array search
    op.execute("CREATE INDEX idx_scn_products ON sc_nodes USING gin (product_categories)")

    # ── sc_relationships ──────────────────────────────────────────────────────
    op.create_table(
        "sc_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_isin", sa.String(12), nullable=False),
        sa.Column("source_name", sa.String(255)),
        sa.Column("target_isin", sa.String(12), nullable=False),
        sa.Column("target_name", sa.String(255)),
        sa.Column("rel_type", sa.String(50), nullable=False),
        sa.Column("product_category", sa.String(100)),
        sa.Column("strength", sa.Float, server_default="0.5"),
        sa.Column("revenue_share_pct", sa.Float),
        sa.Column("disclosed_rev_cr", sa.Numeric(20, 4)),
        sa.Column("discovery_method", sa.String(50)),
        sa.Column("evidence_count", sa.Integer, server_default="1"),
        sa.Column("first_seen", sa.Date),
        sa.Column("last_confirmed", sa.Date),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("confidence_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "source_isin", "target_isin", "rel_type", "product_category",
            name="uq_relationship",
        ),
    )
    op.create_index("idx_scr_source", "sc_relationships", ["source_isin"])
    op.create_index("idx_scr_target", "sc_relationships", ["target_isin"])
    op.create_index("idx_scr_rel_type", "sc_relationships", ["rel_type"])
    op.create_index("idx_scr_product", "sc_relationships", ["product_category"])
    op.create_index("idx_scr_strength", "sc_relationships", ["strength"])
    op.create_index("idx_scr_active", "sc_relationships", ["is_active"])
    # Compound: find all suppliers of a given company
    op.create_index("idx_scr_target_type", "sc_relationships", ["target_isin", "rel_type"])
    # Compound: find all customers of a given company
    op.create_index("idx_scr_source_type", "sc_relationships", ["source_isin", "rel_type"])

    # ── sc_relationship_evidence ──────────────────────────────────────────────
    op.create_table(
        "sc_relationship_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("relationship_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_isin", sa.String(12), nullable=False),
        sa.Column("target_isin", sa.String(12), nullable=False),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("doc_url", sa.Text),
        sa.Column("doc_title", sa.Text),
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("quarter", sa.String(10)),
        sa.Column("evidence_text", sa.Text),
        sa.Column("extraction_model", sa.String(100)),
        sa.Column("extraction_conf", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_scre_rel", "sc_relationship_evidence", ["relationship_id"])
    op.create_index("idx_scre_source", "sc_relationship_evidence", ["source_isin"])

    # ── sc_opportunities ──────────────────────────────────────────────────────
    op.create_table(
        "sc_opportunities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_announcement_id", UUID(as_uuid=True)),
        sa.Column("prime_contractor_isin", sa.String(12), nullable=False),
        sa.Column("prime_contractor_name", sa.String(255)),
        sa.Column("order_amount_cr", sa.Numeric(20, 4)),
        sa.Column("order_customer", sa.String(255)),
        sa.Column("order_sector", sa.String(100)),
        sa.Column("order_description", sa.Text),
        sa.Column("announced_date", sa.Date),
        sa.Column("theme", sa.String(100)),
        sa.Column("sub_themes", JSONB),
        sa.Column("estimated_subcontract_cr", sa.Numeric(20, 4)),
        sa.Column("subcontract_ratio", sa.Float),
        sa.Column("beneficiary_count", sa.Integer, server_default="0"),
        sa.Column("analysis_version", sa.Integer, server_default="1"),
        sa.Column("analysis_model", sa.String(100)),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_sco_prime", "sc_opportunities", ["prime_contractor_isin"])
    op.create_index("idx_sco_theme", "sc_opportunities", ["theme"])
    op.create_index("idx_sco_date", "sc_opportunities", ["announced_date"])
    op.create_index("idx_sco_amount", "sc_opportunities", ["order_amount_cr"])
    op.create_index("idx_sco_status", "sc_opportunities", ["status"])

    # ── sc_beneficiaries ──────────────────────────────────────────────────────
    op.create_table(
        "sc_beneficiaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opportunity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("beneficiary_isin", sa.String(12), nullable=False),
        sa.Column("beneficiary_name", sa.String(255)),
        sa.Column("beneficiary_sector", sa.String(100)),
        sa.Column("beneficiary_mcap_cr", sa.Numeric(20, 4)),
        sa.Column("relationship_type", sa.String(50)),
        sa.Column("product_category", sa.String(100)),
        sa.Column("supply_chain_hops", sa.Integer, server_default="1"),
        sa.Column("probability_score", sa.Float),
        sa.Column("revenue_impact_cr", sa.Numeric(20, 4)),
        sa.Column("revenue_impact_pct", sa.Float),
        sa.Column("confidence_score", sa.Float),
        sa.Column("overall_score", sa.Float),
        sa.Column("rank", sa.Integer),
        sa.Column("score_breakdown", JSONB),
        sa.Column("rationale", sa.Text),
        sa.Column("key_risks", JSONB),
        sa.Column("key_catalysts", JSONB),
        sa.Column("investment_action", sa.String(50)),
        sa.Column("relationship_path", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("opportunity_id", "beneficiary_isin", name="uq_opp_beneficiary"),
    )
    op.create_index("idx_scb_opp", "sc_beneficiaries", ["opportunity_id"])
    op.create_index("idx_scb_isin", "sc_beneficiaries", ["beneficiary_isin"])
    op.create_index("idx_scb_score", "sc_beneficiaries", ["overall_score"])
    op.create_index("idx_scb_rank", "sc_beneficiaries", ["opportunity_id", "rank"])
    op.create_index("idx_scb_action", "sc_beneficiaries", ["investment_action"])

    # ── sc_sector_themes ──────────────────────────────────────────────────────
    op.create_table(
        "sc_sector_themes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("theme_name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("typical_subcontract_categories", JSONB),
        sa.Column("typical_subcontract_ratio", sa.Float),
        sa.Column("beneficiary_sectors", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── sc_prediction_outcomes ────────────────────────────────────────────────
    op.create_table(
        "sc_prediction_outcomes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opportunity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("beneficiary_isin", sa.String(12), nullable=False),
        sa.Column("predicted_prob", sa.Float),
        sa.Column("predicted_rev_cr", sa.Numeric(20, 4)),
        sa.Column("was_correct", sa.Boolean),
        sa.Column("actual_rev_impact_cr", sa.Numeric(20, 4)),
        sa.Column("actual_rev_growth_pct", sa.Float),
        sa.Column("outcome_source", sa.String(100)),
        sa.Column("outcome_notes", sa.Text),
        sa.Column("outcome_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_scpo_opp", "sc_prediction_outcomes", ["opportunity_id"])
    op.create_index("idx_scpo_isin", "sc_prediction_outcomes", ["beneficiary_isin"])

    # ── Seed sector themes ────────────────────────────────────────────────────
    op.execute("""
    INSERT INTO sc_sector_themes (theme_name, description, typical_subcontract_categories, typical_subcontract_ratio, beneficiary_sectors)
    VALUES
    ('POWER_T&D', 'Power transmission and distribution projects', '["cables","transformers","switchgear","insulators","conductors","towers","poles"]', 0.55, '["electrical","capital_goods","metals"]'),
    ('RAILWAYS', 'Railway infrastructure and rolling stock', '["rails","sleepers","signalling","overhead_equipment","coaches","bogies","cables"]', 0.50, '["capital_goods","metals","electrical"]'),
    ('ROADS_HIGHWAYS', 'Road and highway construction', '["bitumen","cement","steel","guardrails","lighting","drainage_pipes","machinery"]', 0.45, '["building_materials","metals","chemicals"]'),
    ('DEFENCE', 'Defence equipment manufacturing', '["electronics","optics","composites","forgings","castings","propulsion","software"]', 0.40, '["electronics","metals","aerospace"]'),
    ('HYDROCARBON', 'Oil, gas and petrochemical EPC', '["pipes","valves","pumps","compressors","heat_exchangers","instrumentation","cables"]', 0.50, '["capital_goods","metals","chemicals"]'),
    ('PORTS_WATERWAYS', 'Port and waterway infrastructure', '["dredging_equipment","cranes","mooring","navigation","marine_cables"]', 0.42, '["capital_goods","electrical","logistics"]'),
    ('URBAN_INFRA', 'Urban infrastructure and smart cities', '["pipes","cables","sensors","IT_systems","street_lighting","water_treatment"]', 0.48, '["electrical","IT","capital_goods"]'),
    ('GREEN_ENERGY', 'Solar, wind and green hydrogen', '["solar_modules","wind_turbines","inverters","cables","transformers","electrolyzers"]', 0.52, '["electrical","capital_goods","chemicals"]'),
    ('DATA_CENTRES', 'Data centre construction and equipment', '["UPS","cooling","cables","switchgear","structural_steel","generators"]', 0.45, '["electrical","capital_goods","IT"]'),
    ('WATER_SANITATION', 'Water supply and sanitation projects', '["pipes","pumps","valves","treatment_equipment","instrumentation","chemicals"]', 0.50, '["capital_goods","chemicals","metals"]')
    ON CONFLICT (theme_name) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("sc_prediction_outcomes")
    op.drop_table("sc_sector_themes")
    op.drop_table("sc_beneficiaries")
    op.drop_table("sc_opportunities")
    op.drop_table("sc_relationship_evidence")
    op.drop_table("sc_relationships")
    op.drop_table("sc_nodes")
