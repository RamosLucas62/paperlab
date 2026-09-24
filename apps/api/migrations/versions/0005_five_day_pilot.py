"""Persist the five-day pilot closing snapshot.

Revision ID: 0005_five_day_pilot
Revises: 0004_terminal_dry_run
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_five_day_pilot"
down_revision = "0004_terminal_dry_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("terminal_simulation_accounts", sa.Column("final_equity_usdc", sa.Numeric(24, 8), nullable=True))
    op.add_column("terminal_simulation_accounts", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("terminal_simulation_accounts", "finished_at")
    op.drop_column("terminal_simulation_accounts", "final_equity_usdc")
