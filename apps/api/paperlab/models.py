from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from paperlab.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="paused", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    entries_paused: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_bar_index: Mapped[int] = mapped_column(Integer, default=57, nullable=False)


class PaperAccountBinding(Base):
    __tablename__ = "paper_account_bindings"
    __table_args__ = (
        UniqueConstraint("experiment_id", "arm", name="uq_paper_binding_arm"),
        UniqueConstraint("experiment_id", "account_id", name="uq_paper_binding_account"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    arm: Mapped[str] = mapped_column(String(1), nullable=False)
    account_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("experiment_id", "cycle_id", name="uq_snapshot_experiment_cycle"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False)
    cycle_index: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Bar(Base):
    __tablename__ = "bars"
    __table_args__ = (UniqueConstraint("snapshot_id", "symbol", "bar_at", name="uq_bar_snapshot_symbol_time"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    bar_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)


class NewsVersion(Base):
    __tablename__ = "news_versions"
    __table_args__ = (UniqueConstraint("snapshot_id", "article_id", "content_hash", name="uq_news_snapshot_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"), nullable=False, index=True)
    article_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("experiment_id", "cycle_id", "arm", name="uq_decision_arm_cycle"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    arm: Mapped[str] = mapped_column(String(1), nullable=False)
    candidate: Mapped[str] = mapped_column(String(12), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    filter_result: Mapped[Optional[str]] = mapped_column(String(12))
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ModelCall(Base):
    __tablename__ = "model_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    arm: Mapped[str] = mapped_column(String(1), nullable=False)
    model_requested: Mapped[str] = mapped_column(String(200), nullable=False)
    model_returned: Mapped[Optional[str]] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[Optional[dict]] = mapped_column(JSON)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8))
    cost_status: Mapped[str] = mapped_column(String(16), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OrderIntent(Base):
    __tablename__ = "order_intents"
    __table_args__ = (UniqueConstraint("experiment_id", "client_order_id", name="uq_order_client_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    arm: Mapped[str] = mapped_column(String(1), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(48), nullable=False)
    external_order_id: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    notional_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Fill(Base):
    __tablename__ = "fills"
    __table_args__ = (UniqueConstraint("order_intent_id", "fill_identity", name="uq_fill_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_intent_id: Mapped[int] = mapped_column(ForeignKey("order_intents.id"), nullable=False, index=True)
    fill_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12))
    fee_currency: Mapped[Optional[str]] = mapped_column(String(12))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("experiment_id", "arm", "cycle_id", name="uq_portfolio_arm_cycle"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    arm: Mapped[str] = mapped_column(String(1), nullable=False)
    cash_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    position_qty: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    position_cost_basis_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    mark_price_usd: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    equity_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    unrealized_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    trading_cost_usd: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    ai_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8))
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    integration: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    cycle_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reservation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    consumed_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class BudgetWindow(Base):
    __tablename__ = "budget_windows"
    window_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    consumed_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TerminalControl(Base):
    __tablename__ = "terminal_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    network_chain_id: Mapped[int] = mapped_column(Integer, default=10143, server_default="10143", nullable=False)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jev_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    simulation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="stopped", nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_block_number: Mapped[Optional[int]] = mapped_column(Integer)
    last_sample_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_jev_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MarketSample(Base):
    __tablename__ = "market_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, default=10143, server_default="10143", nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    best_bid: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    best_ask: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    mid_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    spread_bps: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    block_number: Mapped[Optional[int]] = mapped_column(Integer)


class MarketEvent(Base):
    __tablename__ = "market_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, default=10143, server_default="10143", nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    size: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12))
    tx_hash: Mapped[Optional[str]] = mapped_column(String(100))


class JevObservation(Base):
    __tablename__ = "jev_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    sample_id: Mapped[Optional[int]] = mapped_column(ForeignKey("market_samples.id"))
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8))
    cost_status: Mapped[str] = mapped_column(String(16), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TerminalSimulationAccount(Base):
    __tablename__ = "terminal_simulation_accounts"
    __table_args__ = (UniqueConstraint("chain_id", "symbol", name="uq_terminal_simulation_account_market"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    starting_cash_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cash_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    position_qty: Mapped[Decimal] = mapped_column(Numeric(30, 12), default=Decimal("0"), nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), default=Decimal("0"), nullable=False)
    realized_pnl_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"), nullable=False)
    final_equity_usdc: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TerminalSimulationDecision(Base):
    __tablename__ = "terminal_simulation_decisions"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_terminal_simulation_decision_observation"),
        CheckConstraint("status IN ('queued', 'hold', 'abstain', 'blocked')", name="ck_terminal_simulation_decision_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    observation_id: Mapped[int] = mapped_column(ForeignKey("jev_observations.id"), nullable=False, index=True)
    stance: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class TerminalSimulationOrder(Base):
    __tablename__ = "terminal_simulation_orders"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_terminal_simulation_order_decision"),
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_terminal_simulation_order_side"),
        CheckConstraint("status IN ('open', 'filled', 'cancelled', 'expired')", name="ck_terminal_simulation_order_status"),
        CheckConstraint("quantity > 0 AND limit_price > 0 AND notional_usdc > 0", name="ck_terminal_simulation_order_positive_values"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    decision_id: Mapped[int] = mapped_column(ForeignKey("terminal_simulation_decisions.id"), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    notional_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    created_sample_id: Mapped[int] = mapped_column(ForeignKey("market_samples.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    filled_sample_id: Mapped[Optional[int]] = mapped_column(ForeignKey("market_samples.id"))
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class TerminalSimulationFill(Base):
    __tablename__ = "terminal_simulation_fills"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_terminal_simulation_fill_order"),
        CheckConstraint("quantity > 0 AND price > 0 AND gross_value_usdc > 0", name="ck_terminal_simulation_fill_positive_values"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("terminal_simulation_orders.id"), nullable=False, index=True)
    market_sample_id: Mapped[int] = mapped_column(ForeignKey("market_samples.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    gross_value_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
