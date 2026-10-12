"""Additional boundary checks; supplied tests remain unchanged."""

from gameday_lab.breaker import BreakerState, SlidingWindowBreaker
from gameday_lab.client import ResilientClient
from gameday_lab.retry import FullJitterBackoff
from gameday_lab.sim.contracts import Attempt, CallContext, GiveUp, ProviderError, ProviderInfo, Send


def client(settings=None):
    providers = {name: ProviderInfo(name, name, "us", True, 1.0) for name in ("a", "b")}
    return ResilientClient(providers, list(providers), settings or {})


def test_all_rate_limited_waits_until_retry_after():
    c = client()
    call = CallContext(1, 1, "tool", 0, 30)
    send = c.start(call, 0)
    for now in (0.1, 0.2):
        assert isinstance(send, Send)
        send = c.on_error(Attempt(call, send.provider, 1, now, send.tag),
                          ProviderError(send.provider, 429, "rate_limit_exceeded", retry_after=2), now)
    assert isinstance(send, Send)
    assert 0.2 + send.delay_s >= c.cooldown_until[send.provider]
    assert 0.2 + send.delay_s + send.timeout_s <= call.deadline


def test_all_quota_exhausted_gives_up_even_with_short_quota_cooldown():
    c = client({"quota_cooldown_s": 2})
    call = CallContext(1, 1, "tool", 0, 30)
    send = c.start(call, 0)
    for now in (0.1, 0.2):
        assert isinstance(send, Send)
        send = c.on_error(Attempt(call, send.provider, 1, now, send.tag),
                          ProviderError(send.provider, 429, "insufficient_quota"), now)
    assert isinstance(send, GiveUp)


def test_no_budget_fails_over_and_resets_per_provider_attempt_count():
    c = client({"retry_budget_max_tokens": 0, "retry_budget_ratio": 0, "retry_budget_min_per_s": 0})
    call = CallContext(1, 1, "tool", 0, 30)
    send = c.start(call, 0)
    action = c.on_error(Attempt(call, send.provider, 1, 0, send.tag),
                        ProviderError(send.provider, 500, "api_error"), 0.1)
    assert isinstance(action, Send) and action.provider == "b"
    assert call.state["tries"] == 1


def test_short_deadline_does_not_leak_half_open_permit():
    c = client({"breaker": {"min_calls": 1, "half_open_max_probes": 1}})
    b = c.breakers["a"]
    b.on_failure(b.allow(0), 0)
    assert b.state is BreakerState.OPEN
    assert isinstance(c.start(CallContext(1, 1, "tool", 11, 11.5), 11), GiveUp)
    assert b.probes_in_flight == 0


def test_late_success_and_release_do_not_affect_new_probe():
    b = SlidingWindowBreaker("a", min_calls=1, half_open_max_probes=1, half_open_successes=1)
    old = b.allow(0)
    b.on_failure(b.allow(0), 0)
    probe = b.allow(10)
    b.on_success(old, 10.1, 0.1)
    b.release(old, 10.2)
    assert b.state is BreakerState.HALF_OPEN and b.probes_in_flight == 1
    b.on_success(probe, 11, 1)
    assert b.state is BreakerState.CLOSED


def test_huge_retry_number_is_capped_without_overflow():
    assert 0 <= FullJitterBackoff().delay(1000000) <= 8
