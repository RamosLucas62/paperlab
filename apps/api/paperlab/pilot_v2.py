"""Five-day, book-driven paper comparison. No signer or exchange write path."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from paperlab.models import (
    MarketEvent, MarketSample, PilotV2Evaluation, PilotV2Order, PilotV2Run,
    PilotV2Trade, TerminalControl,
)


INITIAL_CASH = Decimal("1000")
MONEY = Decimal("0.00000001")
QUANTITY = Decimal("0.000000000001")
RULES = {
    "version": "book-v2.0",
    "days": 5,
    "decision_interval_seconds": 5,
    "order_ttl_seconds": 15,
    "max_quote_age_seconds": 5,
    "max_spread_bps": "20",
    "imbalance_threshold": "0.25",
    "ai_action_min_confidence": "0.60",
    "fee_bps_each_fill": "10",
    "execution_uncertainty_bps_each_fill": "5",
    "gas_usdc_each_fill": "0.02",
    "max_loss_fraction": "0.20",
    "cooldown_seconds": 30,
    "position_fraction": "1.0",
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_run(db: Session, chain_id: int, symbol: str) -> PilotV2Run | None:
    return db.scalar(select(PilotV2Run).where(
        PilotV2Run.chain_id == chain_id, PilotV2Run.symbol == symbol,
    ).order_by(PilotV2Run.id.desc()).limit(1))


def active_run(db: Session, chain_id: int, symbol: str) -> PilotV2Run | None:
    run = latest_run(db, chain_id, symbol)
    return run if run is not None and run.status == "running" else None


def start_run(db: Session, chain_id: int, symbol: str, *, now: datetime | None = None) -> PilotV2Run:
    now = _aware(now or _now())
    run = latest_run(db, chain_id, symbol)
    if run is not None:
        if run.status == "finished":
            raise ValueError("O teste de cinco dias já terminou; o histórico foi preservado.")
        if now >= _aware(run.ends_at):
            run.status = "awaiting_close"
            return run
        run.status = "running"
        return run
    run = PilotV2Run(
        chain_id=chain_id, symbol=symbol, status="running", started_at=now,
        ends_at=now + timedelta(days=RULES["days"]), config_json=dict(RULES),
        baseline_cash=INITIAL_CASH, baseline_qty=Decimal("0"), baseline_entry_price=Decimal("0"),
        baseline_costs=Decimal("0"), ai_cash=INITIAL_CASH, ai_qty=Decimal("0"),
        ai_entry_price=Decimal("0"), ai_costs=Decimal("0"), model_costs=Decimal("0"),
        model_unknown_calls=0,
    )
    db.add(run)
    db.flush()
    return run


def pause_run(db: Session, chain_id: int, symbol: str) -> PilotV2Run | None:
    run = latest_run(db, chain_id, symbol)
    if run is not None and run.status == "running":
        run.status = "paused"
        for order in db.scalars(select(PilotV2Order).where(
            PilotV2Order.run_id == run.id, PilotV2Order.status == "open",
        )).all():
            order.status = "cancelled"
    return run


def _cost(gross: Decimal, config: dict) -> Decimal:
    bps = Decimal(config["fee_bps_each_fill"]) + Decimal(config["execution_uncertainty_bps_each_fill"])
    return (gross * bps / Decimal("10000") + Decimal(config["gas_usdc_each_fill"])).quantize(MONEY)


def _marked_equity(run: PilotV2Run, arm: str, sample: MarketSample | None) -> Decimal | None:
    cash = getattr(run, f"{arm}_cash")
    qty = getattr(run, f"{arm}_qty")
    model_cost = run.model_costs if arm == "ai" else Decimal("0")
    if qty == 0:
        return (cash - model_cost).quantize(MONEY)
    if sample is None or sample.best_bid <= 0:
        return None
    gross = (qty * sample.best_bid).quantize(MONEY)
    return (cash + gross - _cost(gross, run.config_json) - model_cost).quantize(MONEY)


def close_if_due(db: Session, control: TerminalControl, sample: MarketSample, *, now: datetime | None = None) -> bool:
    run = latest_run(db, sample.chain_id, sample.symbol)
    now = _aware(now or _now())
    if run is None or run.status == "finished" or now < _aware(run.ends_at):
        return False
    for order in db.scalars(select(PilotV2Order).where(
        PilotV2Order.run_id == run.id, PilotV2Order.status == "open",
    )).all():
        order.status = "expired"
    run.final_baseline_equity = _marked_equity(run, "baseline", sample)
    run.final_ai_equity = _marked_equity(run, "ai", sample)
    run.status = "finished"
    run.finished_at = now
    if not control.simulation_enabled:
        control.monitor_enabled = False
        control.jev_enabled = False
        control.status = "stopped"
    db.flush()
    return True


def advance_orders(db: Session, sample: MarketSample, *, now: datetime | None = None) -> None:
    run = active_run(db, sample.chain_id, sample.symbol)
    if run is None:
        return
    now = _aware(now or _now())
    if now >= _aware(run.ends_at):
        return
    orders = db.scalars(select(PilotV2Order).where(
        PilotV2Order.run_id == run.id, PilotV2Order.status == "open",
    )).all()
    for order in orders:
        if now >= _aware(order.expires_at):
            order.status = "expired"
            continue
        if sample.id == order.created_sample_id:
            continue
        crossed = sample.best_ask <= order.limit_price if order.side == "BUY" else sample.best_bid >= order.limit_price
        if not crossed:
            continue
        arm = order.arm
        cash = getattr(run, f"{arm}_cash")
        qty = getattr(run, f"{arm}_qty")
        gross = (order.quantity * order.limit_price).quantize(MONEY)
        cost = _cost(gross, run.config_json)
        if order.side == "BUY":
            if qty > 0 or gross + cost > cash:
                order.status = "cancelled"
                continue
            setattr(run, f"{arm}_cash", (cash - gross - cost).quantize(MONEY))
            setattr(run, f"{arm}_qty", order.quantity)
            setattr(run, f"{arm}_entry_price", order.limit_price)
        else:
            if qty < order.quantity or qty <= 0:
                order.status = "cancelled"
                continue
            setattr(run, f"{arm}_cash", (cash + gross - cost).quantize(MONEY))
            remaining = (qty - order.quantity).quantize(QUANTITY)
            setattr(run, f"{arm}_qty", remaining)
            if remaining == 0:
                setattr(run, f"{arm}_entry_price", Decimal("0"))
        setattr(run, f"{arm}_costs", (getattr(run, f"{arm}_costs") + cost).quantize(MONEY))
        order.status = "filled"
        order.filled_at = now
        db.add(PilotV2Trade(
            run_id=run.id, evaluation_id=order.evaluation_id, order_id=order.id,
            arm=arm, side=order.side, quantity=order.quantity, market_price=sample.mid_price,
            execution_price=order.limit_price, gross_value_usdc=gross, cost_usdc=cost,
            occurred_at=now,
        ))
    db.flush()


def _book_imbalance(sample: MarketSample) -> Decimal | None:
    bid = sample.best_bid_size_raw
    ask = sample.best_ask_size_raw
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    return (bid - ask) / (bid + ask)


def _return_30s(db: Session, sample: MarketSample) -> Decimal | None:
    at = _aware(sample.observed_at)
    reference = db.scalar(select(MarketSample).where(
        MarketSample.chain_id == sample.chain_id, MarketSample.symbol == sample.symbol,
        MarketSample.observed_at <= at - timedelta(seconds=30),
        MarketSample.observed_at >= at - timedelta(seconds=45),
    ).order_by(MarketSample.observed_at.desc(), MarketSample.id.desc()).limit(1))
    if reference is None or reference.mid_price <= 0:
        return None
    return sample.mid_price / reference.mid_price - 1


def _recent_trade_counts(db: Session, sample: MarketSample, market_address: str) -> tuple[int, int]:
    at = _aware(sample.observed_at)
    events = db.scalars(select(MarketEvent).where(
        MarketEvent.chain_id == sample.chain_id,
        MarketEvent.event_key.like(f"%{market_address.lower()}:%"),
        MarketEvent.occurred_at >= at - timedelta(seconds=30),
        MarketEvent.occurred_at <= at,
    )).all()
    return sum(row.side == "BUY" for row in events), sum(row.side == "SELL" for row in events)


def _baseline_signal(sample: MarketSample, imbalance: Decimal | None, move: Decimal | None, config: dict) -> tuple[str, str]:
    if imbalance is None or move is None:
        return "HOLD", "Aguardando livro com tamanho dos dois lados e 30 segundos de preços."
    if sample.spread_bps > Decimal(config["max_spread_bps"]):
        return "HOLD", "Spread acima do limite da estratégia."
    threshold = Decimal(config["imbalance_threshold"])
    if imbalance >= threshold and move > 0:
        return "BUY", "Pressão compradora no topo do livro e preço subindo em 30 segundos."
    if imbalance <= -threshold and move < 0:
        return "SELL", "Pressão vendedora no topo do livro e preço caindo em 30 segundos."
    return "HOLD", "Livro e movimento recente sem direção conjunta."


def _pending_order(db: Session, run: PilotV2Run, arm: str) -> bool:
    return db.scalar(select(PilotV2Order.id).where(
        PilotV2Order.run_id == run.id, PilotV2Order.arm == arm, PilotV2Order.status == "open",
    ).limit(1)) is not None


def _eligible_side(db: Session, run: PilotV2Run, arm: str, side: str, sample: MarketSample, now: datetime) -> bool:
    if side not in {"BUY", "SELL"} or _pending_order(db, run, arm):
        return False
    last = db.scalar(select(PilotV2Trade.occurred_at).where(
        PilotV2Trade.run_id == run.id, PilotV2Trade.arm == arm,
    ).order_by(PilotV2Trade.occurred_at.desc()).limit(1))
    if last is not None and (now - _aware(last)).total_seconds() < run.config_json["cooldown_seconds"]:
        return False
    qty = getattr(run, f"{arm}_qty")
    if side == "BUY":
        equity = _marked_equity(run, arm, sample)
        return qty == 0 and getattr(run, f"{arm}_cash") > 0 and equity is not None and equity > INITIAL_CASH * (1 - Decimal(run.config_json["max_loss_fraction"]))
    return qty > 0


def _queue_order(db: Session, run: PilotV2Run, evaluation: PilotV2Evaluation, arm: str, side: str, sample: MarketSample, now: datetime) -> bool:
    if not _eligible_side(db, run, arm, side, sample, now):
        return False
    limit = sample.best_bid if side == "BUY" else sample.best_ask
    if limit <= 0:
        return False
    if side == "BUY":
        cash = getattr(run, f"{arm}_cash")
        bps = Decimal(run.config_json["fee_bps_each_fill"]) + Decimal(run.config_json["execution_uncertainty_bps_each_fill"])
        budget = cash * Decimal(run.config_json["position_fraction"]) - Decimal(run.config_json["gas_usdc_each_fill"])
        qty = (budget / (limit * (1 + bps / Decimal("10000")))).quantize(QUANTITY, rounding=ROUND_DOWN)
    else:
        qty = getattr(run, f"{arm}_qty")
    if qty <= 0:
        return False
    db.add(PilotV2Order(
        run_id=run.id, evaluation_id=evaluation.id, arm=arm, side=side, status="open",
        quantity=qty, limit_price=limit, created_sample_id=sample.id, created_at=now,
        expires_at=now + timedelta(seconds=run.config_json["order_ttl_seconds"]),
    ))
    db.flush()
    return True


def begin_evaluation(db: Session, sample: MarketSample, market_address: str, *, now: datetime | None = None) -> tuple[PilotV2Evaluation | None, dict | None]:
    run = active_run(db, sample.chain_id, sample.symbol)
    now = _aware(now or _now())
    if run is None or now >= _aware(run.ends_at):
        return None, None
    existing = db.scalar(select(PilotV2Evaluation).where(
        PilotV2Evaluation.run_id == run.id, PilotV2Evaluation.sample_id == sample.id,
    ))
    if existing is not None:
        return existing, None
    if (now - _aware(sample.observed_at)).total_seconds() > run.config_json["max_quote_age_seconds"]:
        return None, None
    imbalance = _book_imbalance(sample)
    move = _return_30s(db, sample)
    buy_trades, sell_trades = _recent_trade_counts(db, sample, market_address)
    signal, reason = _baseline_signal(sample, imbalance, move, run.config_json)
    evaluation = PilotV2Evaluation(
        run_id=run.id, sample_id=sample.id, occurred_at=now, signal=signal, reason=reason,
        return_30s=move, book_imbalance=imbalance, spread_bps=sample.spread_bps,
        baseline_action="HOLD", ai_action="HOLD", ai_status="not_called",
    )
    db.add(evaluation)
    db.flush()
    baseline_side = signal
    if run.baseline_qty > 0 and sample.best_bid <= run.baseline_entry_price * Decimal("0.985"):
        baseline_side = "SELL"
        evaluation.reason = "Saída de proteção da carteira sem IA: queda de 1,5% desde a entrada."
    if _queue_order(db, run, evaluation, "baseline", baseline_side, sample, now):
        evaluation.baseline_action = baseline_side
    run.last_decision_at = now
    if imbalance is None or move is None or sample.spread_bps > Decimal(run.config_json["max_spread_bps"]):
        evaluation.ai_status = "data_blocked"
        return evaluation, None
    if signal == "HOLD" and run.ai_qty == 0:
        evaluation.ai_status = "no_candidate"
        return evaluation, None
    ai_state = {
        "mode": "virtual_only_no_wallet",
        "symbol": sample.symbol,
        "observed_at": _aware(sample.observed_at).isoformat(),
        "block_number_last_rpc_check": sample.block_number,
        "best_bid": str(sample.best_bid), "best_ask": str(sample.best_ask),
        "bid_size_raw": str(sample.best_bid_size_raw), "ask_size_raw": str(sample.best_ask_size_raw),
        "book_imbalance": str(imbalance.quantize(Decimal("0.0001"))),
        "return_30_seconds": str(move.quantize(Decimal("0.000001"))),
        "spread_bps": str(sample.spread_bps),
        "aggressor_buys_30_seconds": buy_trades, "aggressor_sells_30_seconds": sell_trades,
        "virtual_cash_usdc": str(run.ai_cash), "virtual_position_qty": str(run.ai_qty),
        "entry_price": str(run.ai_entry_price),
        "estimated_cost_bps_per_fill": str(Decimal(run.config_json["fee_bps_each_fill"]) + Decimal(run.config_json["execution_uncertainty_bps_each_fill"])),
        "estimated_gas_usdc_per_fill": run.config_json["gas_usdc_each_fill"],
        "comparison_rule_signal": signal,
    }
    evaluation.ai_status = "pending"
    return evaluation, ai_state


def ai_questions(symbol: str) -> dict:
    return {"action": {
        "type": "choice",
        "instructions": f"Choose BUY, SELL or HOLD for a virtual-only {symbol} portfolio from the current Kuru book, 30-second price change and recent aggressor trades. Consider spread and estimated round-trip costs. BUY requires credible buy pressure with no existing position. SELL requires a position and credible sell pressure or downside protection. HOLD when the evidence is mixed, weak or too costly. No real transaction is permitted.",
        "criteria": {
            "buy": "Bid-side depth and recent price/trade flow jointly support a virtual buy with enough room to cover estimated costs.",
            "sell": "An existing virtual position faces sell-side pressure or downside risk that supports a virtual exit.",
            "hold": "No clear net-of-cost edge, incomplete data, or the portfolio has no eligible action.",
        },
    }}


def complete_ai_evaluation(
    db: Session, evaluation_id: int, *, choice: str | None, confidence: Decimal | None,
    status: str, latency_ms: int | None = None, model_cost: Decimal | None = None,
    now: datetime | None = None,
) -> PilotV2Evaluation:
    evaluation = db.get(PilotV2Evaluation, evaluation_id)
    if evaluation is None:
        raise ValueError("Avaliação virtual não encontrada.")
    if evaluation.ai_status != "pending":
        return evaluation
    run = db.get(PilotV2Run, evaluation.run_id)
    sample = db.get(MarketSample, evaluation.sample_id)
    now = _aware(now or _now())
    evaluation.ai_choice = choice.upper() if choice in {"buy", "sell", "hold"} else None
    evaluation.ai_confidence = confidence
    evaluation.ai_status = status
    evaluation.model_latency_ms = latency_ms
    if model_cost is None and status in {"ready", "failed", "cancelled"}:
        run.model_unknown_calls += 1
    elif model_cost is not None and model_cost >= 0:
        run.model_costs = (run.model_costs + model_cost).quantize(MONEY)
    if status != "ready" or evaluation.ai_choice not in {"BUY", "SELL"}:
        return evaluation
    if confidence is None or confidence < Decimal(run.config_json["ai_action_min_confidence"]):
        evaluation.ai_status = "low_confidence"
        return evaluation
    if run.status != "running" or now >= _aware(run.ends_at) or (now - _aware(sample.observed_at)).total_seconds() > run.config_json["max_quote_age_seconds"]:
        evaluation.ai_status = "stale"
        return evaluation
    if _queue_order(db, run, evaluation, "ai", evaluation.ai_choice, sample, now):
        evaluation.ai_action = evaluation.ai_choice
    else:
        evaluation.ai_status = "ineligible"
    return evaluation


def payload(db: Session, chain_id: int, symbol: str, sample: MarketSample | None) -> dict:
    run = latest_run(db, chain_id, symbol)
    if run is None:
        return {"run": None, "arms": None, "evaluations": [], "trades": [], "orders": [], "rules": RULES}
    fresh = sample is not None and sample.chain_id == chain_id and sample.symbol == symbol and (_now() - _aware(sample.observed_at)).total_seconds() <= 30
    mark = sample if fresh else None
    evaluations = db.scalars(select(PilotV2Evaluation).where(
        PilotV2Evaluation.run_id == run.id,
    ).order_by(PilotV2Evaluation.id.desc()).limit(20)).all()
    trades = db.scalars(select(PilotV2Trade).where(
        PilotV2Trade.run_id == run.id,
    ).order_by(PilotV2Trade.id.desc()).limit(20)).all()
    orders = db.scalars(select(PilotV2Order).where(
        PilotV2Order.run_id == run.id,
    ).order_by(PilotV2Order.id.desc()).limit(20)).all()
    counts = dict(db.execute(select(PilotV2Trade.arm, func.count(PilotV2Trade.id)).where(
        PilotV2Trade.run_id == run.id,
    ).group_by(PilotV2Trade.arm)).all())
    evaluation_count = db.scalar(select(func.count(PilotV2Evaluation.id)).where(PilotV2Evaluation.run_id == run.id)) or 0
    arms = {}
    for arm in ("baseline", "ai"):
        equity = getattr(run, f"final_{arm}_equity") if run.status == "finished" else _marked_equity(run, arm, mark)
        arms[arm] = {
            "cash_usdc": str(getattr(run, f"{arm}_cash")),
            "position_qty": str(getattr(run, f"{arm}_qty")),
            "equity_usdc": None if equity is None else str(equity),
            "trades": counts.get(arm, 0),
            "execution_cost_usdc": str(getattr(run, f"{arm}_costs")),
        }
    return {
        "run": {
            "id": run.id, "status": run.status, "started_at": _aware(run.started_at).isoformat(),
            "ends_at": _aware(run.ends_at).isoformat(),
            "finished_at": None if run.finished_at is None else _aware(run.finished_at).isoformat(),
            "last_decision_at": None if run.last_decision_at is None else _aware(run.last_decision_at).isoformat(),
            "model_cost_usdc": str(run.model_costs), "model_unknown_calls": run.model_unknown_calls,
            "evaluation_count": evaluation_count,
        },
        "arms": arms,
        "evaluations": [{
            "at": _aware(row.occurred_at).isoformat(), "signal": row.signal,
            "reason": row.reason, "imbalance": None if row.book_imbalance is None else str(row.book_imbalance),
            "return_30s": None if row.return_30s is None else str(row.return_30s),
            "baseline_action": row.baseline_action, "ai_choice": row.ai_choice,
            "ai_confidence": None if row.ai_confidence is None else str(row.ai_confidence),
            "ai_status": row.ai_status, "ai_action": row.ai_action,
            "latency_ms": row.model_latency_ms,
        } for row in evaluations],
        "trades": [{
            "at": _aware(row.occurred_at).isoformat(), "arm": row.arm, "side": row.side,
            "quantity": str(row.quantity), "price": str(row.execution_price),
            "cost_usdc": str(row.cost_usdc),
        } for row in trades],
        "orders": [{
            "at": _aware(row.created_at).isoformat(), "arm": row.arm, "side": row.side,
            "status": row.status, "price": str(row.limit_price), "quantity": str(row.quantity),
        } for row in orders],
        "rules": run.config_json,
    }
