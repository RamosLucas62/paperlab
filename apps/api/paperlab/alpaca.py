"""Alpaca paper-trading and read-only data adapters.

The trading origin is deliberately a literal constant. No caller, browser field,
environment variable, or model output can select an order endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

import httpx


PAPER_TRADING_ORIGIN = "https://paper-api.alpaca.markets"
DATA_ORIGIN = "https://data.alpaca.markets"
CRYPTO_LOCATION = "us"


class IntegrationError(RuntimeError):
    """A safe, user-facing integration error without response secrets."""


def validate_paper_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if (
        origin != PAPER_TRADING_ORIGIN
        or parts.scheme != "https"
        or parts.hostname != "paper-api.alpaca.markets"
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Ordens só podem usar a origem HTTPS oficial de paper trading da Alpaca.")
    return PAPER_TRADING_ORIGIN


class AlpacaPaperClient:
    def __init__(self, key_id: str, secret_key: str, *, base_url: str = PAPER_TRADING_ORIGIN,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = validate_paper_origin(base_url)
        if not key_id or not secret_key:
            raise ValueError("Credenciais paper ausentes.")
        self._headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key}
        self._transport = transport

    async def _request(self, method: str, path: str, *, params=None, body=None):
        validate_paper_origin(self.base_url)
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers, timeout=15.0,
            verify=True, follow_redirects=False, trust_env=False, transport=self._transport,
        ) as client:
            try:
                response = await client.request(method, path, params=params, json=body)
                if 300 <= response.status_code < 400:
                    raise IntegrationError("A Alpaca tentou redirecionar a requisição; a resposta foi bloqueada.")
                response.raise_for_status()
                return response.json() if response.content else None
            except IntegrationError:
                raise
            except httpx.HTTPStatusError as exc:
                raise IntegrationError(f"A Alpaca respondeu com HTTP {exc.response.status_code}.") from None
            except httpx.HTTPError:
                raise IntegrationError("Não foi possível concluir a requisição segura à Alpaca.") from None

    async def account(self) -> dict:
        return await self._request("GET", "/v2/account")

    async def assets(self, asset_class: str = "crypto") -> list[dict]:
        return await self._request("GET", "/v2/assets", params={"asset_class": asset_class})

    async def positions(self) -> list[dict]:
        return await self._request("GET", "/v2/positions")

    async def orders(self, status: str = "open", limit: int = 500) -> list[dict]:
        return await self._request("GET", "/v2/orders", params={"status": status, "limit": limit, "direction": "desc"})

    async def executions(self, after: datetime | None = None) -> list[dict]:
        params = {"direction": "desc", "page_size": 100}
        if after:
            params["after"] = after.astimezone(timezone.utc).isoformat()
        return await self._request("GET", "/v2/account/activities/FILL", params=params)

    async def order_by_client_id(self, client_order_id: str) -> dict:
        return await self._request("GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_order_id})

    async def submit_market_crypto_order(self, *, symbol: str, side: str, notional_usd: Decimal, client_order_id: str) -> dict:
        if symbol not in {"BTC/USD", "ETH/USD"}:
            raise ValueError("O MVP permite BTC/USD e ETH/USD apenas.")
        if side not in {"buy", "sell"}:
            raise ValueError("Lado de ordem inválido.")
        if notional_usd <= 0 or notional_usd > Decimal("100"):
            raise ValueError("O valor da ordem excede o limite fixo do MVP.")
        if len(client_order_id) > 48:
            raise ValueError("client_order_id excede o limite documentado pela Alpaca.")
        return await self._request("POST", "/v2/orders", body={
            "symbol": symbol, "notional": format(notional_usd, "f"), "side": side,
            "type": "market", "time_in_force": "gtc", "client_order_id": client_order_id,
        })

    async def submit_market_crypto_qty_order(self, *, symbol: str, side: str, quantity: Decimal,
                                             client_order_id: str, min_order_size: Decimal,
                                             trade_increment: Decimal) -> dict:
        if symbol not in {"BTC/USD", "ETH/USD"} or side not in {"buy", "sell"}:
            raise ValueError("Símbolo ou lado não habilitado para este MVP.")
        if quantity < min_order_size or trade_increment <= 0 or quantity % trade_increment != 0:
            raise ValueError("A quantidade não respeita o mínimo ou incremento publicado para o ativo.")
        if len(client_order_id) > 48:
            raise ValueError("client_order_id excede o limite documentado pela Alpaca.")
        return await self._request("POST", "/v2/orders", body={
            "symbol": symbol, "qty": format(quantity, "f"), "side": side,
            "type": "market", "time_in_force": "gtc", "client_order_id": client_order_id,
        })

    async def submit_and_reconcile(self, *, symbol: str, side: str, notional_usd: Decimal,
                                   client_order_id: str, quantity: Decimal | None = None,
                                   min_order_size: Decimal | None = None,
                                   trade_increment: Decimal | None = None) -> dict:
        """Never blindly resend after a timeout; look up the deterministic ID once."""
        try:
            if quantity is None:
                response = await self.submit_market_crypto_order(symbol=symbol, side=side,
                    notional_usd=notional_usd, client_order_id=client_order_id)
            else:
                if min_order_size is None or trade_increment is None:
                    raise ValueError("Restrições publicadas do ativo são obrigatórias para ordens por quantidade.")
                response = await self.submit_market_crypto_qty_order(symbol=symbol, side=side,
                    quantity=quantity, client_order_id=client_order_id,
                    min_order_size=min_order_size, trade_increment=trade_increment)
            return {**response, "normalized_status": normalize_order_status(response.get("status"))}
        except IntegrationError:
            try:
                response = await self.order_by_client_id(client_order_id)
                return {**response, "normalized_status": normalize_order_status(response.get("status")),
                        "reconciled_after_submission_error": True}
            except IntegrationError:
                return {"client_order_id": client_order_id, "status": "unknown",
                        "normalized_status": "unknown", "entry_pause_required": True}

    async def cancel_order(self, order_id: str) -> None:
        await self._request("DELETE", f"/v2/orders/{order_id}")


class AlpacaDataClient:
    """Read-only market-data/news client; order credentials never enter this adapter."""

    def __init__(self, key_id: str, secret_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        if not key_id or not secret_key:
            raise ValueError("Credenciais de leitura de dados ausentes.")
        self._headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key}
        self._transport = transport

    async def _get(self, path: str, params: dict):
        async with httpx.AsyncClient(
            base_url=DATA_ORIGIN, headers=self._headers, timeout=20.0, verify=True,
            follow_redirects=False, trust_env=False, transport=self._transport,
        ) as client:
            try:
                response = await client.get(path, params=params)
                if 300 <= response.status_code < 400:
                    raise IntegrationError("A Alpaca tentou redirecionar o cliente de dados; a resposta foi bloqueada.")
                response.raise_for_status()
                return response.json()
            except IntegrationError:
                raise
            except httpx.HTTPStatusError as exc:
                raise IntegrationError(f"A Alpaca respondeu com HTTP {exc.response.status_code}.") from None
            except httpx.HTTPError:
                raise IntegrationError("Não foi possível consultar os dados da Alpaca.") from None

    async def crypto_bars(self, symbol: str, start: datetime, end: datetime) -> list[dict]:
        if symbol not in {"BTC/USD", "ETH/USD"}:
            raise ValueError("Símbolo de dados não habilitado neste MVP.")
        token = None
        bars: list[dict] = []
        while True:
            params = {"symbols": symbol, "timeframe": "1Hour", "start": start.astimezone(timezone.utc).isoformat(),
                      "end": end.astimezone(timezone.utc).isoformat(), "limit": 10000, "sort": "asc"}
            if token:
                params["page_token"] = token
            response = await self._get(f"/v1beta3/crypto/{CRYPTO_LOCATION}/bars", params)
            bars.extend(response.get("bars", {}).get(symbol, []))
            token = response.get("next_page_token")
            if not token:
                break
        unique = {item["t"]: item for item in bars if "t" in item}
        ordered = [unique[key] for key in sorted(unique)]
        closed_before = end.astimezone(timezone.utc)
        return [item for item in ordered if datetime.fromisoformat(item["t"].replace("Z", "+00:00")) + timedelta(hours=1) <= closed_before]

    async def news(self, symbol: str, start: datetime, end: datetime, limit: int = 50) -> list[dict]:
        if symbol == "BTC/USD":
            news_symbol = "BTCUSD"  # Alpaca news uses ticker-style symbols, distinct from order symbols.
        elif symbol == "ETH/USD":
            news_symbol = "ETHUSD"
        else:
            raise ValueError("Símbolo de notícias não habilitado neste MVP.")
        token = None
        articles: list[dict] = []
        while True:
            params = {"symbols": news_symbol, "start": start.astimezone(timezone.utc).isoformat(),
                      "end": end.astimezone(timezone.utc).isoformat(), "limit": min(max(limit, 1), 50),
                      "include_content": "false", "sort": "asc"}
            if token:
                params["page_token"] = token
            response = await self._get("/v1beta1/news", params)
            articles.extend(response.get("news", []))
            token = response.get("next_page_token")
            if not token:
                break
        return articles


@dataclass(frozen=True)
class PaperAccountSummary:
    arm: str
    account_id: str
    status: str
    equity: Decimal
    cash: Decimal
    open_positions: int
    open_orders: int
    min_order_size: str
    min_trade_increment: str
    price_increment: str


async def paper_preflight(credential_sets: list[tuple[str, str, str]]) -> dict:
    """Read-only preflight for three independent paper accounts."""
    if len(credential_sets) != 3 or any(not key or not secret for _, key, secret in credential_sets):
        return {"ready": False, "reason": "São necessárias três credenciais paper completas (A, B e C).", "accounts": []}
    summaries: list[PaperAccountSummary] = []
    for arm, key, secret in credential_sets:
        client = AlpacaPaperClient(key, secret)
        account, positions, open_orders, assets = await _read_account_state(client)
        asset = next((a for a in assets if a.get("symbol") == "BTC/USD"), None)
        if not account.get("id"):
            return {"ready": False, "reason": f"A conta {arm} não retornou um identificador.", "accounts": []}
        if account.get("status") != "ACTIVE" or account.get("trading_blocked"):
            return {"ready": False, "reason": f"A conta {arm} não está disponível para paper trading.", "accounts": []}
        if positions or open_orders:
            return {"ready": False, "reason": f"A conta {arm} tem posições ou ordens anteriores; o PaperLab não as altera.", "accounts": []}
        if not asset or asset.get("status") != "active" or not asset.get("tradable"):
            return {"ready": False, "reason": f"BTC/USD não está ativo e negociável na conta {arm}.", "accounts": []}
        try:
            min_order_size = Decimal(str(asset["min_order_size"]))
            min_trade_increment = Decimal(str(asset["min_trade_increment"]))
            price_increment = Decimal(str(asset["price_increment"]))
        except (KeyError, ArithmeticError, ValueError):
            return {"ready": False, "reason": f"A conta {arm} não publicou as restrições de tamanho e precisão do BTC/USD.", "accounts": []}
        if min_order_size <= 0 or min_trade_increment <= 0 or price_increment <= 0:
            return {"ready": False, "reason": f"As restrições publicadas do BTC/USD na conta {arm} são inválidas.", "accounts": []}
        summaries.append(PaperAccountSummary(arm, str(account["id"]), str(account.get("status")),
            Decimal(str(account.get("equity", "0"))), Decimal(str(account.get("cash", "0"))), len(positions), len(open_orders),
            str(min_order_size), str(min_trade_increment), str(price_increment)))
    ids = [item.account_id for item in summaries]
    if len(set(ids)) != 3:
        return {"ready": False, "reason": "As credenciais A, B e C apontam para a mesma conta; são necessárias três contas distintas.", "accounts": []}
    equities = [item.equity for item in summaries]
    cash_balances = [item.cash for item in summaries]
    if max(equities) - min(equities) > Decimal("0.01") or max(cash_balances) - min(cash_balances) > Decimal("0.01"):
        return {"ready": False, "reason": "Os saldos iniciais de caixa ou patrimônio das três contas não são equivalentes.", "accounts": []}
    return {"ready": True, "reason": "Preflight de leitura concluído; nenhuma ordem foi enviada.", "accounts": [
        {"arm": item.arm, "account_id": item.account_id, "status": item.status, "equity_usd": str(item.equity), "cash_usd": str(item.cash), "open_positions": 0, "open_orders": 0,
         "btc_usd_constraints": {"min_order_size": item.min_order_size, "min_trade_increment": item.min_trade_increment, "price_increment": item.price_increment}}
        for item in summaries
    ]}


async def _read_account_state(client: AlpacaPaperClient):
    account = await client.account()
    positions = await client.positions()
    orders = await client.orders(status="open")
    assets = await client.assets("crypto")
    return account, positions, orders, assets


def normalize_order_status(status: str | None) -> str:
    return {
        "new": "accepted", "accepted": "accepted", "accepted_for_bidding": "accepted",
        "pending_new": "pending", "pending_cancel": "pending", "pending_replace": "pending",
        "partially_filled": "partially_filled", "filled": "filled", "canceled": "canceled",
        "rejected": "rejected", "expired": "rejected", "done_for_day": "accepted",
    }.get((status or "").lower(), "unknown")


def find_hourly_gaps(bars: list[dict]) -> list[tuple[str, str]]:
    ordered = sorted({item["t"]: item for item in bars if item.get("t")}.values(), key=lambda item: item["t"])
    gaps: list[tuple[str, str]] = []
    for before, after in zip(ordered, ordered[1:]):
        left = datetime.fromisoformat(before["t"].replace("Z", "+00:00"))
        right = datetime.fromisoformat(after["t"].replace("Z", "+00:00"))
        if right - left > timedelta(hours=1):
            gaps.append((before["t"], after["t"]))
    return gaps
