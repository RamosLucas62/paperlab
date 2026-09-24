"""Read-only Kuru order-book message decoding helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]
    snapshot: bool


@dataclass
class OrderBookState:
    """Maintain Kuru's initial snapshot and subsequent price-level updates."""

    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    asks: dict[Decimal, Decimal] = field(default_factory=dict)

    def apply(self, update: BookUpdate) -> tuple[Decimal | None, Decimal | None]:
        if update.snapshot:
            self.bids.clear()
            self.asks.clear()
        self._apply_side(self.bids, update.bids, update.bid_updated, update.snapshot)
        self._apply_side(self.asks, update.asks, update.ask_updated, update.snapshot)
        return (max(self.bids) if self.bids else None, min(self.asks) if self.asks else None)

    @staticmethod
    def _apply_side(
        book: dict[Decimal, Decimal],
        changes: tuple[tuple[Decimal, Decimal], ...],
        updated: bool,
        snapshot: bool,
    ) -> None:
        if not updated:
            return
        if snapshot and not changes:
            book.clear()
            return
        for price, size in changes:
            if size == 0:
                book.pop(price, None)
            elif size > 0:
                book[price] = size


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


def _level_change(level: Any) -> tuple[Decimal, Decimal] | None:
    if isinstance(level, dict):
        raw_price = level.get("p", level.get("price"))
        raw_size = level.get("s", level.get("size"))
    elif isinstance(level, (list, tuple)) and len(level) >= 2:
        raw_price, raw_size = level[0], level[1]
    else:
        return None
    price = _price(raw_price)
    size = _number(raw_size)
    if price is None or price <= 0 or size is None or size < 0:
        return None
    return price, size


def _number(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        text = str(raw).strip()
        value = Decimal(int(text, 16)) if text.lower().startswith("0x") else Decimal(text)
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _top(levels: Any, *, bids: bool) -> Decimal | None:
    if not isinstance(levels, list):
        return None
    values = []
    for level in levels:
        change = _level_change(level)
        if change is not None:
            price, size = change
            if price > 0 and size > 0:
                values.append(price)
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
    raw_bids = payload.get("b", payload.get("bids"))
    raw_asks = payload.get("a", payload.get("asks"))
    bid_updated = "b" in payload or "bids" in payload
    ask_updated = "a" in payload or "asks" in payload
    bids = tuple(change for level in raw_bids if (change := _level_change(level)) is not None) if isinstance(raw_bids, list) else ()
    asks = tuple(change for level in raw_asks if (change := _level_change(level)) is not None) if isinstance(raw_asks, list) else ()
    message_type = str(message.get("type", "")).lower()
    snapshot = message_type == "snapshot" or (
        message_type == "subscribed" and message.get("status") == "success" and isinstance(message.get("data"), dict)
    ) or (not message_type and bid_updated and ask_updated)
    bid = _top(raw_bids, bids=True) if bid_updated else None
    ask = _top(raw_asks, bids=False) if ask_updated else None

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
    return BookUpdate(
        best_bid=bid, best_ask=ask, trades=tuple(trades), bid_updated=bid_updated, ask_updated=ask_updated,
        bids=bids, asks=asks, snapshot=snapshot,
    )


def terminal_jev_questions(symbol: str) -> dict:
    return {
        "stance": {
            "type": "choice",
            "instructions": f"For this read-only observation of {symbol}, classify the current order-book state as BUY, SELL, or HOLD. This is a non-executable shadow label, not a prediction or recommendation.",
            "criteria": {
                "buy": "The supplied snapshot supports a buy-side shadow label.",
                "sell": "The supplied snapshot supports a sell-side shadow label.",
                "hold": "The snapshot is mixed, neutral, or insufficient for a directional label.",
            },
        },
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
