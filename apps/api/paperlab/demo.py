from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from paperlab.config import get_settings
from paperlab.domain import BarData, CENT, FEE_RATE, ZERO, crossover, demo_bar, deterministic_order_id, quantize_crypto_qty, stable_hash
from paperlab.models import Bar, BudgetReservation, Decision, Experiment, Fill, ModelCall, NewsVersion, OrderIntent, PortfolioSnapshot, Snapshot


ROOT = Path(__file__).resolve().parents[3]
NEWS_FIXTURE_PATH = ROOT / "fixtures" / "demo_news.json"
POLICY_PATH = ROOT / "packages" / "policy" / "filter-v1.json"
with NEWS_FIXTURE_PATH.open(encoding="utf-8") as file:
    DEMO_NEWS = json.load(file)
with POLICY_PATH.open(encoding="utf-8") as file:
    FILTER_POLICY = json.load(file)

EXPERIMENT_CONFIG = {
    "strategy": {"name": "sma-cross-v1", "fast_period": 20, "slow_period": 50, "bar_timeframe": "1Hour", "symbol": "BTC/USD", "fixed_order_notional_usd": "100"},
    "filter_policy": FILTER_POLICY,
    "source": "PaperLab DEMO synthetic generator v1",
    "cost_policy": {"name": "demo-cost-v1", "market_fee_rate": "0.0025", "additional_slippage_rate": "0", "disclaimer": "Illustrative synthetic assumption; not an Alpaca fee quote."},
    "initial_cash_usd": "10000",
    "limits": {"max_order_notional_usd": "100", "max_open_positions": 1, "max_daily_orders": 6, "max_drawdown_usd": "500"},
    "models": {"B": "synthetic-jev-fixture-v1", "C": "synthetic-summary-plus-jev-fixture-v1"},
    "prompts_version": "demo-prompts-v1",
    "seed": 271828,
    "next_bar_index": 57,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_default_experiment(db: Session) -> Experiment:
    experiment = db.scalar(select(Experiment).where(Experiment.name == "Demonstração PaperLab"))
    if experiment:
        return experiment
    return create_demo_experiment(db, "Demonstração PaperLab")


def create_demo_experiment(db: Session, name: str) -> Experiment:
    experiment = Experiment(
        id=str(uuid4()),
        name=name,
        mode="DEMO",
        status="paused",
        config_json=EXPERIMENT_CONFIG,
        config_hash=stable_hash(EXPERIMENT_CONFIG),
        entries_paused=True,
        next_bar_index=57,
    )
    db.add(experiment)
    seed_snapshot = Snapshot(
        id=str(uuid4()), experiment_id=experiment.id, cycle_id="demo-seed-v1", cycle_index=-1,
        mode="DEMO", cutoff_at=demo_bar(56).bar_at, source="PaperLab DEMO synthetic generator v1",
        source_version="1", content_hash=stable_hash({"seed": 271828, "through_index": 56}),
        payload_json={"synthetic": True, "seed": 271828, "history_bars": 57},
    )
    db.add(seed_snapshot)
    # PostgreSQL enforces the snapshot foreign key on every bar insert. Flush
    # the parent snapshot before queuing the bars that reference it; SQLite's
    # test configuration can otherwise hide this unit-of-work ordering issue.
    db.flush()
    bars = [demo_bar(index) for index in range(57)]
    for item in bars:
        db.add(_bar_row(seed_snapshot.id, item))
    last_price = bars[-1].close
    for arm in ("A", "B", "C"):
        db.add(PortfolioSnapshot(
            experiment_id=experiment.id, cycle_id="demo-seed-v1", mode="DEMO", arm=arm,
            cash_usd=Decimal("10000"), position_qty=ZERO, position_cost_basis_usd=ZERO,
            mark_price_usd=last_price, equity_usd=Decimal("10000"), realized_usd=ZERO,
            unrealized_usd=ZERO, trading_cost_usd=ZERO, ai_cost_usd=None, marked_at=bars[-1].bar_at,
        ))
    db.commit()
    return experiment


def _bar_row(snapshot_id: str, bar: BarData) -> Bar:
    return Bar(snapshot_id=snapshot_id, symbol=bar.symbol, bar_at=bar.bar_at,
               open=bar.open, high=bar.high, low=bar.low, close=bar.close,
               volume=bar.volume, source=bar.source)


def _portfolio(db: Session, experiment_id: str, arm: str) -> PortfolioSnapshot:
    return db.scalar(select(PortfolioSnapshot).where(
        PortfolioSnapshot.experiment_id == experiment_id, PortfolioSnapshot.arm == arm,
    ).order_by(PortfolioSnapshot.marked_at.desc(), PortfolioSnapshot.id.desc()).limit(1))


def _news_for_cycle(index: int, cutoff: datetime) -> list[dict]:
    delivery_index = {57: 0, 108: 1, 158: 2}.get(index)
    if delivery_index is None:
        return []
    article = DEMO_NEWS[delivery_index]
    created = datetime.fromisoformat(article["created_at"].replace("Z", "+00:00"))
    if created > cutoff:
        return []
    return [article]


def _filter_result(articles: list[dict], summary: dict | None = None) -> tuple[str, str, list[str]]:
    if not articles:
        return "ALLOW", "sem_contexto_textual_novo", []
    evidence = " ".join((item.get("title", "") + " " + item.get("summary", "")).lower() for item in articles)
    ids = [item["id"] for item in articles]
    if summary:
        missing = [source_id for source_id in summary.get("source_ids", []) if source_id not in ids]
        if missing:
            return "ABSTAIN", "referencia_de_fonte_inexistente", ids
        evidence += " " + " ".join(summary.get("risk_alerts", []))
    if "security review" in evidence or "security incident" in evidence:
        return "BLOCK", "evento_de_risco_descrito_na_fonte", ids
    if "conflicting" in evidence or "incomplete" in evidence or "ambiguous" in evidence:
        return "ABSTAIN", "informacao_ambigua", ids
    return "ALLOW", "evidencia_sem_evento_de_risco", ids


def _demo_summary(articles: list[dict]) -> dict:
    # The synthetic analyzer only extracts from supplied fixtures; no network or
    # actual generative model is used in DEMO.
    source_ids = [article["id"] for article in articles]
    risk_alerts = [article["title"] for article in articles if "security" in article["title"].lower()]
    uncertainties = [article["title"] for article in articles if "conflicting" in article["title"].lower()]
    return {"source_ids": source_ids, "facts": [{"source_id": i, "text": next(a["title"] for a in articles if a["id"] == i)} for i in source_ids], "risk_alerts": risk_alerts, "uncertainties": uncertainties}


def _add_synthetic_model_call(db: Session, experiment_id: str, cycle_id: str, arm: str, model: str, response: dict):
    db.add(ModelCall(
        experiment_id=experiment_id, cycle_id=cycle_id, arm=arm, model_requested=model,
        model_returned=model, provider="PaperLab DEMO fixture", prompt_hash=stable_hash({"model": model, "fixture": response}),
        response_json=response, cost_usd=Decimal("0"), cost_status="not_applicable",
        latency_ms=0, status="synthetic",
    ))


def _already_ordered_today(db: Session, experiment_id: str, arm: str, index: int) -> bool:
    count = db.scalar(select(func.count(OrderIntent.id)).join(
        Snapshot, Snapshot.cycle_id == OrderIntent.cycle_id
    ).where(
        OrderIntent.experiment_id == experiment_id,
        OrderIntent.arm == arm,
        Snapshot.experiment_id == experiment_id,
        Snapshot.cycle_index >= index - 23,
    ))
    return bool(count and count >= 6)


def _create_paperless_fill(db: Session, experiment: Experiment, arm: str, cycle_id: str, index: int,
                           side: str, quantity: Decimal, price: Decimal, notional: Decimal) -> tuple[Decimal, Decimal]:
    client_id = deterministic_order_id(experiment.id, arm, index, side)
    existing = db.scalar(select(OrderIntent).where(
        OrderIntent.experiment_id == experiment.id, OrderIntent.client_order_id == client_id,
    ))
    if existing:
        return ZERO, ZERO
    intent = OrderIntent(
        experiment_id=experiment.id, cycle_id=cycle_id, mode="DEMO", arm=arm,
        symbol="BTC/USD", side=side.lower(), client_order_id=client_id,
        status="filled", quantity=quantity, notional_usd=notional,
        submitted_at=_now(), updated_at=_now(),
    )
    db.add(intent)
    db.flush()
    fee = (notional * FEE_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    db.add(Fill(order_intent_id=intent.id, fill_identity=f"demo-fill:{client_id}", mode="DEMO",
                quantity=quantity, price=price, fee_amount=fee, fee_currency="USD", occurred_at=demo_bar(index).bar_at))
    return notional, fee


def run_demo_cycle(db: Session, experiment: Experiment) -> dict:
    if experiment.mode != "DEMO":
        raise ValueError("Somente DEMO pode avançar pelo worker offline.")
    if experiment.status not in {"running", "paused_entries"}:
        raise ValueError("A demonstração está pausada. Inicie-a para gerar ciclos.")

    index = experiment.next_bar_index
    cycle_id = f"demo-{experiment.config_hash[:10]}-{index:06d}"
    existing = db.scalar(select(Snapshot).where(Snapshot.experiment_id == experiment.id, Snapshot.cycle_id == cycle_id))
    if existing:
        return {"cycle_id": cycle_id, "cycle_index": index, "duplicate": True}

    current = demo_bar(index)
    history_rows = db.scalars(select(Bar).join(Snapshot, Snapshot.id == Bar.snapshot_id).where(
        Snapshot.experiment_id == experiment.id,
        Bar.symbol == "BTC/USD",
        Snapshot.cycle_index < index,
    ).order_by(Bar.bar_at.desc()).limit(50)).all()
    closes = [row.close for row in reversed(history_rows)] + [current.close]
    candidate = crossover(closes)
    news = _news_for_cycle(index, current.bar_at)

    payload = {
        "synthetic": True,
        "seed": 271828,
        "cycle_id": cycle_id,
        "cycle_index": index,
        "cutoff_at": current.bar_at.isoformat(),
        "bar": {"symbol": current.symbol, "timeframe": "1Hour", "closed": True, "at": current.bar_at.isoformat(), "open": str(current.open), "high": str(current.high), "low": str(current.low), "close": str(current.close), "volume": str(current.volume)},
        "news_ids": [item["id"] for item in news],
        "news_feed_status": "healthy_with_articles" if news else "healthy_no_articles",
    }
    snapshot = Snapshot(
        id=str(uuid4()), experiment_id=experiment.id, cycle_id=cycle_id, cycle_index=index,
        mode="DEMO", cutoff_at=current.bar_at, source="PaperLab DEMO synthetic generator v1",
        source_version="1", content_hash=stable_hash(payload), payload_json=payload,
    )
    db.add(snapshot)
    db.flush()
    db.add(_bar_row(snapshot.id, current))
    for article in news:
        title_summary = {"title": article["title"], "summary": article["summary"]}
        db.add(NewsVersion(
            snapshot_id=snapshot.id, article_id=article["id"], source=article["source"],
            title=article["title"], summary=article["summary"],
            created_at=datetime.fromisoformat(article["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(article["updated_at"].replace("Z", "+00:00")),
            first_seen_at=current.bar_at, version=1, content_hash=stable_hash(title_summary), synthetic=True,
        ))

    for arm in ("A", "B", "C"):
        old = _portfolio(db, experiment.id, arm)
        position_qty = old.position_qty
        cost_basis = old.position_cost_basis_usd
        cash = old.cash_usd
        realized = old.realized_usd
        cumulative_cost = old.trading_cost_usd
        filter_result = None
        evidence_ids: list[str] = []
        reason_code = "sem_sinal"
        reason = "Nenhum cruzamento novo nas médias móveis fechadas."
        outcome = "no_candidate"
        action = candidate

        if candidate == "BUY":
            if arm == "A":
                filter_result, reason_code, evidence_ids = "ALLOW", "estrategia_base", []
            else:
                if not news:
                    filter_result, reason_code, evidence_ids = "ALLOW", "sem_contexto_textual_novo", []
                else:
                    summary = _demo_summary(news) if arm == "C" else None
                    if arm == "C":
                        _add_synthetic_model_call(db, experiment.id, cycle_id, "C", "synthetic-summary-v1", summary)
                    filter_result, reason_code, evidence_ids = _filter_result(news, summary)
                    _add_synthetic_model_call(db, experiment.id, cycle_id, arm, "synthetic-jev-fixture-v1", {"classification": filter_result, "reason_code": reason_code, "evidence_ids": evidence_ids})
            outcome = "candidate"
            reason = "Cruzamento de alta confirmado com candles fechados." if arm == "A" else ("Sem contexto textual novo: política versionada segue a estratégia-base." if reason_code == "sem_contexto_textual_novo" else f"Classificação sintética do filtro: {filter_result}.")
            if filter_result == "BLOCK":
                outcome, reason_code = "vetoed", reason_code
            elif filter_result == "ABSTAIN":
                outcome, reason_code = "abstained", reason_code
            elif experiment.entries_paused:
                outcome, reason_code = "blocked", "entradas_pausadas"
            elif position_qty > ZERO:
                outcome, reason_code = "blocked", "ja_posicionado"
            elif _already_ordered_today(db, experiment.id, arm, index):
                outcome, reason_code = "blocked", "limite_de_frequencia"
            elif cash < Decimal("100.25"):
                outcome, reason_code = "blocked", "saldo_insuficiente"
            else:
                high_water = db.scalar(select(func.max(PortfolioSnapshot.equity_usd)).where(
                    PortfolioSnapshot.experiment_id == experiment.id, PortfolioSnapshot.arm == arm,
                )) or Decimal("10000")
                marked_equity = cash + position_qty * current.close
                if high_water - marked_equity >= get_settings().max_simulated_drawdown_usd:
                    outcome, reason_code = "blocked", "limite_de_perda_simulada"
                else:
                    qty = quantize_crypto_qty(Decimal("100"), current.close)
                    planned_notional = (qty * current.close).quantize(CENT, rounding=ROUND_HALF_UP)
                    notional, fee = _create_paperless_fill(db, experiment, arm, cycle_id, index, "BUY",
                                                          qty, current.close, planned_notional)
                    if notional:
                        position_qty += qty
                        cash -= notional + fee
                        cost_basis = (old.position_qty * old.position_cost_basis_usd + notional + fee) / position_qty
                        cumulative_cost += fee
                        outcome, reason_code = "filled", "ordem_sintetica_executada"
                    else:
                        outcome, reason_code = "blocked", "intencao_duplicada"
        elif candidate == "SELL":
            if position_qty <= ZERO:
                outcome, reason_code = "no_position", "sem_posicao_para_encerrar"
                reason = "Cruzamento de baixa detectado; não havia posição aberta neste braço."
                action = "HOLD"
            else:
                notional = (position_qty * current.close).quantize(CENT, rounding=ROUND_HALF_UP)
                _, fee = _create_paperless_fill(db, experiment, arm, cycle_id, index, "SELL", position_qty, current.close, notional)
                proceeds = notional - fee
                realized += proceeds - position_qty * cost_basis
                cash += proceeds
                cumulative_cost += fee
                position_qty = ZERO
                cost_basis = ZERO
                outcome, reason_code = "filled", "saida_baseline_independente"
                reason = "Cruzamento de baixa: saída determinística, independente de filtros ou modelos."
        else:
            if position_qty > ZERO:
                outcome, reason_code = "holding", "posicao_mantida"
            db.add(Decision(
                experiment_id=experiment.id, cycle_id=cycle_id, snapshot_id=snapshot.id, mode="DEMO",
                arm=arm, candidate=candidate, action=action, outcome=outcome,
                reason_code=reason_code, reason=reason, filter_result=filter_result,
                evidence_ids=evidence_ids, latency_ms=0,
            ))
            market_value = position_qty * current.close
            unrealized = market_value - position_qty * cost_basis
            db.add(PortfolioSnapshot(
                experiment_id=experiment.id, cycle_id=cycle_id, mode="DEMO", arm=arm,
                cash_usd=cash, position_qty=position_qty, position_cost_basis_usd=cost_basis,
                mark_price_usd=current.close, equity_usd=cash + market_value,
                realized_usd=realized, unrealized_usd=unrealized, trading_cost_usd=cumulative_cost,
                ai_cost_usd=None, marked_at=current.bar_at,
            ))
            continue

        market_value = position_qty * current.close
        unrealized = market_value - position_qty * cost_basis
        db.add(Decision(
            experiment_id=experiment.id, cycle_id=cycle_id, snapshot_id=snapshot.id, mode="DEMO",
            arm=arm, candidate=candidate, action=action, outcome=outcome,
            reason_code=reason_code, reason=reason, filter_result=filter_result,
            evidence_ids=evidence_ids, latency_ms=0,
        ))
        db.add(PortfolioSnapshot(
            experiment_id=experiment.id, cycle_id=cycle_id, mode="DEMO", arm=arm,
            cash_usd=cash, position_qty=position_qty, position_cost_basis_usd=cost_basis,
            mark_price_usd=current.close, equity_usd=cash + market_value,
            realized_usd=realized, unrealized_usd=unrealized, trading_cost_usd=cumulative_cost,
            ai_cost_usd=None, marked_at=current.bar_at,
        ))

    experiment.next_bar_index += 1
    db.commit()
    return {"cycle_id": cycle_id, "cycle_index": index, "candidate": candidate, "snapshot_hash": snapshot.content_hash, "news_count": len(news)}


def set_demo_status(db: Session, experiment: Experiment, action: str) -> dict:
    if experiment.mode != "DEMO":
        raise ValueError("Ação indisponível para este modo.")
    if action == "start":
        if experiment.status == "ended":
            raise ValueError("Experimentos encerrados são imutáveis; crie outro experimento.")
        if experiment.status == "running" and not experiment.entries_paused:
            return {"status": "running", "duplicate": True, "message": "Experimento já está em execução."}
        experiment.status = "running"
        experiment.entries_paused = False
        if experiment.started_at is None:
            experiment.started_at = _now()
        db.commit()
        return run_demo_cycle(db, experiment)
    if action == "pause":
        if experiment.status == "ended":
            raise ValueError("O experimento já foi encerrado.")
        experiment.status = "paused_entries"
        experiment.entries_paused = True
        db.commit()
        return {"status": experiment.status, "entries_paused": True, "message": "Novas entradas pausadas; saídas e reconciliação permanecem ativas."}
    if action == "stop":
        portfolios = {arm: _portfolio(db, experiment.id, arm) for arm in ("A", "B", "C")}
        remaining = {arm: {"qty": str(p.position_qty), "mark_usd": str((p.position_qty * p.mark_price_usd).quantize(CENT))} for arm, p in portfolios.items() if p and p.position_qty > ZERO}
        experiment.status = "ended"
        experiment.entries_paused = True
        experiment.ended_at = _now()
        db.commit()
        return {"status": "ended", "remaining_positions": remaining}
    raise ValueError("Ação não reconhecida.")
