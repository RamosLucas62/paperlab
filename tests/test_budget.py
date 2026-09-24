from decimal import Decimal

import pytest
from sqlalchemy import select

from paperlab.budget import BudgetExceeded, reconcile_ai_budget, reserve_ai_budget
from paperlab.demo import create_demo_experiment
from paperlab.models import BudgetReservation, BudgetWindow


def test_budget_reservation_is_idempotent_and_reconciles_cost(db_session):
    experiment = create_demo_experiment(db_session, "Orçamento")
    args = dict(experiment_id=experiment.id, cycle_id="cycle-1", reservation_key="call-1",
                proposed_usd=Decimal("0.05"), per_call_cap_usd=Decimal("0.10"), daily_cap_usd=Decimal("1.00"))
    first = reserve_ai_budget(db_session, **args)
    second = reserve_ai_budget(db_session, **args)
    assert first.id == second.id
    assert first.status == "reserved"
    reconciled = reconcile_ai_budget(db_session, "call-1", Decimal("0.04"))
    assert reconciled.status == "reconciled"
    window = db_session.scalars(select(BudgetWindow)).one()
    assert window.reserved_usd == Decimal("0")
    assert window.consumed_usd == Decimal("0.04")


def test_unknown_cost_stays_reserved_until_reconciled(db_session):
    experiment = create_demo_experiment(db_session, "Custo desconhecido")
    reserve_ai_budget(db_session, experiment_id=experiment.id, cycle_id="cycle-2", reservation_key="call-2",
        proposed_usd=Decimal("0.05"), per_call_cap_usd=Decimal("0.10"), daily_cap_usd=Decimal("1.00"))
    reservation = reconcile_ai_budget(db_session, "call-2", None)
    assert reservation.status == "unknown"
    window = db_session.scalars(select(BudgetWindow)).one()
    assert window.reserved_usd == Decimal("0.05")
    reconcile_ai_budget(db_session, "call-2", Decimal("0.03"))
    assert db_session.get(BudgetReservation, reservation.id).status == "reconciled"


def test_budget_limit_blocks_reservation(db_session):
    experiment = create_demo_experiment(db_session, "Limite de custo")
    with pytest.raises(BudgetExceeded):
        reserve_ai_budget(db_session, experiment_id=experiment.id, cycle_id="cycle-3", reservation_key="call-3",
            proposed_usd=Decimal("0.11"), per_call_cap_usd=Decimal("0.10"), daily_cap_usd=Decimal("1.00"))
