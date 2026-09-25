from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from paperlab.models import MarketSample, PilotV2Order, PilotV2Trade
from paperlab.pilot_v2 import advance_orders, begin_evaluation, complete_ai_evaluation, pause_run, payload, start_run


MARKET = "0x065c9d28e428a0db40191a54d33d5b7c71a9c394"


def sample(db, at, bid, ask, bid_size="2", ask_size="1"):
    bid, ask = Decimal(bid), Decimal(ask)
    mid = (bid + ask) / 2
    row = MarketSample(
        chain_id=143, symbol="MON/USDC", observed_at=at, best_bid=bid, best_ask=ask,
        mid_price=mid, spread_bps=(ask - bid) / mid * 10000, block_number=100,
        best_bid_size_raw=Decimal(bid_size), best_ask_size_raw=Decimal(ask_size),
    )
    db.add(row)
    db.flush()
    return row


def test_book_signal_queues_two_virtual_orders_and_only_later_touch_fills(db_session):
    now = datetime.now(timezone.utc)
    sample(db_session, now - timedelta(seconds=30), "0.024", "0.02401")
    current = sample(db_session, now, "0.025", "0.02501")
    run = start_run(db_session, 143, "MON/USDC", now=now)

    evaluation, state = begin_evaluation(db_session, current, MARKET, now=now)
    assert state is not None
    assert evaluation.signal == "BUY"
    assert evaluation.baseline_action == "BUY"
    complete_ai_evaluation(db_session, evaluation.id, choice="buy", confidence=Decimal("0.98"),
                           status="ready", latency_ms=250, model_cost=Decimal("0.001"), now=now + timedelta(milliseconds=250))
    assert len(db_session.scalars(select(PilotV2Order)).all()) == 2

    advance_orders(db_session, current, now=now + timedelta(seconds=1))
    assert not db_session.scalars(select(PilotV2Trade)).all()
    touched = sample(db_session, now + timedelta(seconds=2), "0.02499", "0.025")
    advance_orders(db_session, touched, now=now + timedelta(seconds=2))

    assert len(db_session.scalars(select(PilotV2Trade)).all()) == 2
    result = payload(db_session, 143, "MON/USDC", touched)
    assert Decimal(result["arms"]["ai"]["equity_usdc"]) < Decimal(result["arms"]["baseline"]["equity_usdc"])
    assert run.ai_qty > 0


def test_pause_preserves_ledger_and_cancels_virtual_order(db_session):
    now = datetime.now(timezone.utc)
    sample(db_session, now - timedelta(seconds=30), "0.024", "0.02401")
    current = sample(db_session, now, "0.025", "0.02501")
    run = start_run(db_session, 143, "MON/USDC", now=now)
    begin_evaluation(db_session, current, MARKET, now=now)

    pause_run(db_session, 143, "MON/USDC")
    assert run.status == "paused"
    assert all(order.status == "cancelled" for order in db_session.scalars(select(PilotV2Order)).all())
    assert start_run(db_session, 143, "MON/USDC", now=now + timedelta(minutes=1)).id == run.id


def test_neutral_book_records_hold_without_a_paid_jev_request(db_session):
    now = datetime.now(timezone.utc)
    sample(db_session, now - timedelta(seconds=30), "0.025", "0.02501")
    current = sample(db_session, now, "0.025", "0.02501", bid_size="1", ask_size="1")
    start_run(db_session, 143, "MON/USDC", now=now)

    evaluation, state = begin_evaluation(db_session, current, MARKET, now=now)

    assert evaluation.signal == "HOLD"
    assert evaluation.ai_status == "no_candidate"
    assert state is None
    assert not db_session.scalars(select(PilotV2Order)).all()


def test_expired_paused_run_can_wait_for_a_final_quote(db_session):
    now = datetime.now(timezone.utc)
    run = start_run(db_session, 143, "MON/USDC", now=now - timedelta(days=5, minutes=1))
    pause_run(db_session, 143, "MON/USDC")

    resumed = start_run(db_session, 143, "MON/USDC", now=now)

    assert resumed.id == run.id
    assert resumed.status == "awaiting_close"
