from decimal import Decimal

from paperlab.config import Settings
from paperlab.domain import crossover, demo_bar, deterministic_order_id, moving_average
from paperlab.openrouter import apply_filter_policy, parse_choice, parse_noul, parse_score


def test_strategy_uses_closed_history_and_detects_synthetic_crossovers():
    closes = [demo_bar(index).close for index in range(89)]
    assert crossover(closes[:58]) == "BUY"
    assert crossover(closes[:88]) == "HOLD"
    assert crossover(closes) == "SELL"
    assert crossover(closes[:50]) == "HOLD"


def test_moving_average_keeps_decimal_precision():
    assert moving_average([Decimal("1"), Decimal("2"), Decimal("4")], 3) == Decimal("7") / Decimal("3")


def test_demo_bar_is_stable_and_time_is_hourly_utc():
    first = demo_bar(57)
    again = demo_bar(57)
    assert first == again
    assert first.bar_at.isoformat() == "2024-01-03T09:00:00+00:00"


def test_order_identity_is_deterministic_and_scoped_by_arm():
    a = deterministic_order_id("experiment", "A", 57, "BUY")
    assert a == deterministic_order_id("experiment", "A", 57, "BUY")
    assert a != deterministic_order_id("experiment", "B", 57, "BUY")
    assert len(a) <= 48


def test_live_and_real_application_modes_are_rejected():
    for mode in ("paper", "live", "real"):
        try:
            Settings(app_mode=mode)
        except Exception:
            continue
        raise AssertionError(f"mode {mode} should not be accepted")


def test_choice_without_confidence_is_parsed_from_probabilities():
    parsed = parse_choice({"type": "choice", "choice": "relevant", "probabilities": {"relevant": 0.9, "not_relevant": 0.1}}, {"relevant", "not_relevant"})
    assert parsed["confidence"] == "0.9"
    assert parsed["choice"] == "relevant"


def test_jev_typed_primitives_are_validated_without_assuming_confidence():
    assert parse_noul({"type": "noul", "noul": 0.8})["noul"] == "0.8"
    score = parse_score({"type": "score", "score": 2, "probabilities": {"low": 0.2, "high": 0.8}}, {"low", "high"})
    assert score["confidence"] is None
    try:
        parse_noul({"type": "noul", "noul": 1.5})
    except ValueError:
        pass
    else:
        raise AssertionError("out of range Noul value must be rejected")


def test_filter_policy_blocks_risk_and_abstains_on_missing_confidence():
    policy = {
        "relevance_allow_min_confidence": 0.75,
        "risk_block_min_confidence": 0.65,
        "ambiguity_abstain_min_confidence": 0.65,
        "risk_choice": "risk_event",
        "ambiguity_choice": "insufficient_or_ambiguous",
    }
    risk = {
        "relevance": {"choice": "relevant", "confidence": "0.9"},
        "risk": {"choice": "risk_event", "confidence": "0.8"},
        "sufficiency": {"choice": "sufficient", "confidence": "0.9"},
    }
    assert apply_filter_policy(risk, policy) == ("BLOCK", "evento_de_risco_classificado")
    risk["risk"]["confidence"] = None
    assert apply_filter_policy(risk, policy) == ("ABSTAIN", "confidence_absente")
