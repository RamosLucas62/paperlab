from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
import math
from typing import Iterable


ZERO = Decimal("0")
CENT = Decimal("0.01")
FEE_RATE = Decimal("0.0025")
DEMO_SEED = 271828


@dataclass(frozen=True)
class BarData:
    symbol: str
    bar_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


def as_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def demo_bar(index: int) -> BarData:
    # Synthetic, repeatable price path. The floats are used only to draw fixture
    # values; all domain amounts are converted to Decimal before calculations.
    close_f = 50_000 + 25 * index + 1_500 * math.sin(index / 8) + 300 * math.sin(index / 3)
    previous_f = 50_000 + 25 * max(0, index - 1) + 1_500 * math.sin(max(0, index - 1) / 8) + 300 * math.sin(max(0, index - 1) / 3)
    close = Decimal(str(round(close_f, 6)))
    open_price = Decimal(str(round(previous_f, 6)))
    wick = Decimal("21.125")
    at = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    return BarData("BTC/USD", at, open_price, max(open_price, close) + wick, min(open_price, close) - wick, close, Decimal("0.1375"), "PaperLab DEMO synthetic generator v1")


def moving_average(values: Iterable[Decimal], period: int) -> Decimal | None:
    vals = list(values)
    if len(vals) < period:
        return None
    return sum(vals[-period:], ZERO) / Decimal(period)


def crossover(closes: list[Decimal], fast: int = 20, slow: int = 50) -> str:
    """Return BUY/SELL/HOLD from two closed-bar windows and their predecessor."""
    if len(closes) < slow + 1:
        return "HOLD"
    fast_now = moving_average(closes, fast)
    slow_now = moving_average(closes, slow)
    fast_prev = moving_average(closes[:-1], fast)
    slow_prev = moving_average(closes[:-1], slow)
    if fast_prev is None or slow_prev is None or fast_now is None or slow_now is None:
        return "HOLD"
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "BUY"
    if fast_prev >= slow_prev and fast_now < slow_now:
        return "SELL"
    return "HOLD"


def stable_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def deterministic_order_id(experiment_id: str, arm: str, cycle_index: int, action: str) -> str:
    raw = f"{experiment_id}:{arm}:{cycle_index}:{action}".encode()
    return "pl-" + hashlib.sha256(raw).hexdigest()[:42]


def quantize_crypto_qty(notional_usd: Decimal, price: Decimal) -> Decimal:
    return (notional_usd / price).quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN)
