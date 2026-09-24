"""Read-only Kuru order-book message decoding helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


PRICE_SCALE = Decimal(10) ** 18


def market_address_is_valid(value: str) -> bool:
    return len(value) == 42 and value.startswith("0x") and all(ch in "0123456789abcdefABCDEF" for ch in value[2:])


@dataclass(frozen=True)
class MarketTrade:
    event_key: str
    occurred_at: datetime
    side: str
    price: Decimal
    size: Decimal | None
    tx_hash: str | None


@dataclass(frozen=True)
class BookUpdate:
    best_bid: Decimal | None
    best_ask: Decimal | None
    trades: tuple[MarketTrade, ...]
    bid_updated: bool
    ask_updated: bool


def _price(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        text = str(raw).strip()
        value = Decimal(int(text, 16)) if text.lower().startswith("0x") else Decimal(text)
        if not value.is_finite():
            return None
        return value / PRICE_SCALE
    except (InvalidOperation, ValueError):
        return None


def _level_price(level: Any) -> Decimal | None:
    if isinstance(level, dict):
        return _price(level.get("p", level.get("price")))
    if isinstance(level, (list, tuple)) and level:
        return _price(level[0])
    return _price(level)


def _top(levels: Any, *, bids: bool) -> Decimal | None:
    if not isinstance(levels, list):
        return None
    values = [value for level in levels if (value := _level_price(level)) is not None and value > 0]
    if not values:
        return None
    return max(values) if bids else min(values)


def _event_time(raw: Any) -> datetime | None:
    try:
        text = str(raw).strip()
        value = int(text, 16) if text.lower().startswith("0x") else int(text)
        # Kuru event timestamps are milliseconds since epoch.
        if value > 10_000_000_000:
            value //= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def decode_orderbook_message(message: dict[str, Any]) -> BookUpdate:
    """Normalize a Kuru frontendOrderbook snapshot/update without inventing data."""
    payload = message.get("data") if isinstance(message.get("data"), dict) else message
    bid_updated = "b" in payload or "bids" in payload
    ask_updated = "a" in payload or "asks" in payload
    bid = _top(payload.get("b", payload.get("bids")), bids=True) if bid_updated else None
    ask = _top(payload.get("a", payload.get("asks")), bids=False) if ask_updated else None

    raw_events = payload.get("events")
    if raw_events is None and "p" in payload and "ib" in payload:
        raw_events = [payload]
    if not isinstance(raw_events, list):
        raw_events = []

    trades: list[MarketTrade] = []
    for index, event in enumerate(raw_events):
        if not isinstance(event, dict):
            continue
        if str(event.get("e", "")).lower() != "trade":
            continue
        event_price = _price(event.get("p", event.get("price")))
        if event_price is None or event_price <= 0 or event.get("ib") is None:
            continue
        aggressor = event.get("ib")
        if aggressor is True or str(aggressor).lower() in {"1", "true", "buy"}:
            side = "BUY"
        elif aggressor is False or str(aggressor).lower() in {"0", "false", "sell"}:
            side = "SELL"
        else:
            continue
        timestamp = _event_time(event.get("ts", event.get("timestamp")))
        if timestamp is None:
            continue
        tx_hash = next((str(event[key]) for key in ("txHash", "tx_hash", "hash", "th") if event.get(key)), None)
        identity = f"{tx_hash or 'trade'}:{timestamp.isoformat()}:{event_price}:{side}:{index}"
        # Kuru's raw `s` field depends on a market-specific size precision.
        # Only accept an already-normalized `size`; never guess that precision.
        raw_size = event.get("size")
        try:
            size = Decimal(str(raw_size)) if raw_size is not None else None
        except (InvalidOperation, ValueError):
            size = None
        if size is not None and (not size.is_finite() or size <= 0):
            size = None
        trades.append(MarketTrade(
            event_key=str(identity)[:200], occurred_at=timestamp, side=side,
            price=event_price, size=size, tx_hash=tx_hash,
        ))
    return BookUpdate(best_bid=bid, best_ask=ask, trades=tuple(trades), bid_updated=bid_updated, ask_updated=ask_updated)


def terminal_jev_questions(symbol: str) -> dict:
    return {
        "relevance": {
            "type": "choice",
            "instructions": f"Does this read-only {symbol} order-book snapshot contain a usable market observation?",
            "criteria": {
                "relevant": "The bid, ask and spread describe a coherent, current order book.",
                "not_relevant": "The book is missing, stale, crossed, or cannot support this narrow observation.",
            },
        },
        "risk": {
            "type": "choice",
            "instructions": "Does the supplied snapshot show an obvious market-data risk condition that should make an observer pause?",
            "criteria": {
                "risk_event": "The spread is unusually wide, the book is crossed, or the supplied values are internally inconsistent.",
                "no_risk_event": "No such condition is evident from the supplied snapshot alone.",
            },
        },
        "sufficiency": {
            "type": "choice",
            "instructions": "Is the supplied snapshot sufficient for this limited market-quality classification?",
            "criteria": {
                "sufficient": "Bid, ask, midpoint, spread and observation time are all present and consistent.",
                "insufficient_or_ambiguous": "Important values are missing, stale, or ambiguous.",
            },
        },
    }
