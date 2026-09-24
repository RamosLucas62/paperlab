from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from paperlab.models import JevObservation, MarketSample, TerminalControl, TerminalSimulationAccount, TerminalSimulationFill, TerminalSimulationOrder
from paperlab.bot_worker import _prune_terminal_history
from paperlab.simulation import (
    advance_simulation_with_sample,
    ensure_simulation_account,
    expire_open_orders,
    record_simulated_decision,
    simulation_payload,
)


def _quote(db_session, at: datetime, *, bid="0.0245", ask="0.0246") -> MarketSample:
    row = MarketSample(
        chain_id=143,
        observed_at=at,
        symbol="MON/USDC",
        best_bid=Decimal(bid),
        best_ask=Decimal(ask),
        mid_price=(Decimal(bid) + Decimal(ask)) / 2,
        spread_bps=(Decimal(ask) - Decimal(bid)) / ((Decimal(bid) + Decimal(ask)) / 2) * 10000,
        block_number=123,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _result(stance="buy", stance_confidence="0.98", *, risk="no_risk_event"):
    return {
        "stance": {"choice": stance, "confidence": stance_confidence},
        "relevance": {"choice": "relevant", "confidence": "0.98"},
        "risk": {"choice": risk, "confidence": "0.98"},
        "sufficiency": {"choice": "sufficient", "confidence": "0.98"},
    }


def _observation(db_session, sample: MarketSample, result: dict | None, *, status="ready") -> JevObservation:
    row = JevObservation(
        sample_id=sample.id,
        model="typesafe/jev-1.13",
        status=status,
        result_json=result,
        message="typed observation",
        cost_status="reported",
        latency_ms=1,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _control() -> TerminalControl:
    return TerminalControl(
        id=1,
        network_chain_id=143,
        monitor_enabled=True,
        jev_enabled=True,
        simulation_enabled=True,
        status="connected",
    )


def test_buy_signal_creates_fictional_limit_order_and_fills_only_on_a_later_touch(db_session):
    now = datetime.now(timezone.utc)
    signal_quote = _quote(db_session, now - timedelta(seconds=1))
    observation = _observation(db_session, signal_quote, _result())
    decision = record_simulated_decision(db_session, _control(), observation, signal_quote, now=now)

    order = db_session.query(TerminalSimulationOrder).one()
    account = db_session.query(TerminalSimulationAccount).one()
    assert decision.status == "queued"
    assert order.side == "BUY"
    assert order.status == "open"
    assert order.limit_price == Decimal("0.0245")
    assert order.notional_usdc <= Decimal("10.00")
    assert account.cash_usdc == Decimal("1000.00")
    assert not db_session.query(TerminalSimulationFill).all()

    touching_quote = _quote(db_session, now + timedelta(seconds=2), bid="0.0243", ask="0.0245")
    assert advance_simulation_with_sample(db_session, _control(), touching_quote, now=now + timedelta(seconds=3))
    db_session.refresh(order)
    db_session.refresh(account)
    assert order.status == "filled"
    assert account.position_qty == order.quantity
    assert account.average_entry_price == order.limit_price
    assert account.cash_usdc < Decimal("1000.00")
    assert db_session.query(TerminalSimulationFill).one().price == order.limit_price


def test_unqualified_or_failed_jev_abstains_and_never_creates_an_order(db_session):
    now = datetime.now(timezone.utc)
    quote = _quote(db_session, now - timedelta(seconds=1))
    weak = _observation(db_session, quote, _result(stance_confidence="0.79"))
    failed = _observation(db_session, quote, None, status="failed")
    risky = _observation(db_session, quote, _result(risk="risk_event"))

    decisions = [record_simulated_decision(db_session, _control(), item, quote, now=now) for item in (weak, failed, risky)]

    assert all(item.status == "abstain" for item in decisions)
    assert not db_session.query(TerminalSimulationOrder).all()


def test_hold_and_sell_without_position_do_not_create_orders(db_session):
    now = datetime.now(timezone.utc)
    quote = _quote(db_session, now - timedelta(seconds=1))
    hold = _observation(db_session, quote, _result(stance="hold"))
    sell = _observation(db_session, quote, _result(stance="sell"))

    hold_decision = record_simulated_decision(db_session, _control(), hold, quote, now=now)
    sell_decision = record_simulated_decision(db_session, _control(), sell, quote, now=now)

    assert hold_decision.status == "hold"
    assert sell_decision.status == "blocked"
    assert not db_session.query(TerminalSimulationOrder).all()


def test_filled_buy_can_only_be_closed_by_a_simulated_sell_without_shorting(db_session):
    now = datetime.now(timezone.utc)
    buy_quote = _quote(db_session, now - timedelta(seconds=1))
    buy = _observation(db_session, buy_quote, _result())
    record_simulated_decision(db_session, _control(), buy, buy_quote, now=now)
    account = db_session.query(TerminalSimulationAccount).one()
    buy_order = db_session.query(TerminalSimulationOrder).one()
    fill_quote = _quote(db_session, now + timedelta(seconds=1), bid="0.0244", ask="0.0245")
    assert advance_simulation_with_sample(db_session, _control(), fill_quote, now=now + timedelta(seconds=2))

    sell_signal = _observation(db_session, fill_quote, _result(stance="sell"))
    sell_decision = record_simulated_decision(db_session, _control(), sell_signal, fill_quote, now=now + timedelta(seconds=3))
    sell_order = db_session.query(TerminalSimulationOrder).filter(TerminalSimulationOrder.id != buy_order.id).one()
    assert sell_decision.status == "queued"
    assert sell_order.quantity == account.position_qty

    sell_fill_quote = _quote(db_session, now + timedelta(seconds=4), bid=str(sell_order.limit_price), ask="0.0247")
    assert advance_simulation_with_sample(db_session, _control(), sell_fill_quote, now=now + timedelta(seconds=5))
    db_session.refresh(account)
    assert account.position_qty == Decimal("0")
    assert account.average_entry_price == Decimal("0")
    assert db_session.query(TerminalSimulationFill).count() == 2
    assert account.realized_pnl_usdc == (sell_order.limit_price - buy_order.limit_price) * buy_order.quantity


def test_expired_order_is_not_filled_after_its_ttl(db_session):
    now = datetime.now(timezone.utc)
    quote = _quote(db_session, now - timedelta(seconds=1))
    observation = _observation(db_session, quote, _result())
    record_simulated_decision(db_session, _control(), observation, quote, now=now)
    order = db_session.query(TerminalSimulationOrder).one()

    assert expire_open_orders(db_session, 143, now=now + timedelta(seconds=121)) == 1
    db_session.refresh(order)
    later_quote = _quote(db_session, now + timedelta(seconds=122), bid="0.0243", ask="0.0245")
    assert not advance_simulation_with_sample(db_session, _control(), later_quote, now=now + timedelta(seconds=123))
    assert order.status == "expired"
    assert not db_session.query(TerminalSimulationFill).all()


def test_reprocessing_same_observation_is_idempotent(db_session):
    now = datetime.now(timezone.utc)
    quote = _quote(db_session, now - timedelta(seconds=1))
    observation = _observation(db_session, quote, _result())

    first = record_simulated_decision(db_session, _control(), observation, quote, now=now)
    second = record_simulated_decision(db_session, _control(), observation, quote, now=now)

    assert first.id == second.id
    assert db_session.query(TerminalSimulationOrder).count() == 1


def test_position_pnl_is_not_presented_as_current_when_the_last_quote_is_stale(db_session):
    now = datetime.now(timezone.utc)
    stale_quote = _quote(db_session, now - timedelta(seconds=45))
    account = ensure_simulation_account(db_session, 143, "MON/USDC")
    account.position_qty = Decimal("100")
    account.average_entry_price = Decimal("0.025")
    db_session.flush()

    payload = simulation_payload(db_session, _control(), stale_quote)

    assert payload["account"]["mark_stale"] is True
    assert payload["account"]["equity_usdc"] is None
    assert payload["account"]["total_pnl_usdc"] is None


def test_history_pruning_keeps_rows_referenced_by_simulation_ledger(db_session):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=31)

    disposable_quote = _quote(db_session, old)
    disposable_observation = _observation(db_session, disposable_quote, None, status="failed")
    disposable_observation.observed_at = old

    decision_quote = _quote(db_session, old + timedelta(seconds=1))
    decision_observation = _observation(db_session, decision_quote, None, status="failed")
    decision_observation.observed_at = old
    decision = record_simulated_decision(db_session, _control(), decision_observation, decision_quote, now=old)

    created_quote = _quote(db_session, old + timedelta(seconds=2))
    filled_quote = _quote(db_session, old + timedelta(seconds=3))
    fill_market_quote = _quote(db_session, old + timedelta(seconds=4))
    order = TerminalSimulationOrder(
        chain_id=143,
        symbol="MON/USDC",
        decision_id=decision.id,
        side="BUY",
        status="filled",
        quantity=Decimal("100"),
        limit_price=Decimal("0.0245"),
        notional_usdc=Decimal("2.45"),
        created_sample_id=created_quote.id,
        filled_sample_id=filled_quote.id,
        expires_at=old + timedelta(minutes=2),
        created_at=old,
        filled_at=old + timedelta(seconds=5),
    )
    db_session.add(order)
    db_session.flush()
    fill = TerminalSimulationFill(
        order_id=order.id,
        market_sample_id=fill_market_quote.id,
        quantity=Decimal("100"),
        price=Decimal("0.0245"),
        gross_value_usdc=Decimal("2.45"),
        occurred_at=old + timedelta(seconds=5),
    )
    db_session.add(fill)
    db_session.flush()

    _prune_terminal_history(db_session, now=now)

    remaining_sample_ids = {row.id for row in db_session.query(MarketSample).all()}
    remaining_observation_ids = {row.id for row in db_session.query(JevObservation).all()}
    remaining_decision_ids = {row.id for row in db_session.query(type(decision)).all()}
    assert disposable_quote.id not in remaining_sample_ids
    assert disposable_observation.id not in remaining_observation_ids
    assert {decision_quote.id, created_quote.id, filled_quote.id, fill_market_quote.id} <= remaining_sample_ids
    assert decision_observation.id in remaining_observation_ids
    assert decision.id in remaining_decision_ids
