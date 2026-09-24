"""Scope market terminal controls and history by Monad network.

Revision ID: 0003_terminal_network_scoping
Revises: 0002_market_terminal
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_terminal_network_scoping"
down_revision = "0002_market_terminal"
branch_labels = None
depends_on = None


def upgrade():
    # The prior terminal only accepted Monad Testnet (10143), so existing rows
    # can be safely classified as testnet during this migration.
    op.add_column(
        "terminal_control",
        sa.Column("network_chain_id", sa.Integer(), nullable=False, server_default="10143"),
    )
    op.add_column(
        "market_samples",
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="10143"),
    )
    op.add_column(
        "market_events",
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="10143"),
    )
    op.create_index("ix_market_samples_chain_id", "market_samples", ["chain_id"])
    op.create_index("ix_market_events_chain_id", "market_events", ["chain_id"])


def downgrade():
    op.drop_index("ix_market_events_chain_id", table_name="market_events")
    op.drop_index("ix_market_samples_chain_id", table_name="market_samples")
    op.drop_column("market_events", "chain_id")
    op.drop_column("market_samples", "chain_id")
    op.drop_column("terminal_control", "network_chain_id")
