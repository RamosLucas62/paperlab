"""Create PaperLab persistence schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("experiments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entries_paused", sa.Boolean(), nullable=False),
        sa.Column("next_bar_index", sa.Integer(), nullable=False),
    )
    op.create_index("ix_experiments_mode", "experiments", ["mode"])
    op.create_table("paper_account_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("arm", sa.String(length=1), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "arm", name="uq_paper_binding_arm"),
        sa.UniqueConstraint("experiment_id", "account_id", name="uq_paper_binding_account"),
    )
    op.create_index("ix_paper_account_bindings_experiment_id", "paper_account_bindings", ["experiment_id"])
    op.create_table("snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("cycle_index", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "cycle_id", name="uq_snapshot_experiment_cycle"),
    )
    op.create_index("ix_snapshots_experiment_id", "snapshots", ["experiment_id"])
    op.create_table("bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("bar_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(30, 12), nullable=False),
        sa.Column("high", sa.Numeric(30, 12), nullable=False),
        sa.Column("low", sa.Numeric(30, 12), nullable=False),
        sa.Column("close", sa.Numeric(30, 12), nullable=False),
        sa.Column("volume", sa.Numeric(30, 12), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("snapshot_id", "symbol", "bar_at", name="uq_bar_snapshot_symbol_time"),
    )
    op.create_index("ix_bars_snapshot_id", "bars", ["snapshot_id"])
    op.create_index("ix_bars_bar_at", "bars", ["bar_at"])
    op.create_table("news_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("article_id", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "article_id", "content_hash", name="uq_news_snapshot_version"),
    )
    op.create_index("ix_news_versions_snapshot_id", "news_versions", ["snapshot_id"])
    op.create_table("decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("arm", sa.String(length=1), nullable=False),
        sa.Column("candidate", sa.String(length=12), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("filter_result", sa.String(length=12), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "cycle_id", "arm", name="uq_decision_arm_cycle"),
    )
    op.create_index("ix_decisions_experiment_id", "decisions", ["experiment_id"])
    op.create_index("ix_decisions_cycle_id", "decisions", ["cycle_id"])
    op.create_table("model_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("arm", sa.String(length=1), nullable=False),
        sa.Column("model_requested", sa.String(length=200), nullable=False),
        sa.Column("model_returned", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("cost_status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_calls_experiment_id", "model_calls", ["experiment_id"])
    op.create_index("ix_model_calls_cycle_id", "model_calls", ["cycle_id"])
    op.create_table("order_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("arm", sa.String(length=1), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("client_order_id", sa.String(length=48), nullable=False),
        sa.Column("external_order_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("notional_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("limit_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "client_order_id", name="uq_order_client_identity"),
    )
    op.create_index("ix_order_intents_experiment_id", "order_intents", ["experiment_id"])
    op.create_index("ix_order_intents_cycle_id", "order_intents", ["cycle_id"])
    op.create_table("fills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_intent_id", sa.Integer(), sa.ForeignKey("order_intents.id"), nullable=False),
        sa.Column("fill_identity", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("price", sa.Numeric(30, 12), nullable=False),
        sa.Column("fee_amount", sa.Numeric(30, 12), nullable=True),
        sa.Column("fee_currency", sa.String(length=12), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_intent_id", "fill_identity", name="uq_fill_identity"),
    )
    op.create_index("ix_fills_order_intent_id", "fills", ["order_intent_id"])
    op.create_table("portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("arm", sa.String(length=1), nullable=False),
        sa.Column("cash_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("position_qty", sa.Numeric(30, 12), nullable=False),
        sa.Column("position_cost_basis_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("mark_price_usd", sa.Numeric(30, 12), nullable=False),
        sa.Column("equity_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("unrealized_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("trading_cost_usd", sa.Numeric(24, 8), nullable=False),
        sa.Column("ai_cost_usd", sa.Numeric(24, 8), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "arm", "cycle_id", name="uq_portfolio_arm_cycle"),
    )
    op.create_index("ix_portfolio_snapshots_experiment_id", "portfolio_snapshots", ["experiment_id"])
    op.create_table("integration_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("integration", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_events_integration", "integration_events", ["integration"])
    op.create_table("budget_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("cycle_id", sa.String(length=100), nullable=False),
        sa.Column("reservation_key", sa.String(length=160), nullable=False, unique=True),
        sa.Column("reserved_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("consumed_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_budget_reservations_experiment_id", "budget_reservations", ["experiment_id"])
    op.create_index("ix_budget_reservations_cycle_id", "budget_reservations", ["cycle_id"])
    op.create_table("budget_windows",
        sa.Column("window_id", sa.String(length=10), primary_key=True),
        sa.Column("reserved_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("consumed_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("budget_windows")
    op.drop_index("ix_budget_reservations_cycle_id", table_name="budget_reservations")
    op.drop_index("ix_budget_reservations_experiment_id", table_name="budget_reservations")
    op.drop_table("budget_reservations")
    op.drop_index("ix_integration_events_integration", table_name="integration_events")
    op.drop_table("integration_events")
    op.drop_index("ix_portfolio_snapshots_experiment_id", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_index("ix_fills_order_intent_id", table_name="fills")
    op.drop_table("fills")
    op.drop_index("ix_order_intents_cycle_id", table_name="order_intents")
    op.drop_index("ix_order_intents_experiment_id", table_name="order_intents")
    op.drop_table("order_intents")
    op.drop_index("ix_model_calls_cycle_id", table_name="model_calls")
    op.drop_index("ix_model_calls_experiment_id", table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_index("ix_decisions_cycle_id", table_name="decisions")
    op.drop_index("ix_decisions_experiment_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_news_versions_snapshot_id", table_name="news_versions")
    op.drop_table("news_versions")
    op.drop_index("ix_bars_bar_at", table_name="bars")
    op.drop_index("ix_bars_snapshot_id", table_name="bars")
    op.drop_table("bars")
    op.drop_index("ix_snapshots_experiment_id", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index("ix_experiments_mode", table_name="experiments")
    op.drop_index("ix_paper_account_bindings_experiment_id", table_name="paper_account_bindings")
    op.drop_table("paper_account_bindings")
    op.drop_table("experiments")
    op.drop_table("admin_users")
