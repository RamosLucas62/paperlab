"""Add read-only market terminal storage.

Revision ID: 0002_market_terminal
Revises: 0001_initial
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_market_terminal"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "terminal_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("monitor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("jev_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="stopped"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_block_number", sa.Integer(), nullable=True),
        sa.Column("last_sample_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_jev_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("best_bid", sa.Numeric(30, 12), nullable=False),
        sa.Column("best_ask", sa.Numeric(30, 12), nullable=False),
        sa.Column("mid_price", sa.Numeric(30, 12), nullable=False),
        sa.Column("spread_bps", sa.Numeric(18, 8), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=True),
    )
    op.create_index("ix_market_samples_observed_at", "market_samples", ["observed_at"])
    op.create_table(
        "market_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=200), nullable=False, unique=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(30, 12), nullable=False),
        sa.Column("size", sa.Numeric(30, 12), nullable=True),
        sa.Column("tx_hash", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_market_events_occurred_at", "market_events", ["occurred_at"])
    op.create_table(
        "jev_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("market_samples.id"), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("cost_status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_jev_observations_observed_at", "jev_observations", ["observed_at"])


def downgrade():
    op.drop_index("ix_jev_observations_observed_at", table_name="jev_observations")
    op.drop_table("jev_observations")
    op.drop_index("ix_market_events_occurred_at", table_name="market_events")
    op.drop_table("market_events")
    op.drop_index("ix_market_samples_observed_at", table_name="market_samples")
    op.drop_table("market_samples")
    op.drop_table("terminal_control")
