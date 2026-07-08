"""Regression: the price-fetch retry must cover transient server/network errors, not only 429/403 (N7).

`PriceIngest._fetch_with_retry` retries ONLY `_RETRY_STATUSES = (429, 403)`. A transient 5xx
(502/503/504 — routine behind a load balancer) or a socket read-timeout therefore hits the final
`raise` on attempt 1, silently dropping that ticker's column for the whole tick with no recovery.
Over 12+ sector-ETF pulls per tick this is a frequent, avoidable panel gap (a dropped column becomes a
NaN the outer join can't fill — §3 — so the whole tick's xcorr loses a pair).

These tests assert the *behaviour* a fix must produce (retry then succeed on a transient error), not a
specific status set, so they don't lock in which codes/exceptions the implementer chooses to add.

N7 was labelled a SMELL (INFERRED) in the review. It is verified here by driving the real retry loop
with a counting fetch — a 503-then-200 sequence should be recovered, exactly like a 429-then-200 is.
"""

import pytest

from prospector.ingest.prices import PriceIngest, PriceIngestError
from prospector.store.layout import StoreLayout


def _ingest(fetch, layout):
    # sleep is a no-op so the backoff opens no real clock; api_token keeps the tiingo header builder happy.
    return PriceIngest(layout, fetch=fetch, clock=lambda: 0.0, sleep=lambda _s: None,
                       api_token="tiingo-test-token")


def _counting_fetch(status_sequence):
    """A fetch that returns the given HTTP outcomes in order; 200 -> a valid empty body."""
    state = {"n": 0}

    def fetch(url, headers):
        i = state["n"]
        state["n"] += 1
        status = status_sequence[min(i, len(status_sequence) - 1)]
        if status == 200:
            return b"[]"
        raise PriceIngestError(f"GET {url} -> HTTP {status}", status=status)

    return fetch, state


def test_transient_5xx_is_retried_then_succeeds(layout):
    # A 503 on the first attempt, then 200 — a transient server blip. A retry recovers it; today it is
    # NOT retried (503 not in _RETRY_STATUSES), so the first 503 raises and the ticker is dropped. RED.
    fetch, calls = _counting_fetch([503, 200])
    ingest = _ingest(fetch, layout)

    body = ingest._fetch_with_retry("https://api.example/prices", {})
    assert body == b"[]", "a transient 5xx should be retried and the subsequent 200 returned (N7)"
    assert calls["n"] == 2, (
        f"expected a retry after the 503 (2 attempts), got {calls['n']} — a transient 5xx is dropped "
        "on the first attempt because retry covers only 429/403 (N7)")


def test_transport_timeout_is_retried_then_succeeds(layout):
    # Beyond the 5xx statuses: a transport/read-timeout surfaces as a PriceIngestError with status None
    # (the httpx.HTTPError catch in _default_fetch). It is the same transient class — retry it (N7). RED
    # before the fix: status None fell through to the final raise on attempt 1 and dropped the ticker.
    attempts = {"n": 0}

    def flaky(url, headers):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise PriceIngestError(f"GET {url} failed: ReadTimeout")  # status defaults to None
        return b"[]"

    ingest = _ingest(flaky, layout)
    body = ingest._fetch_with_retry("https://api.example/prices", {})
    assert body == b"[]" and attempts["n"] == 2


def test_persistent_5xx_still_gives_up_loudly(layout):
    # The fix must not make 5xx retry forever: a persistent 503 still raises (a loud, countable failure
    # that soft-faults the ticker for this tick), it just does so AFTER exhausting the retry budget.
    fetch, calls = _counting_fetch([503, 503, 503, 503, 503])
    ingest = _ingest(fetch, layout)

    with pytest.raises(PriceIngestError):
        ingest._fetch_with_retry("https://api.example/prices", {})
    assert calls["n"] >= 2, (
        f"a persistent 5xx should be retried before giving up, got only {calls['n']} attempt(s) (N7)")
