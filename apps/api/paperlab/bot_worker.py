"""Opt-in, read-only Monad/Kuru terminal worker. It never signs or sends transactions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import time
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from websockets.asyncio.client import connect

from paperlab.budget import BudgetExceeded, reconcile_ai_budget, reserve_ai_budget
from paperlab.config import get_settings
from paperlab.database import SessionLocal
from paperlab.demo import ensure_default_experiment
from paperlab.market_feed import OrderBookState, decode_orderbook_message, market_address_is_valid, terminal_jev_questions
from paperlab.models import JevObservation, MarketEvent, MarketSample, TerminalControl
from paperlab.openrouter import ModelIntegrationError, OpenRouterClient
from paperlab.terminal_state import ensure_terminal_control


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("paperlab.market_worker")
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_control(db):
    return ensure_terminal_control(db, settings.monad_chain_id)


def _set_status(status: str, error: str | None = None, *, block_number: int | None = None):
    with SessionLocal() as db:
        control = ensure_control(db)
        control.status = status
        control.last_error = error
        if block_number is not None:
            control.last_block_number = block_number
        control.updated_at = _now()
        db.commit()


def _prune_terminal_history():
    cutoff = _now() - timedelta(days=30)
    with SessionLocal() as db:
        old_samples = select(MarketSample.id).where(MarketSample.observed_at < cutoff)
        db.execute(delete(JevObservation).where(JevObservation.sample_id.in_(old_samples)))
        db.execute(delete(JevObservation).where(JevObservation.observed_at < cutoff))
        db.execute(delete(MarketSample).where(MarketSample.observed_at < cutoff))
        db.execute(delete(MarketEvent).where(MarketEvent.occurred_at < cutoff))
        db.commit()


async def monad_block_number() -> tuple[int, int]:
    async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
        chain_response = await client.post(settings.monad_rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
        chain_response.raise_for_status()
        chain = chain_response.json()
        chain_id = int(chain["result"], 16)
        if chain_id != settings.monad_chain_id:
            expected = "Monad Mainnet" if settings.monad_chain_id == 143 else "Monad Testnet"
            raise RuntimeError(f"RPC configurado na rede {chain_id}; esperado {expected} (chain ID {settings.monad_chain_id}).")
        block_response = await client.post(settings.monad_rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []})
        block_response.raise_for_status()
        block = block_response.json()
        return chain_id, int(block["result"], 16)


async def assert_market_contract_exists() -> None:
    async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
        response = await client.post(settings.monad_rpc_url, json={
            "jsonrpc": "2.0", "id": 3, "method": "eth_getCode",
            "params": [settings.kuru_market_address, "latest"],
        })
        response.raise_for_status()
        code = response.json().get("result")
    if not isinstance(code, str) or code.lower() in {"0x", "0x0", "0x00"}:
        network = "Monad Mainnet" if settings.monad_chain_id == 143 else "Monad Testnet"
        raise RuntimeError(f"KURU_MARKET_ADDRESS não tem contrato na {network} configurada.")


def _persist_message(message: dict, block_number: int | None, book: OrderBookState) -> tuple[MarketSample | None, bool]:
    parsed = decode_orderbook_message(message)
    current_bid, current_ask = book.apply(parsed)
    sample = None
    jev_due = False
    now = _now()
    with SessionLocal() as db:
        control = ensure_control(db)
        for trade in parsed.trades:
            key = f"{settings.kuru_market_address.lower()}:{trade.event_key}"[:200]
            if settings.monad_chain_id != 10143:
                key = f"{settings.monad_chain_id}:{key}"[:200]
            exists = db.scalar(select(MarketEvent.id).where(MarketEvent.event_key == key))
            if exists is None:
                db.add(MarketEvent(chain_id=settings.monad_chain_id, event_key=key, occurred_at=trade.occurred_at, side=trade.side,
                    price=trade.price, size=trade.size, tx_hash=trade.tx_hash))
        if current_bid and current_ask and current_bid <= current_ask:
            last_at = control.last_sample_at
            if last_at is None or (now - (last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc))).total_seconds() >= max(1, settings.terminal_sample_interval_seconds):
                mid = (current_bid + current_ask) / Decimal(2)
                spread = (current_ask - current_bid) / mid * Decimal(10000) if mid else Decimal(0)
                sample = MarketSample(chain_id=settings.monad_chain_id, observed_at=now, symbol=settings.kuru_symbol, best_bid=current_bid,
                    best_ask=current_ask, mid_price=mid, spread_bps=spread, block_number=block_number)
                db.add(sample)
                db.flush()
                control.last_sample_at = now
                control.last_block_number = block_number
                last_jev = control.last_jev_at
                elapsed = settings.terminal_jev_interval_seconds + 1 if last_jev is None else (now - (last_jev if last_jev.tzinfo else last_jev.replace(tzinfo=timezone.utc))).total_seconds()
                jev_due = control.jev_enabled and elapsed >= max(30, settings.terminal_jev_interval_seconds)
        control.status = "connected"
        control.last_error = None
        control.updated_at = now
        db.commit()
        if sample is not None:
            db.refresh(sample)
        return sample, jev_due


async def _classify_with_jev(sample: MarketSample):
    if not settings.openrouter_api_key:
        return
    cap = Decimal(settings.ai_call_budget_usd)
    if cap <= 0:
        return
    cycle_id = f"terminal-{sample.id}-{uuid4().hex[:8]}"
    reservation_key = f"terminal-jev-{sample.id}-{uuid4().hex[:12]}"
    with SessionLocal() as db:
        experiment = ensure_default_experiment(db)
        try:
            reserve_ai_budget(db, experiment_id=experiment.id, cycle_id=cycle_id, reservation_key=reservation_key,
                proposed_usd=cap, per_call_cap_usd=cap, daily_cap_usd=Decimal(settings.ai_daily_budget_usd))
        except BudgetExceeded as exc:
            db.add(JevObservation(sample_id=sample.id, model=settings.jev_model, status="budget_blocked",
                result_json=None, message=str(exc), cost_usd=None, cost_status="not_called", latency_ms=0))
            control = ensure_control(db)
            control.last_jev_at = _now()
            db.commit()
            return

    state = {
        "mode": "read_only_market_observation",
        "chain_id": settings.monad_chain_id,
        "symbol": sample.symbol,
        "observed_at": sample.observed_at.isoformat(),
        "best_bid": str(sample.best_bid),
        "best_ask": str(sample.best_ask),
        "mid_price": str(sample.mid_price),
        "spread_bps": str(sample.spread_bps),
        "block_number": sample.block_number,
        "orders_enabled": False,
    }
    result_json = None
    error_message = None
    cost = None
    cost_status = "unknown"
    status = "failed"
    latency_ms = 0
    try:
        client = OpenRouterClient(settings.openrouter_api_key, timeout=25)
        result = await client.jev_classify(settings.jev_model, state, terminal_jev_questions(sample.symbol))
        result_json = result.response
        cost = result.cost_usd
        cost_status = "reported" if cost is not None else "unknown"
        status = "ready"
        latency_ms = result.latency_ms
        error_message = "Postura BUY/SELL/HOLD somente observacional; não é ordem nem recomendação."
    except (ModelIntegrationError, ValueError) as exc:
        error_message = str(exc)
    except Exception:
        error_message = "Falha ao consultar Jev; nenhum resultado foi registrado como decisão válida."
        logger.exception("Jev classification failed")

    with SessionLocal() as db:
        try:
            reconcile_ai_budget(db, reservation_key, cost)
        except Exception:
            db.rollback()
            logger.exception("Could not reconcile Jev budget reservation")
        db.add(JevObservation(sample_id=sample.id, model=settings.jev_model, status=status,
            result_json=result_json, message=error_message or "Falha sem detalhe.", cost_usd=cost,
            cost_status=cost_status, latency_ms=latency_ms))
        control = ensure_control(db)
        control.last_jev_at = _now()
        control.updated_at = _now()
        db.commit()


async def _run_feed_session():
    if not market_address_is_valid(settings.kuru_market_address):
        raise RuntimeError("KURU_MARKET_ADDRESS ausente ou inválido; configure o endereço do mercado MON/USDC.")
    if not settings.kuru_ws_url.startswith("wss://"):
        raise RuntimeError("KURU_WS_URL deve usar WSS seguro.")
    _, block_number = await monad_block_number()
    await assert_market_contract_exists()
    _set_status("starting", block_number=block_number)
    subscription = {"type": "subscribe", "channel": "frontendOrderbook", "market": settings.kuru_market_address.lower()}
    last_rpc = time.monotonic()
    async with connect(settings.kuru_ws_url, open_timeout=12, close_timeout=5, ping_interval=20, ping_timeout=20, max_size=10 * 1024 * 1024) as socket:
        await socket.send(json.dumps(subscription))
        book = OrderBookState()
        while True:
            with SessionLocal() as db:
                control = ensure_control(db)
                enabled = control.monitor_enabled
            if not enabled:
                return
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=5)
            except TimeoutError:
                if time.monotonic() - last_rpc >= 15:
                    _, block_number = await monad_block_number()
                    _set_status("connected", block_number=block_number)
                    last_rpc = time.monotonic()
                continue
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "error":
                raise RuntimeError("A Kuru recusou a assinatura do mercado solicitado.")
            if payload.get("type") == "subscribed" and payload.get("status") not in {"success", "pending"}:
                raise RuntimeError("A Kuru recusou a assinatura do mercado solicitado.")
            if time.monotonic() - last_rpc >= 15:
                try:
                    _, block_number = await monad_block_number()
                    last_rpc = time.monotonic()
                except Exception:
                    logger.exception("Monad RPC temporarily unavailable")
            sample, jev_due = _persist_message(payload, block_number, book)
            if jev_due and sample is not None:
                await _classify_with_jev(sample)


async def run():
    _prune_terminal_history()
    last_pruned = time.monotonic()
    while True:
        if time.monotonic() - last_pruned >= 24 * 60 * 60:
            _prune_terminal_history()
            last_pruned = time.monotonic()
        with SessionLocal() as db:
            control = ensure_control(db)
            enabled = control.monitor_enabled
        if not enabled:
            await asyncio.sleep(2)
            continue
        try:
            await _run_feed_session()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Market feed reconnecting: %s", exc)
            _set_status("error", str(exc)[:500])
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
