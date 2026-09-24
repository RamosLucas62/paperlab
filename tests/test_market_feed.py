from decimal import Decimal

from paperlab.market_feed import decode_orderbook_message, market_address_is_valid, terminal_jev_questions


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


def test_market_address_and_observation_questions_are_explicit():
    assert market_address_is_valid("0x" + "a" * 40)
    assert not market_address_is_valid("0x123")
    questions = terminal_jev_questions("MON/USDC")
    assert set(questions) == {"stance", "relevance", "risk", "sufficiency"}
    assert set(questions["stance"]["criteria"]) == {"buy", "sell", "hold"}
    assert "non-executable shadow label" in questions["stance"]["instructions"]
    assert "MON/USDC" in questions["relevance"]["instructions"]
