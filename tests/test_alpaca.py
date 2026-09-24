from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

import paperlab.alpaca as alpaca
from paperlab.alpaca import AlpacaDataClient, AlpacaPaperClient, IntegrationError, find_hourly_gaps, normalize_order_status, paper_preflight, validate_paper_origin


@pytest.mark.parametrize("origin", [
    "https://api.alpaca.markets", "https://paper-api.alpaca.markets.evil", "http://paper-api.alpaca.markets",
    "https://paper-api.alpaca.markets:443", "https://user@paper-api.alpaca.markets", "https://paper-api.alpaca.markets/path",
])
def test_non_paper_order_origins_are_rejected_before_request(origin):
    with pytest.raises(ValueError):
        validate_paper_origin(origin)
    with pytest.raises(ValueError):
        AlpacaPaperClient("key", "secret", base_url=origin)


def test_exact_paper_origin_is_allowed():
    assert validate_paper_origin("https://paper-api.alpaca.markets") == "https://paper-api.alpaca.markets"


@pytest.mark.asyncio
async def test_timeout_is_looked_up_by_id_and_never_blindly_resent():
    seen = []
    async def handler(request):
        seen.append((request.method, str(request.url)))
        if request.method == "POST":
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(404, json={"message": "not found"})
    client = AlpacaPaperClient("key", "secret", transport=httpx.MockTransport(handler))
    result = await client.submit_and_reconcile(symbol="BTC/USD", side="buy", notional_usd=Decimal("100"), client_order_id="pl-test")
    assert result["normalized_status"] == "unknown"
    assert result["entry_pause_required"] is True
    assert [method for method, _ in seen] == ["POST", "GET"]
    assert all("paper-api.alpaca.markets" in url for _, url in seen)


@pytest.mark.asyncio
async def test_redirect_is_blocked_without_following():
    seen = []
    async def handler(request):
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://example.com/"})
    client = AlpacaPaperClient("key", "secret", transport=httpx.MockTransport(handler))
    with pytest.raises(IntegrationError, match="redirecionar"):
        await client.account()
    assert seen == ["paper-api.alpaca.markets"]


@pytest.mark.asyncio
async def test_data_client_removes_open_bars_and_deduplicates_and_sorts():
    async def handler(request):
        assert request.url.host == "data.alpaca.markets"
        return httpx.Response(200, json={"bars": {"BTC/USD": [
            {"t": "2024-01-01T01:00:00Z", "c": 2},
            {"t": "2024-01-01T00:00:00Z", "c": 1},
            {"t": "2024-01-01T00:00:00Z", "c": 1},
        ]}, "next_page_token": None})
    client = AlpacaDataClient("read-key", "read-secret", transport=httpx.MockTransport(handler))
    rows = await client.crypto_bars("BTC/USD", datetime(2023, 12, 31, tzinfo=timezone.utc), datetime(2024, 1, 1, 1, 30, tzinfo=timezone.utc))
    assert [row["t"] for row in rows] == ["2024-01-01T00:00:00Z"]


def test_hourly_gaps_are_reported():
    rows = [{"t": "2024-01-01T00:00:00Z"}, {"t": "2024-01-01T02:00:00Z"}]
    assert find_hourly_gaps(rows) == [(rows[0]["t"], rows[1]["t"])]


def test_order_status_mapping_handles_partial_and_unknown():
    assert normalize_order_status("partially_filled") == "partially_filled"
    assert normalize_order_status("filled") == "filled"
    assert normalize_order_status("some_new_value") == "unknown"


@pytest.mark.asyncio
async def test_preflight_rejects_three_keys_for_same_account(monkeypatch):
    class FakeClient:
        def __init__(self, key, secret): pass
        async def account(self): return {"id": "same", "status": "ACTIVE", "trading_blocked": False, "equity": "10000", "cash": "10000"}
        async def positions(self): return []
        async def orders(self, status="open"): return []
        async def assets(self, asset_class="crypto"): return [{"symbol": "BTC/USD", "status": "active", "tradable": True,
            "min_order_size": "0.0001", "min_trade_increment": "0.0001", "price_increment": "0.01"}]
    monkeypatch.setattr(alpaca, "AlpacaPaperClient", FakeClient)
    result = await paper_preflight([(arm, f"key-{arm}", f"secret-{arm}") for arm in ("A", "B", "C")])
    assert result["ready"] is False
    assert "mesma conta" in result["reason"]


@pytest.mark.asyncio
async def test_preflight_requires_equivalent_cash_and_returns_btc_constraints(monkeypatch):
    class FakeClient:
        def __init__(self, key, secret): self.account_id = key
        async def account(self):
            cash = "9999" if self.account_id == "key-B" else "10000"
            return {"id": self.account_id, "status": "ACTIVE", "trading_blocked": False, "equity": "10000", "cash": cash}
        async def positions(self): return []
        async def orders(self, status="open"): return []
        async def assets(self, asset_class="crypto"): return [{"symbol": "BTC/USD", "status": "active", "tradable": True,
            "min_order_size": "0.0001", "min_trade_increment": "0.0001", "price_increment": "0.01"}]
    monkeypatch.setattr(alpaca, "AlpacaPaperClient", FakeClient)
    creds = [(arm, f"key-{arm}", f"secret-{arm}") for arm in ("A", "B", "C")]
    result = await paper_preflight(creds)
    assert result["ready"] is False
    assert "caixa" in result["reason"]

    async def equivalent_account(self):
        return {"id": self.account_id, "status": "ACTIVE", "trading_blocked": False, "equity": "10000", "cash": "10000"}
    FakeClient.account = equivalent_account
    result = await paper_preflight(creds)
    assert result["ready"] is True
    assert result["accounts"][0]["btc_usd_constraints"] == {
        "min_order_size": "0.0001", "min_trade_increment": "0.0001", "price_increment": "0.01",
    }


@pytest.mark.asyncio
async def test_news_no_results_is_healthy_empty_but_feed_error_is_not():
    async def empty_handler(request):
        return httpx.Response(200, json={"news": [], "next_page_token": None})
    client = AlpacaDataClient("data-key", "data-secret", transport=httpx.MockTransport(empty_handler))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert await client.news("BTC/USD", start, start) == []
    async def failed_handler(request): return httpx.Response(403, json={})
    failed = AlpacaDataClient("data-key", "data-secret", transport=httpx.MockTransport(failed_handler))
    with pytest.raises(IntegrationError):
        await failed.news("BTC/USD", start, start)
