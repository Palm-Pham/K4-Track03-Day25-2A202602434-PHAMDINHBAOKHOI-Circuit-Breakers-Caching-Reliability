"""Boundary cases for the remaining lab work; supplied tests are untouched."""

import pytest

from gameday_lab.cache import SemanticCache
from gameday_lab.sim.contracts import Answer, Request
from gameday_lab.slo.alerting import AlertRule, BurnRateAlerter, error_budget_report
from gameday_lab.workflows.executor import checkpoint_key, idempotency_key
from gameday_lab.workflows.runner import RefundRequest


def test_exact_burn_threshold_fires_despite_float_representation():
    rule = AlertRule("boundary", "page", 60, 5, 14.4)
    events = BurnRateAlerter(rules=(rule,)).evaluate([1000] * 60, [72] * 60)
    assert len(events) == 1 and events[0].start_min == 0 and events[0].end_min == 60


def test_exactly_spent_budget_freezes_releases():
    report = error_budget_report([200], [1])
    assert report["budget_remaining"] == 0 and report["freeze_releases"] is True


def test_empty_traffic_has_no_alerts_and_no_consumed_budget():
    assert BurnRateAlerter().evaluate([], []) == []
    assert error_budget_report([], [])["budget_consumed"] == 0
    with pytest.raises(ValueError):
        BurnRateAlerter().evaluate([1], [])


def test_mismatched_answer_prompt_is_not_stored():
    cache = SemanticCache()
    request = Request("faq", "u1", False, "v2", (1.0, 0.0))
    cache.store(request, Answer(1, "v1", ("source",), 0), 0)
    assert cache.lookup(request, 1) is None


def test_keys_cannot_collide_when_session_or_step_contains_delimiters():
    first = RefundRequest("a:b", "o", 10, "u@example.com")
    second = RefundRequest("a", "o", 10, "u@example.com")
    assert idempotency_key(first, "c") != idempotency_key(second, "b:c")
    assert checkpoint_key(first, "c") != idempotency_key(first, "c")
