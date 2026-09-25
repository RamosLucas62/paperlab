"""Bounded paper execution for the read-only Kuru terminal.

This module only updates local ledger rows. It has no wallet, signer, RPC write,
or exchange client dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from paperlab.models import (
    JevObservation,
    MarketSample,
    PilotV2Run,
    TerminalControl,
    TerminalSimulationAccount,
    TerminalSimulationDecision,
    TerminalSimulationFill,
    TerminalSimulationOrder,
)


STARTING_CASH_USDC = Decimal("1000.00")
ORDER_NOTIONAL_USDC = Decimal("10.00")
PILOT_DAYS = 5
GOAL_DAYS = 90
GOAL_EQUITY_USDC = Decimal("10000.00")
MIN_CLASSIFICATION_CONFIDENCE = Decimal("0.80")
ORDER_TTL_SECONDS = 120
MAX_SIGNAL_AGE_SECONDS = 120
MAX_QUOTE_AGE_SECONDS = 30
QUANTITY_QUANTUM = Decimal("0.000000000001")
MONEY_QUANTUM = Decimal("0.00000001")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def ensure_simulation_account(db: Session, chain_id: int, symbol: str) -> TerminalSimulationAccount:
    account = db.scalar(
        select(TerminalSimulationAccount).where(
            TerminalSimulationAccount.chain_id == chain_id,
            TerminalSimulationAccount.symbol == symbol,
        )
    )
    if account is None:
        now = _now()
        account = TerminalSimulationAccount(
            chain_id=chain_id,
            symbol=symbol,
            starting_cash_usdc=STARTING_CASH_USDC,
            cash_usdc=STARTING_CASH_USDC,
            position_qty=Decimal("0"),
            average_entry_price=Decimal("0"),
            realized_pnl_usdc=Decimal("0"),
            created_at=now,
            updated_at=now,
        )
        db.add(account)
        db.flush()
    return account


def pilot_end(account: TerminalSimulationAccount) -> datetime:
    return _aware(account.created_at) + timedelta(days=PILOT_DAYS)


def close_pilot_if_due(db: Session, control: TerminalControl, sample: MarketSample, *, now: datetime | None = None) -> bool:
    """Freeze the virtual result on the first valid quote at or after day five."""
    now = _aware(now or _now())
    account = db.scalar(select(TerminalSimulationAccount).where(
        TerminalSimulationAccount.chain_id == sample.chain_id,
        TerminalSimulationAccount.symbol == sample.symbol,
    ))
    if account is None or account.finished_at is not None or now < pilot_end(account):
        return False
    account.final_equity_usdc = (account.cash_usdc + account.position_qty * sample.mid_price).quantize(MONEY_QUANTUM)
    account.finished_at = now
    account.updated_at = now
    cancel_open_orders(db, sample.chain_id, now=now)
    control.simulation_enabled = False
    v2_running = db.scalar(select(PilotV2Run.id).where(
        PilotV2Run.chain_id == sample.chain_id,
        PilotV2Run.symbol == sample.symbol,
        PilotV2Run.status == "running",
    ).limit(1)) is not None
    if not v2_running:
        control.jev_enabled = False
        control.monitor_enabled = False
        control.status = "stopped"
    db.flush()
    return True


def _new_decision(db: Session, observation: JevObservation, chain_id: int, symbol: str,
                  stance: str, confidence: Decimal | None, status: str, reason: str) -> TerminalSimulationDecision:
    decision = TerminalSimulationDecision(
        chain_id=chain_id,
        symbol=symbol,
        observation_id=observation.id,
        stance=stance,
        confidence=confidence,
        status=status,
        reason=reason,
        created_at=_now(),
    )
    db.add(decision)
    db.flush()
    return decision


def record_simulated_decision(
    db: Session,
    control: TerminalControl,
    observation: JevObservation,
    quote: MarketSample | None,
    *,
    now: datetime | None = None,
) -> TerminalSimulationDecision | None:
    """Evaluate typed Jev labels and, if eligible, queue one virtual limit order."""
    if not control.simulation_enabled:
        return None
    now = _aware(now or _now())
    existing = db.scalar(
        select(TerminalSimulationDecision).where(
            TerminalSimulationDecision.observation_id == observation.id
        )
    )
    if existing is not None:
        return existing

    account = ensure_simulation_account(db, control.network_chain_id, quote.symbol if quote else "MON/USDC")
    if account.finished_at is not None or now >= pilot_end(account):
        return None
    symbol = quote.symbol if quote else account.symbol
    chain_id = control.network_chain_id
    result = observation.result_json if observation.status == "ready" and isinstance(observation.result_json, dict) else {}
    stance_data = result.get("stance") if isinstance(result.get("stance"), dict) else {}
    raw_stance = stance_data.get("choice")
    stance = raw_stance.upper() if raw_stance in {"buy", "sell", "hold"} else "ABSTAIN"
    confidence = _decimal(stance_data.get("confidence"))

    def abstain(reason: str) -> TerminalSimulationDecision:
        return _new_decision(db, observation, chain_id, symbol, "ABSTAIN", confidence, "abstain", reason)

    if stance == "ABSTAIN":
        return abstain("Classificação ausente ou inválida; nenhuma ordem simulada foi criada.")
    if confidence is None or confidence < 0 or confidence > 1:
        return abstain("Confiança do Jev ausente ou inválida; decisão em ABSTAIN.")
    if confidence < MIN_CLASSIFICATION_CONFIDENCE:
        return abstain("Confiança da postura abaixo do mínimo de 80%; decisão em ABSTAIN.")

    for key, expected, label in (
        ("relevance", "relevant", "relevância"),
        ("risk", "no_risk_event", "risco"),
        ("sufficiency", "sufficient", "suficiência dos dados"),
    ):
        answer = result.get(key) if isinstance(result.get(key), dict) else {}
        answer_confidence = _decimal(answer.get("confidence"))
        if answer.get("choice") != expected or answer_confidence is None or answer_confidence < MIN_CLASSIFICATION_CONFIDENCE:
            return abstain(f"Classificação de {label} não passou pelo mínimo de 80%; decisão em ABSTAIN.")

    if stance == "HOLD":
        return _new_decision(db, observation, chain_id, symbol, stance, confidence, "hold",
                             "HOLD observacional; nenhuma ordem simulada foi criada.")
    if quote is None or quote.chain_id != chain_id or quote.symbol != symbol:
        return abstain("Cotação atual ausente ou pertence a outra rede/mercado.")
    quote_age = (now - _aware(quote.observed_at)).total_seconds()
    if quote_age < -5 or quote_age > MAX_QUOTE_AGE_SECONDS:
        return abstain("Livro Kuru desatualizado; nenhuma ordem simulada foi criada.")
    source_sample = db.get(MarketSample, observation.sample_id) if observation.sample_id is not None else None
    if source_sample is None or source_sample.chain_id != chain_id or (now - _aware(source_sample.observed_at)).total_seconds() > MAX_SIGNAL_AGE_SECONDS:
        return abstain("Leitura do Jev está antiga ou sem amostra correspondente; nenhuma ordem simulada foi criada.")
    if quote.best_bid <= 0 or quote.best_ask <= 0 or quote.best_bid > quote.best_ask:
        return abstain("Livro ausente, inválido ou cruzado; nenhuma ordem simulada foi criada.")

    pending = db.scalar(
        select(TerminalSimulationOrder).where(
            TerminalSimulationOrder.chain_id == chain_id,
            TerminalSimulationOrder.symbol == symbol,
            TerminalSimulationOrder.status == "open",
        ).order_by(TerminalSimulationOrder.id.desc()).limit(1)
    )
    if pending is not None:
        return _new_decision(db, observation, chain_id, symbol, stance, confidence, "blocked",
                             "Já existe uma ordem simulada pendente neste mercado.")

    side = stance
    if side == "BUY" and account.position_qty > 0:
        return _new_decision(db, observation, chain_id, symbol, stance, confidence, "blocked",
                             "A simulação é somente comprada e já existe uma posição aberta.")
    if side == "SELL" and account.position_qty <= 0:
        return _new_decision(db, observation, chain_id, symbol, stance, confidence, "blocked",
                             "Não há posição comprada para encerrar; venda a descoberto é bloqueada.")

    limit_price = quote.best_bid if side == "BUY" else quote.best_ask
    if side == "BUY":
        notional = min(ORDER_NOTIONAL_USDC, account.cash_usdc)
        quantity = (notional / limit_price).quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN)
    else:
        sell_notional = min(ORDER_NOTIONAL_USDC, account.position_qty * limit_price)
        quantity = min(account.position_qty, (sell_notional / limit_price).quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN))
    if quantity <= 0:
        return _new_decision(db, observation, chain_id, symbol, stance, confidence, "blocked",
                             "Saldo ou quantidade disponível insuficiente para a ordem simulada.")
    notional = (quantity * limit_price).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
    decision = _new_decision(db, observation, chain_id, symbol, stance, confidence, "queued",
                             f"Ordem limite {side} simulada no melhor {('bid' if side == 'BUY' else 'ask')} observado.")
    db.add(TerminalSimulationOrder(
        chain_id=chain_id,
        symbol=symbol,
        decision_id=decision.id,
        side=side,
        status="open",
        quantity=quantity,
        limit_price=limit_price,
        notional_usdc=notional,
        created_sample_id=quote.id,
        expires_at=now + timedelta(seconds=ORDER_TTL_SECONDS),
        created_at=now,
    ))
    db.flush()
    return decision


def _active_order(db: Session, chain_id: int, symbol: str | None = None) -> TerminalSimulationOrder | None:
    query = select(TerminalSimulationOrder).where(
        TerminalSimulationOrder.chain_id == chain_id,
        TerminalSimulationOrder.status == "open",
    )
    if symbol is not None:
        query = query.where(TerminalSimulationOrder.symbol == symbol)
    return db.scalar(query.order_by(TerminalSimulationOrder.id.asc()).limit(1))


def expire_open_orders(db: Session, chain_id: int, *, now: datetime | None = None) -> int:
    now = _aware(now or _now())
    orders = db.scalars(select(TerminalSimulationOrder).where(
        TerminalSimulationOrder.chain_id == chain_id,
        TerminalSimulationOrder.status == "open",
        TerminalSimulationOrder.expires_at <= now,
    )).all()
    for order in orders:
        order.status = "expired"
    if orders:
        db.flush()
    return len(orders)


def cancel_open_orders(db: Session, chain_id: int, *, now: datetime | None = None) -> int:
    orders = db.scalars(select(TerminalSimulationOrder).where(
        TerminalSimulationOrder.chain_id == chain_id,
        TerminalSimulationOrder.status == "open",
    )).all()
    for order in orders:
        order.status = "cancelled"
        order.filled_at = None
    if orders:
        db.flush()
    return len(orders)


def advance_simulation_with_sample(
    db: Session,
    control: TerminalControl,
    sample: MarketSample,
    *,
    now: datetime | None = None,
) -> bool:
    """Expire or conservatively mark one virtual order filled on a later quote."""
    if not control.simulation_enabled:
        return False
    now = _aware(now or _now())
    account = db.scalar(select(TerminalSimulationAccount).where(
        TerminalSimulationAccount.chain_id == sample.chain_id,
        TerminalSimulationAccount.symbol == sample.symbol,
    ))
    if account is None:
        return False
    if account.finished_at is not None or now >= pilot_end(account):
        return False
    order = _active_order(db, sample.chain_id, sample.symbol)
    if order is None or sample.id == order.created_sample_id:
        return False
    if now >= _aware(order.expires_at):
        order.status = "expired"
        db.flush()
        return False
    if sample.chain_id != order.chain_id or sample.symbol != order.symbol:
        return False
    crossed = sample.best_ask <= order.limit_price if order.side == "BUY" else sample.best_bid >= order.limit_price
    if not crossed:
        return False

    quantity = order.quantity
    price = order.limit_price
    gross_value = (quantity * price).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
    if order.side == "BUY":
        if gross_value > account.cash_usdc or account.position_qty > 0:
            order.status = "cancelled"
            db.flush()
            return False
        account.cash_usdc = (account.cash_usdc - gross_value).quantize(MONEY_QUANTUM)
        account.position_qty = quantity
        account.average_entry_price = price
    else:
        if quantity > account.position_qty or account.position_qty <= 0:
            order.status = "cancelled"
            db.flush()
            return False
        account.cash_usdc = (account.cash_usdc + gross_value).quantize(MONEY_QUANTUM)
        account.realized_pnl_usdc = (account.realized_pnl_usdc + (price - account.average_entry_price) * quantity).quantize(MONEY_QUANTUM)
        remaining = (account.position_qty - quantity).quantize(QUANTITY_QUANTUM)
        account.position_qty = Decimal("0") if remaining <= QUANTITY_QUANTUM else remaining
        if account.position_qty == 0:
            account.average_entry_price = Decimal("0")
    account.updated_at = now
    order.status = "filled"
    order.filled_sample_id = sample.id
    order.filled_at = now
    db.add(TerminalSimulationFill(
        order_id=order.id,
        market_sample_id=sample.id,
        quantity=quantity,
        price=price,
        gross_value_usdc=gross_value,
        occurred_at=now,
    ))
    db.flush()
    return True


def simulation_payload(db: Session, control: TerminalControl, sample: MarketSample | None, symbol: str = "MON/USDC") -> dict:
    chain_id = control.network_chain_id
    symbol = sample.symbol if sample is not None else symbol
    account = db.scalar(select(TerminalSimulationAccount).where(
        TerminalSimulationAccount.chain_id == chain_id,
        TerminalSimulationAccount.symbol == symbol,
    ))
    if account is None:
        account_data = None
        pilot_data = None
    else:
        mark_is_current = sample is not None and sample.chain_id == chain_id and sample.symbol == symbol
        if mark_is_current:
            age = (_now() - _aware(sample.observed_at)).total_seconds()
            mark_is_current = -5 <= age <= MAX_QUOTE_AGE_SECONDS
        mark = sample.mid_price if mark_is_current and sample is not None else None
        unrealized = None if mark is None and account.position_qty > 0 else Decimal("0")
        if mark is not None:
            unrealized = ((mark - account.average_entry_price) * account.position_qty).quantize(MONEY_QUANTUM)
        total_pnl = None if unrealized is None else (account.realized_pnl_usdc + unrealized).quantize(MONEY_QUANTUM)
        equity = None if mark is None and account.position_qty > 0 else account.cash_usdc + account.position_qty * (mark or Decimal("0"))
        if account.finished_at is not None:
            equity = account.final_equity_usdc
            total_pnl = None if equity is None else equity - account.starting_cash_usdc
        account_data = {
            "starting_cash_usdc": str(account.starting_cash_usdc),
            "cash_usdc": str(account.cash_usdc),
            "position_qty": str(account.position_qty),
            "average_entry_price": str(account.average_entry_price),
            "mark_price": None if mark is None else str(mark),
            "marked_at": None if sample is None else sample.observed_at.isoformat(),
            "mark_stale": not mark_is_current,
            "position_value_usdc": None if mark is None else str((account.position_qty * mark).quantize(MONEY_QUANTUM)),
            "equity_usdc": None if equity is None else str(equity.quantize(MONEY_QUANTUM)),
            "realized_pnl_usdc": str(account.realized_pnl_usdc),
            "unrealized_pnl_usdc": None if unrealized is None else str(unrealized),
            "total_pnl_usdc": None if total_pnl is None else str(total_pnl),
        }
        cutoff = account.finished_at or pilot_end(account)
        decision_count = db.scalar(select(func.count(TerminalSimulationDecision.id)).where(
            TerminalSimulationDecision.chain_id == chain_id,
            TerminalSimulationDecision.symbol == symbol,
            TerminalSimulationDecision.created_at >= account.created_at,
            TerminalSimulationDecision.created_at <= cutoff,
        )) or 0
        filled_count = db.scalar(select(func.count(TerminalSimulationOrder.id)).where(
            TerminalSimulationOrder.chain_id == chain_id,
            TerminalSimulationOrder.symbol == symbol,
            TerminalSimulationOrder.status == "filled",
            TerminalSimulationOrder.created_at >= account.created_at,
            TerminalSimulationOrder.created_at <= cutoff,
        )) or 0
        ai_cost = db.scalar(select(func.sum(JevObservation.cost_usd)).join(
            MarketSample, JevObservation.sample_id == MarketSample.id,
        ).where(
            MarketSample.chain_id == chain_id,
            MarketSample.symbol == symbol,
            JevObservation.observed_at >= account.created_at,
            JevObservation.observed_at <= cutoff,
        ))
        unknown_cost_count = db.scalar(select(func.count(JevObservation.id)).join(
            MarketSample, JevObservation.sample_id == MarketSample.id,
        ).where(
            MarketSample.chain_id == chain_id,
            MarketSample.symbol == symbol,
            JevObservation.observed_at >= account.created_at,
            JevObservation.observed_at <= cutoff,
            JevObservation.cost_status == "unknown",
        )) or 0
        pilot_data = {
            "started_at": _aware(account.created_at).isoformat(),
            "ends_at": pilot_end(account).isoformat(),
            "finished_at": None if account.finished_at is None else _aware(account.finished_at).isoformat(),
            "status": "finished" if account.finished_at is not None else "awaiting_close" if _now() >= pilot_end(account) else "running" if control.simulation_enabled else "paused",
            "decision_count": decision_count,
            "filled_order_count": filled_count,
            "ai_cost_reported_usd": None if ai_cost is None else str(ai_cost),
            "ai_cost_unknown_count": unknown_cost_count,
            "final_equity_usdc": None if account.final_equity_usdc is None else str(account.final_equity_usdc),
            "days": PILOT_DAYS,
            "goal_days": GOAL_DAYS,
            "goal_equity_usdc": str(GOAL_EQUITY_USDC),
        }

    open_order = _active_order(db, chain_id, symbol)
    recent_orders = db.scalars(select(TerminalSimulationOrder).where(
        TerminalSimulationOrder.chain_id == chain_id,
        TerminalSimulationOrder.symbol == symbol,
    ).order_by(TerminalSimulationOrder.created_at.desc(), TerminalSimulationOrder.id.desc()).limit(20)).all()
    order_ids = [row.id for row in recent_orders]
    fills = db.scalars(select(TerminalSimulationFill).where(TerminalSimulationFill.order_id.in_(order_ids))).all() if order_ids else []
    fills_by_order = {fill.order_id: fill for fill in fills}
    decisions = db.scalars(select(TerminalSimulationDecision).where(
        TerminalSimulationDecision.chain_id == chain_id,
        TerminalSimulationDecision.symbol == symbol,
    ).order_by(TerminalSimulationDecision.created_at.desc(), TerminalSimulationDecision.id.desc()).limit(20)).all()
    decisions_by_id = {row.id: row for row in decisions}

    def serialize_order(order: TerminalSimulationOrder | None):
        if order is None:
            return None
        fill = fills_by_order.get(order.id)
        decision = decisions_by_id.get(order.decision_id) or db.get(TerminalSimulationDecision, order.decision_id)
        return {
            "side": order.side,
            "status": order.status,
            "quantity": str(order.quantity),
            "limit_price": str(order.limit_price),
            "notional_usdc": str(order.notional_usdc),
            "confidence": None if decision is None or decision.confidence is None else str(decision.confidence),
            "at": order.created_at.isoformat(),
            "expires_at": order.expires_at.isoformat(),
            "filled_at": None if order.filled_at is None else order.filled_at.isoformat(),
            "fill_price": None if fill is None else str(fill.price),
            "fill_quantity": None if fill is None else str(fill.quantity),
        }

    decisions_data = []
    for decision in decisions:
        order = db.scalar(select(TerminalSimulationOrder).where(TerminalSimulationOrder.decision_id == decision.id))
        decisions_data.append({
            "stance": decision.stance,
            "confidence": None if decision.confidence is None else str(decision.confidence),
            "status": decision.status,
            "reason": decision.reason,
            "at": decision.created_at.isoformat(),
            "order": serialize_order(order),
        })

    return {
        "enabled": control.simulation_enabled,
        "mode": "dry_run",
        "account": account_data,
        "pilot": pilot_data,
        "open_order": serialize_order(open_order),
        "orders": [serialize_order(order) for order in recent_orders],
        "decisions": decisions_data,
        "assumptions": {
            "order_notional_usdc": str(ORDER_NOTIONAL_USDC),
            "minimum_confidence": str(MIN_CLASSIFICATION_CONFIDENCE),
            "order_ttl_seconds": ORDER_TTL_SECONDS,
            "fill_rule": "A ordem limite é considerada preenchida quando a melhor cotação oposta toca/cruza o preço; fila e impacto de mercado não são modelados.",
            "cost_rule": "Taxas, gas e slippage não estão modelados; P&L é bruto e pode divergir do resultado real.",
            "starting_cash_usdc": str(STARTING_CASH_USDC),
        },
    }
