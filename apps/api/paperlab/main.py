from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import csv
import io
import secrets
import time
from typing import Literal, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from paperlab.alpaca import AlpacaDataClient, IntegrationError, paper_preflight
from paperlab.config import get_settings
from paperlab.database import Base, SessionLocal, engine, get_db
from paperlab.demo import create_demo_experiment, ensure_default_experiment, run_demo_cycle, set_demo_status
from paperlab.domain import ZERO
from paperlab.market_feed import market_address_is_valid
from paperlab.models import AdminUser, Bar, Decision, Experiment, Fill, IntegrationEvent, JevObservation, MarketEvent, MarketSample, ModelCall, NewsVersion, OrderIntent, PortfolioSnapshot, Snapshot, TerminalControl
from paperlab.openrouter import ModelIntegrationError, OpenRouterClient


settings = get_settings()
if not settings.session_secret_key or len(settings.session_secret_key) < 32:
    raise RuntimeError("SESSION_SECRET_KEY é obrigatório e deve ter pelo menos 32 caracteres.")
if not settings.admin_username or len(settings.admin_password) < 12:
    raise RuntimeError("Configure ADMIN_USERNAME e uma ADMIN_PASSWORD com pelo menos 12 caracteres.")

password_hasher = PasswordHash.recommended()
login_attempts: dict[str, deque[float]] = defaultdict(deque)
app = FastAPI(title="PaperLab API", version="0.1.0", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="paperlab_session",
    max_age=8 * 60 * 60,
    same_site="strict",
    https_only=settings.cookie_secure,
)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ExperimentBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal["DEMO"] = "DEMO"


class TerminalControlBody(BaseModel):
    action: Literal["start_monitor", "stop_monitor", "enable_jev", "disable_jev"]


def require_user(request: Request):
    if not request.session.get("username"):
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    return request.session["username"]


def require_csrf(request: Request, token: Optional[str]):
    expected = request.session.get("csrf_token")
    if not expected or not token or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="Token de segurança inválido. Atualize a sessão e tente novamente.")


def integration_event(db: Session, name: str, status: str, message: str, details: Optional[dict] = None):
    db.add(IntegrationEvent(integration=name, status=status, message=message, details_json=details or {}))
    db.commit()


def _dt_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _latest_portfolio(db: Session, experiment_id: str, arm: str):
    return db.scalar(select(PortfolioSnapshot).where(
        PortfolioSnapshot.experiment_id == experiment_id, PortfolioSnapshot.mode == "DEMO", PortfolioSnapshot.arm == arm,
    ).order_by(PortfolioSnapshot.marked_at.desc(), PortfolioSnapshot.id.desc()).limit(1))


def _experiment_metrics(db: Session, experiment: Experiment) -> dict:
    arms: dict[str, dict] = {}
    initial_cash = Decimal(experiment.config_json["initial_cash_usd"])
    for arm in ("A", "B", "C"):
        series = db.scalars(select(PortfolioSnapshot).where(
            PortfolioSnapshot.experiment_id == experiment.id,
            PortfolioSnapshot.mode == "DEMO",
            PortfolioSnapshot.arm == arm,
        ).order_by(PortfolioSnapshot.marked_at.asc(), PortfolioSnapshot.id.asc())).all()
        latest = series[-1]
        max_equity = series[0].equity_usd
        max_drawdown = ZERO
        for item in series:
            max_equity = max(max_equity, item.equity_usd)
            max_drawdown = max(max_drawdown, max_equity - item.equity_usd)
        orders = db.scalars(select(OrderIntent).where(
            OrderIntent.experiment_id == experiment.id, OrderIntent.mode == "DEMO", OrderIntent.arm == arm,
        )).all()
        decisions = db.scalars(select(Decision).where(
            Decision.experiment_id == experiment.id, Decision.mode == "DEMO", Decision.arm == arm,
        )).all()
        sell_cycles = {order.cycle_id for order in orders if order.side == "sell"}
        realized_changes: list[Decimal] = []
        prior_realized = ZERO
        prior_cycle = None
        for item in series:
            if prior_cycle is not None and item.cycle_id in sell_cycles:
                delta = item.realized_usd - prior_realized
                realized_changes.append(delta)
            prior_cycle = item.cycle_id
            prior_realized = item.realized_usd
        wins = sum(1 for amount in realized_changes if amount > ZERO)
        start_price = series[0].mark_price_usd
        current_price = latest.mark_price_usd
        hold_equity = initial_cash / start_price * current_price
        ret = (latest.equity_usd / initial_cash - 1) * Decimal("100") if initial_cash else ZERO
        exposure = latest.position_qty * latest.mark_price_usd
        arms[arm] = {
            "arm": arm,
            "cash_usd": str(latest.cash_usd),
            "position_qty": str(latest.position_qty),
            "position_mark_usd": str(exposure),
            "equity_usd": str(latest.equity_usd),
            "realized_usd": str(latest.realized_usd),
            "unrealized_usd": str(latest.unrealized_usd),
            "return_pct": str(ret),
            "max_drawdown_usd": str(max_drawdown),
            "exposure_pct": str(exposure / latest.equity_usd * 100 if latest.equity_usd else ZERO),
            "trade_count": len(orders),
            "closed_operations": len(realized_changes),
            "win_rate_pct": str(Decimal(wins) / Decimal(len(realized_changes)) * 100) if realized_changes else None,
            "average_gain_usd": str(sum((v for v in realized_changes if v > ZERO), ZERO) / Decimal(max(1, sum(1 for v in realized_changes if v > ZERO)))) if any(v > ZERO for v in realized_changes) else None,
            "average_loss_usd": str(sum((v for v in realized_changes if v < ZERO), ZERO) / Decimal(max(1, sum(1 for v in realized_changes if v < ZERO)))) if any(v < ZERO for v in realized_changes) else None,
            "trading_cost_usd": str(latest.trading_cost_usd),
            "ai_infrastructure_cost_usd": None,
            "ai_cost_status": "Não aplicável à DEMO sintética",
            "veto_count": sum(1 for row in decisions if row.outcome == "vetoed"),
            "abstention_count": sum(1 for row in decisions if row.outcome == "abstained"),
            "failure_count": sum(1 for row in decisions if row.outcome == "failed"),
            "avg_latency_ms": 0 if not decisions else sum(row.latency_ms for row in decisions) // len(decisions),
            "evaluated_opportunities": sum(1 for row in decisions if row.candidate == "BUY"),
            "sample_status": "amostra insuficiente" if not realized_changes else "operações encerradas disponíveis",
            "flat_cash_benchmark_usd": str(initial_cash),
            "buy_and_hold_benchmark_usd": str(hold_equity),
            "equity_curve": [{"at": _dt_iso(item.marked_at), "equity_usd": str(item.equity_usd)} for item in series],
        }
    return arms


def _find_experiment(db: Session, experiment_id: str) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experimento não encontrado.")
    return experiment


def _latest_integration_states(db: Session) -> dict:
    result = {}
    for name in ("alpaca_paper", "alpaca_data", "openrouter"):
        row = db.scalar(select(IntegrationEvent).where(IntegrationEvent.integration == name).order_by(IntegrationEvent.created_at.desc(), IntegrationEvent.id.desc()).limit(1))
        result[name] = {"status": row.status, "message": row.message, "checked_at": _dt_iso(row.created_at)} if row else {"status": "pending", "message": "Integração não executada.", "checked_at": None}
    return result


def _terminal_control(db: Session) -> TerminalControl:
    control = db.get(TerminalControl, 1)
    if control is None:
        control = TerminalControl(id=1, monitor_enabled=False, jev_enabled=False, status="stopped")
        db.add(control)
        db.commit()
        db.refresh(control)
    return control


@app.on_event("startup")
def startup():
    if engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == settings.admin_username))
        if admin is None:
            db.add(AdminUser(username=settings.admin_username, password_hash=password_hasher.hash(settings.admin_password)))
            db.commit()
        ensure_default_experiment(db)
        _terminal_control(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "application_mode": "DEMO", "external_calls_on_startup": False}


@app.get("/api/terminal")
def market_terminal(db: Session = Depends(get_db), _user: str = Depends(require_user)):
    control = _terminal_control(db)
    samples = db.scalars(select(MarketSample).order_by(MarketSample.observed_at.desc()).limit(300)).all()
    events = db.scalars(select(MarketEvent).order_by(MarketEvent.occurred_at.desc(), MarketEvent.id.desc()).limit(60)).all()
    observations = db.scalars(select(JevObservation).order_by(JevObservation.observed_at.desc(), JevObservation.id.desc()).limit(30)).all()
    latest = samples[0] if samples else None
    return {
        "configuration": {
            "market_configured": market_address_is_valid(settings.kuru_market_address),
            "market_address_hint": (settings.kuru_market_address[:6] + "…" + settings.kuru_market_address[-4:]) if market_address_is_valid(settings.kuru_market_address) else None,
            "symbol": settings.kuru_symbol,
            "chain_id": settings.monad_chain_id,
            "rpc_configured": bool(settings.monad_rpc_url.startswith("https://")),
            "jev_configured": bool(settings.openrouter_api_key and settings.jev_model and "latest" not in settings.jev_model.lower()),
            "jev_model": settings.jev_model,
            "ai_call_budget_usd": str(settings.ai_call_budget_usd),
            "ai_daily_budget_usd": str(settings.ai_daily_budget_usd),
            "jev_interval_seconds": max(30, settings.terminal_jev_interval_seconds),
        },
        "control": {
            "monitor_enabled": control.monitor_enabled,
            "jev_enabled": control.jev_enabled,
            "status": control.status,
            "last_error": control.last_error,
            "last_block_number": control.last_block_number,
            "last_sample_at": _dt_iso(control.last_sample_at),
            "last_jev_at": _dt_iso(control.last_jev_at),
        },
        "market": None if latest is None else {
            "symbol": latest.symbol, "best_bid": str(latest.best_bid), "best_ask": str(latest.best_ask),
            "mid_price": str(latest.mid_price), "spread_bps": str(latest.spread_bps),
            "block_number": latest.block_number, "observed_at": _dt_iso(latest.observed_at),
        },
        "samples": [{"at": _dt_iso(row.observed_at), "mid_price": str(row.mid_price), "best_bid": str(row.best_bid),
                      "best_ask": str(row.best_ask), "spread_bps": str(row.spread_bps)} for row in reversed(samples)],
        "events": [{"at": _dt_iso(row.occurred_at), "side": row.side, "price": str(row.price),
                     "size": None if row.size is None else str(row.size), "tx_hash": row.tx_hash} for row in events],
        "jev_observations": [{"at": _dt_iso(row.observed_at), "status": row.status, "model": row.model,
                              "result": row.result_json, "message": row.message, "cost_usd": None if row.cost_usd is None else str(row.cost_usd),
                              "cost_status": row.cost_status, "latency_ms": row.latency_ms} for row in observations],
        "safety": {"orders_enabled": False, "transaction_signing": False, "mode": "read_only_shadow"},
    }


@app.post("/api/terminal/control")
def market_terminal_control(body: TerminalControlBody, request: Request,
                            x_csrf_token: Optional[str] = Header(default=None), db: Session = Depends(get_db),
                            _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    control = _terminal_control(db)
    if body.action == "start_monitor":
        if not market_address_is_valid(settings.kuru_market_address):
            raise HTTPException(status_code=409, detail="Configure KURU_MARKET_ADDRESS com o endereço MON/USDC da Kuru no EasyPanel antes de iniciar.")
        if not settings.monad_rpc_url.startswith("https://"):
            raise HTTPException(status_code=409, detail="Configure um endpoint HTTPS da Monad em MONAD_RPC_URL.")
        if not settings.kuru_ws_url.startswith("wss://"):
            raise HTTPException(status_code=409, detail="Configure um endpoint WSS seguro em KURU_WS_URL.")
        control.monitor_enabled = True
        control.status = "starting"
        control.last_error = None
    elif body.action == "stop_monitor":
        control.monitor_enabled = False
        control.jev_enabled = False
        control.status = "stopped"
        control.last_error = None
    elif body.action == "enable_jev":
        if not control.monitor_enabled:
            raise HTTPException(status_code=409, detail="Inicie primeiro o monitor de mercado.")
        if not settings.openrouter_api_key:
            raise HTTPException(status_code=409, detail="Configure OPENROUTER_API_KEY no EasyPanel antes de habilitar o Jev.")
        if not settings.jev_model or "latest" in settings.jev_model.lower():
            raise HTTPException(status_code=409, detail="Configure em JEV_MODEL um identificador de versão fixa.")
        control.jev_enabled = True
        control.last_error = None
    else:
        control.jev_enabled = False
    control.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"monitor_enabled": control.monitor_enabled, "jev_enabled": control.jev_enabled, "status": control.status}


@app.get("/api/session")
def session_state(request: Request):
    if not request.session.get("username"):
        return {"authenticated": False}
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return {"authenticated": True, "username": request.session["username"], "csrf_token": token}


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    remote = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = login_attempts[remote]
    while attempts and now - attempts[0] > 60:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde um minuto.")
    attempts.append(now)
    user = db.scalar(select(AdminUser).where(AdminUser.username == body.username))
    valid = bool(user and password_hasher.verify(body.password, user.password_hash))
    if not valid:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    request.session.clear()
    csrf = secrets.token_urlsafe(32)
    request.session.update({"username": user.username, "csrf_token": csrf})
    return {"authenticated": True, "username": user.username, "csrf_token": csrf}


@app.post("/api/auth/logout")
def logout(request: Request, x_csrf_token: Optional[str] = Header(default=None), _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/dashboard")
def dashboard(experiment_id: Optional[str] = None, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    experiment = db.get(Experiment, experiment_id) if experiment_id else db.scalar(select(Experiment).where(Experiment.mode == "DEMO").order_by(Experiment.created_at.desc()).limit(1))
    if experiment and experiment.mode != "DEMO":
        raise HTTPException(status_code=409, detail="Este painel mostra somente experimentos do mesmo modo.")
    if not experiment:
        if experiment_id:
            raise HTTPException(status_code=404, detail="Experimento não encontrado.")
        experiment = ensure_default_experiment(db)
    latest_snapshot = db.scalar(select(Snapshot).where(Snapshot.experiment_id == experiment.id).order_by(Snapshot.cycle_index.desc()).limit(1))
    decisions = db.scalars(select(Decision).where(Decision.experiment_id == experiment.id, Decision.mode == "DEMO").order_by(Decision.id.desc()).limit(12)).all()
    return {
        "banner": "DEMONSTRAÇÃO — dados e decisões sintéticos",
        "mode": experiment.mode,
        "experiment": {"id": experiment.id, "name": experiment.name, "status": experiment.status,
                       "entries_paused": experiment.entries_paused, "config_hash": experiment.config_hash,
                       "next_bar_index": experiment.next_bar_index, "created_at": _dt_iso(experiment.created_at)},
        "snapshot": None if not latest_snapshot else {"cycle_id": latest_snapshot.cycle_id, "cycle_index": latest_snapshot.cycle_index,
                      "cutoff_at": _dt_iso(latest_snapshot.cutoff_at), "source": latest_snapshot.source,
                      "hash": latest_snapshot.content_hash, "synthetic": True},
        "arms": _experiment_metrics(db, experiment),
        "decisions": [{"id": row.id, "cycle_id": row.cycle_id, "snapshot_id": row.snapshot_id,
                      "arm": row.arm, "candidate": row.candidate, "action": row.action,
                      "outcome": row.outcome, "reason_code": row.reason_code, "reason": row.reason,
                      "filter_result": row.filter_result, "evidence_ids": row.evidence_ids,
                      "created_at": _dt_iso(row.created_at)} for row in decisions],
        "integrations": _latest_integration_states(db),
        "timezone": "America/Sao_Paulo",
        "limitations": ["A DEMO usa preços, notícias e classificações sintéticos e fixos.",
                        "Amostra DEMO não mede desempenho de mercado nem valida estratégia.",
                        "O experimento não isola IA generativa sem JEV."],
    }


@app.get("/api/experiments")
def experiments(db: Session = Depends(get_db), _user: str = Depends(require_user)):
    rows = db.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all()
    return [{"id": row.id, "name": row.name, "mode": row.mode, "status": row.status,
             "entries_paused": row.entries_paused, "config_hash": row.config_hash,
             "created_at": _dt_iso(row.created_at), "ended_at": _dt_iso(row.ended_at)} for row in rows]


@app.post("/api/experiments")
def new_experiment(body: ExperimentBody, request: Request, x_csrf_token: Optional[str] = Header(default=None),
                   db: Session = Depends(get_db), _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    row = create_demo_experiment(db, body.name.strip())
    return {"id": row.id, "mode": row.mode, "status": row.status, "config_hash": row.config_hash}


@app.post("/api/experiments/{experiment_id}/{action}")
def experiment_action(experiment_id: str, action: Literal["start", "pause", "stop", "cycle"], request: Request,
                      x_csrf_token: Optional[str] = Header(default=None), db: Session = Depends(get_db),
                      _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    experiment = _find_experiment(db, experiment_id)
    try:
        if action == "cycle":
            result = run_demo_cycle(db, experiment)
        else:
            result = set_demo_status(db, experiment, action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"result": result, "experiment": {"id": experiment.id, "status": experiment.status, "entries_paused": experiment.entries_paused}}


@app.get("/api/decisions")
def decisions(experiment_id: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    query = select(Decision).where(Decision.mode == "DEMO").order_by(Decision.id.desc()).limit(min(max(limit, 1), 500))
    if experiment_id:
        query = query.where(Decision.experiment_id == experiment_id)
    rows = db.scalars(query).all()
    result = []
    for row in rows:
        snapshot = db.get(Snapshot, row.snapshot_id)
        news = db.scalars(select(NewsVersion).where(NewsVersion.snapshot_id == row.snapshot_id)).all()
        intents = db.scalars(select(OrderIntent).where(OrderIntent.experiment_id == row.experiment_id, OrderIntent.cycle_id == row.cycle_id, OrderIntent.arm == row.arm)).all()
        result.append({"id": row.id, "experiment_id": row.experiment_id, "cycle_id": row.cycle_id,
            "snapshot_id": row.snapshot_id, "snapshot_hash": snapshot.content_hash if snapshot else None,
            "arm": row.arm, "candidate": row.candidate, "action": row.action, "outcome": row.outcome,
            "reason_code": row.reason_code, "reason": row.reason, "filter_result": row.filter_result,
            "evidence_ids": row.evidence_ids, "latency_ms": row.latency_ms, "created_at": _dt_iso(row.created_at),
            "sources": [{"article_id": item.article_id, "source": item.source, "title": item.title,
                         "summary": item.summary, "content_hash": item.content_hash, "synthetic": item.synthetic,
                         "created_at": _dt_iso(item.created_at), "updated_at": _dt_iso(item.updated_at), "first_seen_at": _dt_iso(item.first_seen_at)} for item in news],
            "orders": [{"client_order_id": item.client_order_id, "side": item.side, "status": item.status,
                        "quantity": str(item.quantity), "notional_usd": str(item.notional_usd), "mode": item.mode,
                        "fills": [{"quantity": str(fill.quantity), "price": str(fill.price), "fee_amount": None if fill.fee_amount is None else str(fill.fee_amount), "occurred_at": _dt_iso(fill.occurred_at)} for fill in db.scalars(select(Fill).where(Fill.order_intent_id == item.id)).all()]} for item in intents]
        })
    return result


@app.get("/api/integrations")
def integrations(db: Session = Depends(get_db), _user: str = Depends(require_user)):
    alpaca_a = bool(settings.alpaca_paper_a_key_id and settings.alpaca_paper_a_secret_key)
    alpaca_b = bool(settings.alpaca_paper_b_key_id and settings.alpaca_paper_b_secret_key)
    alpaca_c = bool(settings.alpaca_paper_c_key_id and settings.alpaca_paper_c_secret_key)
    data_ready = bool(settings.alpaca_data_key_id and settings.alpaca_data_secret_key)
    return {
        **_latest_integration_states(db),
        "configuration": {
            "alpaca_paper_accounts_configured": {"A": alpaca_a, "B": alpaca_b, "C": alpaca_c},
            "alpaca_data_configured": data_ready,
            "openrouter_configured": bool(settings.openrouter_api_key),
            "openrouter_model_configured": bool(settings.openrouter_llm_model),
            "jev_model": settings.jev_model,
            "status": "pending" if not all((alpaca_a, alpaca_b, alpaca_c, data_ready, settings.openrouter_api_key, settings.openrouter_llm_model)) else "configured",
        },
        "capabilities": {"alpaca_orders_only_paper": True, "order_origin": "https://paper-api.alpaca.markets", "alpaca_data_read_only": True,
                         "model_tools": False, "external_calls_run_automatically": False},
    }


@app.post("/api/integrations/alpaca/preflight")
async def alpaca_preflight(request: Request, x_csrf_token: Optional[str] = Header(default=None), db: Session = Depends(get_db), _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    creds = [("A", settings.alpaca_paper_a_key_id, settings.alpaca_paper_a_secret_key),
             ("B", settings.alpaca_paper_b_key_id, settings.alpaca_paper_b_secret_key),
             ("C", settings.alpaca_paper_c_key_id, settings.alpaca_paper_c_secret_key)]
    if any(not key or not secret for _, key, secret in creds):
        result = {"ready": False, "reason": "Configuração pendente: são necessárias três credenciais paper independentes.", "accounts": []}
        integration_event(db, "alpaca_paper", "pending", result["reason"])
        return result
    try:
        result = await paper_preflight(creds)
        integration_event(db, "alpaca_paper", "ready" if result["ready"] else "blocked", result["reason"],
                          {"accounts": result.get("accounts", [])})
        return result
    except (IntegrationError, ValueError):
        reason = "Preflight interrompido; confira credenciais, elegibilidade e acesso paper no painel de integrações."
        integration_event(db, "alpaca_paper", "unavailable", reason)
        return {"ready": False, "reason": reason, "accounts": []}


@app.post("/api/integrations/openrouter/validate")
async def openrouter_validate(request: Request, x_csrf_token: Optional[str] = Header(default=None), db: Session = Depends(get_db), _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    if not settings.openrouter_api_key or not settings.openrouter_llm_model:
        reason = "Configuração pendente: defina OPENROUTER_API_KEY e um ID fixo em OPENROUTER_LLM_MODEL."
        integration_event(db, "openrouter", "pending", reason)
        return {"ready": False, "reason": reason}
    try:
        client = OpenRouterClient(settings.openrouter_api_key)
        result = await client.validate_structured_model(settings.openrouter_llm_model)
        integration_event(db, "openrouter", "ready", "Modelo com saída estruturada disponível; nenhuma chamada generativa foi feita.", result)
        return {"ready": True, "reason": "Modelo e capacidade de saída estruturada verificados; nenhum prompt foi enviado.", **result}
    except ModelIntegrationError as exc:
        integration_event(db, "openrouter", "unavailable", str(exc))
        return {"ready": False, "reason": str(exc)}


@app.post("/api/integrations/alpaca/data-check")
async def alpaca_data_check(request: Request, x_csrf_token: Optional[str] = Header(default=None), db: Session = Depends(get_db), _user: str = Depends(require_user)):
    require_csrf(request, x_csrf_token)
    if not settings.alpaca_data_key_id or not settings.alpaca_data_secret_key:
        reason = "Configuração pendente: configure credenciais de leitura de dados autorizadas."
        integration_event(db, "alpaca_data", "pending", reason)
        return {"ready": False, "reason": reason}
    try:
        client = AlpacaDataClient(settings.alpaca_data_key_id, settings.alpaca_data_secret_key)
        end = datetime.now(timezone.utc) - timedelta(hours=1)
        bars = await client.crypto_bars("BTC/USD", end - timedelta(hours=2), end)
        integration_event(db, "alpaca_data", "ready", "Consulta de leitura de candles concluída.", {"closed_bars_returned": len(bars)})
        return {"ready": True, "reason": "Consulta somente de leitura concluída.", "closed_bars_returned": len(bars), "source": "Alpaca market data"}
    except (IntegrationError, ValueError):
        reason = "A consulta de dados não foi concluída; confira permissão e atraso do feed."
        integration_event(db, "alpaca_data", "unavailable", reason)
        return {"ready": False, "reason": reason}


@app.get("/api/export")
def export_data(format: Literal["json", "csv"] = "json", experiment_id: Optional[str] = None,
                db: Session = Depends(get_db), _user: str = Depends(require_user)):
    exp = _find_experiment(db, experiment_id) if experiment_id else db.scalar(select(Experiment).where(Experiment.mode == "DEMO").order_by(Experiment.created_at.desc()).limit(1))
    if exp is None:
        raise HTTPException(status_code=404, detail="Experimento não encontrado.")
    rows = db.scalars(select(Decision).where(Decision.experiment_id == exp.id, Decision.mode == "DEMO").order_by(Decision.id.asc())).all()
    safe_rows = [{"mode": row.mode, "experiment_id": row.experiment_id, "cycle_id": row.cycle_id,
                  "snapshot_id": row.snapshot_id, "arm": row.arm, "candidate": row.candidate,
                  "action": row.action, "outcome": row.outcome, "reason_code": row.reason_code,
                  "reason": row.reason, "filter_result": row.filter_result,
                  "evidence_ids": row.evidence_ids, "created_at": _dt_iso(row.created_at)} for row in rows]
    if format == "csv":
        output = io.StringIO()
        columns = list(safe_rows[0].keys()) if safe_rows else ["mode", "experiment_id", "cycle_id", "arm", "candidate", "action", "outcome"]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(safe_rows)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="paperlab-{exp.id}.csv"'})
    return {"mode": "DEMO", "synthetic": True, "experiment_id": exp.id, "config_hash": exp.config_hash,
            "exported_at": datetime.now(timezone.utc).isoformat(), "decisions": safe_rows}


@app.get("/api/experiment/{experiment_id}/configuration")
def experiment_configuration(experiment_id: str, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    experiment = _find_experiment(db, experiment_id)
    return {"mode": experiment.mode, "config_hash": experiment.config_hash, "configuration": experiment.config_json,
            "immutable": True, "created_at": _dt_iso(experiment.created_at)}
