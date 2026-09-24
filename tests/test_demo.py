from decimal import Decimal
from sqlalchemy import select

from paperlab.demo import create_demo_experiment, run_demo_cycle, set_demo_status
from paperlab.models import Decision, Experiment, Fill, OrderIntent, PortfolioSnapshot, Snapshot


def test_demo_first_cycle_is_shared_and_reproducibly_differs_between_arms(db_session):
    experiment = create_demo_experiment(db_session, "Teste DEMO")
    result = set_demo_status(db_session, experiment, "start")
    assert result["cycle_index"] == 57
    decisions = db_session.scalars(select(Decision).where(Decision.cycle_id == result["cycle_id"]).order_by(Decision.arm)).all()
    assert {row.arm: row.outcome for row in decisions} == {"A": "filled", "B": "vetoed", "C": "vetoed"}
    assert len({row.snapshot_id for row in decisions}) == 1
    assert db_session.scalar(select(Snapshot).where(Snapshot.cycle_id == result["cycle_id"])).content_hash == result["snapshot_hash"]
    assert db_session.scalar(select(OrderIntent).where(OrderIntent.arm == "A", OrderIntent.cycle_id == result["cycle_id"])).mode == "DEMO"
    assert db_session.scalar(select(OrderIntent).where(OrderIntent.arm == "B", OrderIntent.cycle_id == result["cycle_id"])) is None
    assert db_session.scalar(select(Fill).join(OrderIntent).where(OrderIntent.experiment_id == experiment.id)).fee_amount > Decimal("0")


def test_repeating_a_cycle_identity_does_not_duplicate_orders(db_session):
    experiment = create_demo_experiment(db_session, "Idempotência")
    set_demo_status(db_session, experiment, "start")
    experiment.next_bar_index = 57
    db_session.commit()
    duplicate = run_demo_cycle(db_session, experiment)
    assert duplicate["duplicate"] is True
    assert len(db_session.scalars(select(OrderIntent).where(OrderIntent.experiment_id == experiment.id)).all()) == 1


def test_pause_persists_and_keeps_cycles_for_deterministic_exits(db_session):
    experiment = create_demo_experiment(db_session, "Pausa de entradas")
    set_demo_status(db_session, experiment, "start")
    result = set_demo_status(db_session, experiment, "pause")
    db_session.refresh(experiment)
    assert experiment.entries_paused is True
    assert result["status"] == "paused_entries"
    while experiment.next_bar_index <= 88:
        exit_cycle = run_demo_cycle(db_session, experiment)
    exit_decision = db_session.scalar(select(Decision).where(Decision.cycle_id == exit_cycle["cycle_id"], Decision.arm == "A"))
    assert exit_decision.action == "SELL"
    assert exit_decision.reason_code == "saida_baseline_independente"
    assert experiment.entries_paused is True


def test_experiment_configuration_is_frozen_and_cash_uses_decimal(db_session):
    experiment = create_demo_experiment(db_session, "Config congelada")
    frozen = experiment.config_hash
    set_demo_status(db_session, experiment, "start")
    db_session.refresh(experiment)
    assert experiment.config_hash == frozen
    portfolio = db_session.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.experiment_id == experiment.id, PortfolioSnapshot.arm == "A").order_by(PortfolioSnapshot.id.desc()))
    assert isinstance(portfolio.cash_usd, Decimal)
