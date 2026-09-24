"""Network-scoped state and history for the read-only market terminal."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from paperlab.models import JevObservation, MarketEvent, MarketSample, TerminalControl


def _network_name(chain_id: int) -> str:
    return {10143: "Monad Testnet", 143: "Monad Mainnet"}.get(chain_id, f"chain {chain_id}")


def ensure_terminal_control(db: Session, chain_id: int) -> TerminalControl:
    """Create terminal control or pause it when the configured chain changes."""
    control = db.get(TerminalControl, 1)
    now = datetime.now(timezone.utc)
    if control is None:
        control = TerminalControl(
            id=1,
            network_chain_id=chain_id,
            monitor_enabled=False,
            jev_enabled=False,
            status="stopped",
            updated_at=now,
        )
        db.add(control)
        db.commit()
        db.refresh(control)
        return control

    if control.network_chain_id != chain_id:
        previous_chain_id = control.network_chain_id
        control.network_chain_id = chain_id
        control.monitor_enabled = False
        control.jev_enabled = False
        control.status = "stopped"
        control.last_error = (
            f"Rede alterada de {_network_name(previous_chain_id)} para {_network_name(chain_id)}. "
            "Monitor pausado; inicie novamente para conectar à nova rede."
        )
        control.last_block_number = None
        control.last_sample_at = None
        control.last_jev_at = None
        control.updated_at = now
        db.commit()
        db.refresh(control)
    return control


def load_terminal_history(db: Session, chain_id: int):
    """Return market data and Jev observations belonging to one Monad chain."""
    samples = db.scalars(
        select(MarketSample)
        .where(MarketSample.chain_id == chain_id)
        .order_by(MarketSample.observed_at.desc(), MarketSample.id.desc())
        .limit(300)
    ).all()
    events = db.scalars(
        select(MarketEvent)
        .where(MarketEvent.chain_id == chain_id)
        .order_by(MarketEvent.occurred_at.desc(), MarketEvent.id.desc())
        .limit(60)
    ).all()
    observations = db.scalars(
        select(JevObservation)
        .join(MarketSample, JevObservation.sample_id == MarketSample.id)
        .where(MarketSample.chain_id == chain_id)
        .order_by(JevObservation.observed_at.desc(), JevObservation.id.desc())
        .limit(30)
    ).all()
    return samples, events, observations
