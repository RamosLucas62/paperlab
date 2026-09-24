from decimal import Decimal

from paperlab.market_feed import OrderBookState, decode_orderbook_message, market_address_is_valid, terminal_jev_questions


def test_decode_kuru_book_levels_and_trade_without_guessing_raw_size():
    update = decode_orderbook_message({
        "type": "snapshot",
        "data": {
            "b": [["100000000000000000000", "9000000000000000000"], ["99000000000000000000", "1"]],
            "a": [["101000000000000000000", "1"]],
            "events": [{"e": "Trade", "p": "100000000000000000000", "s": "9000000000000000000", "ib": True, "ts": "0x19c9ac0c00", "th": "0xtrade"}, {"e": "OrderCreated", "p": "102000000000000000000", "ib": False, "ts": 1780000000000}],
        },
    })
    assert update.best_bid == Decimal("100")
    assert update.best_ask == Decimal("101")
    assert update.bid_updated and update.ask_updated
    assert update.snapshot
    assert len(update.trades) == 1
    assert update.trades[0].side == "BUY"
    assert update.trades[0].price == Decimal("100")
    assert update.trades[0].size is None
    assert update.trades[0].tx_hash == "0xtrade"


def test_invalid_or_partial_market_messages_do_not_invent_a_book():
    update = decode_orderbook_message({"type": "snapshot", "data": {"b": [["invalid"]], "a": []}})
    assert update.best_bid is None
    assert update.best_ask is None
    assert update.bid_updated and update.ask_updated
    assert not update.trades


def test_incremental_book_updates_preserve_other_levels_and_remove_empty_levels():
    book = OrderBookState()
    initial = decode_orderbook_message({
        "type": "snapshot",
        "data": {
            "b": [["100000000000000000000", "10"], ["99000000000000000000", "8"]],
            "a": [["101000000000000000000", "5"], ["102000000000000000000", "6"]],
        },
    })
    assert book.apply(initial) == (Decimal("100"), Decimal("101"))

    # An incremental change at a worse bid must not replace the existing best level.
    lower_bid_and_remove_best_ask = decode_orderbook_message({
        "type": "update",
        "data": {
            "b": [["99500000000000000000", "3"]],
            "a": [["101000000000000000000", "0"]],
        },
    })
    assert not lower_bid_and_remove_best_ask.snapshot
    assert book.apply(lower_bid_and_remove_best_ask) == (Decimal("100"), Decimal("102"))

    remove_best_bid = decode_orderbook_message({
        "type": "update",
        "data": {"b": [["100000000000000000000", "0"]]},
    })
    assert book.apply(remove_best_bid) == (Decimal("99.5"), Decimal("102"))


def test_successful_subscription_payload_is_a_fresh_snapshot():
    book = OrderBookState()
    book.apply(decode_orderbook_message({
        "type": "snapshot",
        "data": {"b": [["100000000000000000000", "1"]], "a": [["101000000000000000000", "1"]]},
    }))
    subscribed = decode_orderbook_message({
        "type": "subscribed",
        "status": "success",
        "data": {"b": [["99500000000000000000", "2"]], "a": [["102000000000000000000", "2"]]},
    })
    assert subscribed.snapshot
    assert book.apply(subscribed) == (Decimal("99.5"), Decimal("102"))


def test_market_address_and_observation_questions_are_explicit():
    assert market_address_is_valid("0x" + "a" * 40)
    assert not market_address_is_valid("0x123")
    questions = terminal_jev_questions("MON/USDC")
    assert set(questions) == {"stance", "relevance", "risk", "sufficiency"}
    assert set(questions["stance"]["criteria"]) == {"buy", "sell", "hold"}
    assert "non-executable shadow label" in questions["stance"]["instructions"]
    assert "MON/USDC" in questions["relevance"]["instructions"]
