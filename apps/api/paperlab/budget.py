"""Transactional daily spend reservation for billable external model calls."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from paperlab.models import BudgetReservation, BudgetWindow


class BudgetExceeded(RuntimeError):
    pass


def reserve_ai_budget(db: Session, *, experiment_id: str, cycle_id: str, reservation_key: str,
                      proposed_usd: Decimal, per_call_cap_usd: Decimal, daily_cap_usd: Decimal) -> BudgetReservation:
    if proposed_usd <= 0 or proposed_usd > per_call_cap_usd:
        raise BudgetExceeded("A reserva excede o teto configurado por chamada.")
    existing = db.scalar(select(BudgetReservation).where(BudgetReservation.reservation_key == reservation_key))
    if existing:
        return existing
    day = datetime.now(timezone.utc).date().isoformat()
    values = {"window_id": day, "reserved_usd": Decimal("0"), "consumed_usd": Decimal("0"), "updated_at": datetime.now(timezone.utc)}
    if db.bind.dialect.name == "postgresql":
        db.execute(pg_insert(BudgetWindow).values(**values).on_conflict_do_nothing(index_elements=["window_id"]))
    elif db.bind.dialect.name == "sqlite":
        db.execute(sqlite_insert(BudgetWindow).values(**values).on_conflict_do_nothing(index_elements=["window_id"]))
    elif not db.get(BudgetWindow, day):
        db.add(BudgetWindow(**values))
    window = db.scalar(select(BudgetWindow).where(BudgetWindow.window_id == day).with_for_update())
    if window.reserved_usd + window.consumed_usd + proposed_usd > daily_cap_usd:
        db.rollback()
        raise BudgetExceeded("O orçamento diário disponível é insuficiente para esta chamada.")
    window.reserved_usd += proposed_usd
    window.updated_at = datetime.now(timezone.utc)
    reservation = BudgetReservation(experiment_id=experiment_id, cycle_id=cycle_id,
        reservation_key=reservation_key, reserved_usd=proposed_usd, consumed_usd=None, status="reserved")
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def reconcile_ai_budget(db: Session, reservation_key: str, actual_cost_usd: Decimal | None) -> BudgetReservation:
    reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.reservation_key == reservation_key).with_for_update())
    if not reservation:
        raise ValueError("Reserva de orçamento não encontrada.")
    if reservation.status == "reconciled":
        return reservation
    if actual_cost_usd is None:
        reservation.status = "unknown"
        reservation.consumed_usd = None
        db.commit()
        return reservation
    created_at = reservation.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    day = created_at.astimezone(timezone.utc).date().isoformat()
    window = db.scalar(select(BudgetWindow).where(BudgetWindow.window_id == day).with_for_update())
    cost = max(Decimal("0"), actual_cost_usd)
    window.reserved_usd = max(Decimal("0"), window.reserved_usd - reservation.reserved_usd)
    window.consumed_usd += cost
    reservation.consumed_usd = cost
    reservation.status = "reconciled"
    reservation.reconciled_at = datetime.now(timezone.utc)
    window.updated_at = datetime.now(timezone.utc)
    db.commit()
    return reservation
