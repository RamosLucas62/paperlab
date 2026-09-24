from datetime import datetime, timezone
from decimal import Decimal

from paperlab.models import JevObservation, MarketEvent, MarketSample
from paperlab.terminal_state import ensure_terminal_control, load_terminal_history


def _sample(chain_id: int, observed_at: datetime) -> MarketSample:
    return MarketSample(
        chain_id=chain_id,
        observed_at=observed_at,
        symbol="MON/USDC",
        best_bid=Decimal("0.0245"),
        best_ask=Decimal("0.0246"),
        mid_price=Decimal("0.02455"),
        spread_bps=Decimal("40.7"),
    )


def test_terminal_history_only_returns_rows_for_selected_chain(db_session):
    testnet_sample = _sample(10143, datetime(2026, 9, 24, 10, tzinfo=timezone.utc))
    mainnet_sample = _sample(143, datetime(2026, 9, 24, 11, tzinfo=timezone.utc))
    db_session.add_all([testnet_sample, mainnet_sample])
    db_session.flush()
    db_session.add_all([
        JevObservation(sample_id=testnet_sample.id, model="test-model", status="ready", message="testnet",
                       cost_status="reported", latency_ms=1),
        JevObservation(sample_id=mainnet_sample.id, model="test-model", status="ready", message="mainnet",
                       cost_status="reported", latency_ms=1),
        MarketEvent(chain_id=10143, event_key="testnet:event", occurred_at=testnet_sample.observed_at,
                    side="buy", price=Decimal("0.0245")),
        MarketEvent(chain_id=143, event_key="143:mainnet:event", occurred_at=mainnet_sample.observed_at,
                    side="sell", price=Decimal("0.0246")),
    ])
    db_session.commit()

    samples, events, observations = load_terminal_history(db_session, 143)

    assert [row.chain_id for row in samples] == [143]
    assert [row.chain_id for row in events] == [143]
    assert [row.message for row in observations] == ["mainnet"]


def test_switching_chain_pauses_monitor_and_clears_network_cursors(db_session):
    control = ensure_terminal_control(db_session, 10143)
    control.monitor_enabled = True
    control.jev_enabled = True
    control.simulation_enabled = True
    control.status = "connected"
    control.last_block_number = 900
    control.last_sample_at = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
    control.last_jev_at = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)
    db_session.commit()

    switched = ensure_terminal_control(db_session, 143)

    assert switched.network_chain_id == 143
    assert switched.monitor_enabled is False
    assert switched.jev_enabled is False
    assert switched.simulation_enabled is False
    assert switched.status == "stopped"
    assert switched.last_block_number is None
    assert switched.last_sample_at is None
    assert switched.last_jev_at is None
    assert "Testnet para Monad Mainnet" in switched.last_error
