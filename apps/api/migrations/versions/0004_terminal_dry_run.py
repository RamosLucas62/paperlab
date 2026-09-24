"""Add an isolated, non-executable Kuru paper simulator.

Revision ID: 0004_terminal_dry_run
Revises: 0003_terminal_network_scoping
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_terminal_dry_run"
down_revision = "0003_terminal_network_scoping"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "terminal_control",
        sa.Column("simulation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "terminal_simulation_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("starting_cash_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("position_qty", sa.Numeric(30, 12), nullable=False, server_default="0"),
        sa.Column("average_entry_price", sa.Numeric(30, 12), nullable=False, server_default="0"),
        sa.Column("realized_pnl_usdc", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chain_id", "symbol", name="uq_terminal_simulation_account_market"),
    )
    op.create_index("ix_terminal_simulation_accounts_chain_id", "terminal_simulation_accounts", ["chain_id"])

    op.create_table(
        "terminal_simulation_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("observation_id", sa.Integer(), sa.ForeignKey("jev_observations.id"), nullable=False),
        sa.Column("stance", sa.String(length=12), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("observation_id", name="uq_terminal_simulation_decision_observation"),
        sa.CheckConstraint("status IN ('queued', 'hold', 'abstain', 'blocked')", name="ck_terminal_simulation_decision_status"),
    )
    op.create_index("ix_terminal_simulation_decisions_chain_id", "terminal_simulation_decisions", ["chain_id"])
    op.create_index("ix_terminal_simulation_decisions_observation_id", "terminal_simulation_decisions", ["observation_id"])
    op.create_index("ix_terminal_simulation_decisions_created_at", "terminal_simulation_decisions", ["created_at"])

    op.create_table(
        "terminal_simulation_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("decision_id", sa.Integer(), sa.ForeignKey("terminal_simulation_decisions.id"), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("limit_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("notional_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("created_sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("decision_id", name="uq_terminal_simulation_order_decision"),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_terminal_simulation_order_side"),
        sa.CheckConstraint("status IN ('open', 'filled', 'cancelled', 'expired')", name="ck_terminal_simulation_order_status"),
        sa.CheckConstraint("quantity > 0 AND limit_price > 0 AND notional_usdc > 0", name="ck_terminal_simulation_order_positive_values"),
    )
    op.create_index("ix_terminal_simulation_orders_chain_id", "terminal_simulation_orders", ["chain_id"])
    op.create_index("ix_terminal_simulation_orders_decision_id", "terminal_simulation_orders", ["decision_id"])
    op.create_index("ix_terminal_simulation_orders_status", "terminal_simulation_orders", ["status"])
    op.create_index("ix_terminal_simulation_orders_expires_at", "terminal_simulation_orders", ["expires_at"])
    op.create_index("ix_terminal_simulation_orders_created_at", "terminal_simulation_orders", ["created_at"])

    op.create_table(
        "terminal_simulation_fills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("terminal_simulation_orders.id"), nullable=False),
        sa.Column("market_sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("price", sa.Numeric(30, 12), nullable=False),
        sa.Column("gross_value_usdc", sa.Numeric(24, 8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_terminal_simulation_fill_order"),
        sa.CheckConstraint("quantity > 0 AND price > 0 AND gross_value_usdc > 0", name="ck_terminal_simulation_fill_positive_values"),
    )
    op.create_index("ix_terminal_simulation_fills_order_id", "terminal_simulation_fills", ["order_id"])
    op.create_index("ix_terminal_simulation_fills_occurred_at", "terminal_simulation_fills", ["occurred_at"])


def downgrade():
    op.drop_index("ix_terminal_simulation_fills_occurred_at", table_name="terminal_simulation_fills")
    op.drop_index("ix_terminal_simulation_fills_order_id", table_name="terminal_simulation_fills")
    op.drop_table("terminal_simulation_fills")
    for index in (
        "ix_terminal_simulation_orders_created_at",
        "ix_terminal_simulation_orders_expires_at",
        "ix_terminal_simulation_orders_status",
        "ix_terminal_simulation_orders_decision_id",
        "ix_terminal_simulation_orders_chain_id",
    ):
        op.drop_index(index, table_name="terminal_simulation_orders")
    op.drop_table("terminal_simulation_orders")
    for index in (
        "ix_terminal_simulation_decisions_created_at",
        "ix_terminal_simulation_decisions_observation_id",
        "ix_terminal_simulation_decisions_chain_id",
    ):
        op.drop_index(index, table_name="terminal_simulation_decisions")
    op.drop_table("terminal_simulation_decisions")
    op.drop_index("ix_terminal_simulation_accounts_chain_id", table_name="terminal_simulation_accounts")
    op.drop_table("terminal_simulation_accounts")
    op.drop_column("terminal_control", "simulation_enabled")
