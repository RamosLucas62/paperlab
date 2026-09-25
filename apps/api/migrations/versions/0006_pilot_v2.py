"""Keep the historical pilot and the strategy comparison in separate ledgers.

Revision ID: 0006_pilot_v2
Revises: 0005_five_day_pilot
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_pilot_v2"
down_revision = "0005_five_day_pilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_samples", sa.Column("best_bid_size_raw", sa.Numeric(50, 18)))
    op.add_column("market_samples", sa.Column("best_ask_size_raw", sa.Numeric(50, 18)))
    op.create_table(
        "pilot_v2_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_decision_at", sa.DateTime(timezone=True)),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("baseline_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("baseline_qty", sa.Numeric(30, 12), nullable=False),
        sa.Column("baseline_entry_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("baseline_costs", sa.Numeric(24, 8), nullable=False),
        sa.Column("ai_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("ai_qty", sa.Numeric(30, 12), nullable=False),
        sa.Column("ai_entry_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("ai_costs", sa.Numeric(24, 8), nullable=False),
        sa.Column("model_costs", sa.Numeric(24, 8), nullable=False),
        sa.Column("model_unknown_calls", sa.Integer(), nullable=False),
        sa.Column("final_baseline_equity", sa.Numeric(24, 8)),
        sa.Column("final_ai_equity", sa.Numeric(24, 8)),
    )
    op.create_index("ix_pilot_v2_runs_chain_id", "pilot_v2_runs", ["chain_id"])
    op.create_table(
        "pilot_v2_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("pilot_v2_runs.id"), nullable=False),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal", sa.String(8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("return_30s", sa.Numeric(18, 10)),
        sa.Column("book_imbalance", sa.Numeric(18, 10)),
        sa.Column("spread_bps", sa.Numeric(18, 8), nullable=False),
        sa.Column("baseline_action", sa.String(8), nullable=False),
        sa.Column("ai_action", sa.String(8), nullable=False),
        sa.Column("ai_choice", sa.String(16)),
        sa.Column("ai_confidence", sa.Numeric(5, 4)),
        sa.Column("ai_status", sa.String(24), nullable=False),
        sa.Column("model_latency_ms", sa.Integer()),
        sa.UniqueConstraint("run_id", "sample_id", name="uq_pilot_v2_run_sample"),
    )
    op.create_index("ix_pilot_v2_evaluations_run_id", "pilot_v2_evaluations", ["run_id"])
    op.create_index("ix_pilot_v2_evaluations_occurred_at", "pilot_v2_evaluations", ["occurred_at"])
    op.create_table(
        "pilot_v2_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("pilot_v2_runs.id"), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), sa.ForeignKey("pilot_v2_evaluations.id"), nullable=False),
        sa.Column("arm", sa.String(8), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("limit_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("created_sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_pilot_v2_orders_run_id", "pilot_v2_orders", ["run_id"])
    op.create_table(
        "pilot_v2_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("pilot_v2_runs.id"), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), sa.ForeignKey("pilot_v2_evaluations.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("pilot_v2_orders.id"), nullable=False),
        sa.Column("arm", sa.String(8), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("market_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("execution_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("gross_value_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pilot_v2_trades_run_id", "pilot_v2_trades", ["run_id"])
    op.create_index("ix_pilot_v2_trades_occurred_at", "pilot_v2_trades", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_pilot_v2_trades_occurred_at", table_name="pilot_v2_trades")
    op.drop_index("ix_pilot_v2_trades_run_id", table_name="pilot_v2_trades")
    op.drop_table("pilot_v2_trades")
    op.drop_index("ix_pilot_v2_orders_run_id", table_name="pilot_v2_orders")
    op.drop_table("pilot_v2_orders")
    op.drop_index("ix_pilot_v2_evaluations_occurred_at", table_name="pilot_v2_evaluations")
    op.drop_index("ix_pilot_v2_evaluations_run_id", table_name="pilot_v2_evaluations")
    op.drop_table("pilot_v2_evaluations")
    op.drop_index("ix_pilot_v2_runs_chain_id", table_name="pilot_v2_runs")
    op.drop_table("pilot_v2_runs")
    op.drop_column("market_samples", "best_ask_size_raw")
    op.drop_column("market_samples", "best_bid_size_raw")
