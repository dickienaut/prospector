"""Regression: the retry policy must fit Tiingo's per-HOUR cap, not SEC's per-second cap (N4).

`_RETRY_STATUSES`/`_BACKOFF_BASE_SECONDS` were copied verbatim from `EdgarClient`, where SEC's limit
is per-SECOND and a 1-2s backoff genuinely clears a 429. Tiingo's binding cap is 50 requests/HOUR
(config comment). Two consequences the review flagged:

  N4a — a 429 retried within seconds cannot reopen an hourly window; each of the 3 attempts spends
        another of the 50 hourly requests (12 tickers x 3 = 36 wasted pulls), so the "backoff"
        ACCELERATES budget exhaustion. On an hourly cap the right move is to stop and let the ticker
        soft-fault to the next tick, not to hammer 3x in 3 seconds. (A per-SECOND-capped source like
        yahoo/stooq SHOULD keep retrying 429 — so the fix is source-aware, not a global change.)
  N4b — 403 is in the retry set, but a Tiingo 403 is an auth/entitlement refusal (expired/invalid
        token) that NEVER clears on retry — retrying burns 3 useless requests per ticker.

These assert the *policy* a fix must implement; they are DESIGN-DECISION tests (unlike the mechanical
N7), and they will need to move if the team chooses a different remedy (e.g. Retry-After honoring with
a hard per-hour ceiling). The 429 test targets the TIINGO rate model specifically (via the hourly_cap
seam the fix introduces / the source's own flag), since the cap is source-bound; the reference fix adds
`_Source.hourly_cap=True` for tiingo and threads it into `_fetch_with_retry`.
"""

import inspect

import pytest

from prospector.ingest.prices import PriceIngest, PriceIngestError
from prospector.store.layout import StoreLayout


def _ingest(fetch, layout):
    return PriceIngest(layout, fetch=fetch, clock=lambda: 0.0, sleep=lambda _s: None,
                       api_token="tiingo-test-token")


def _counting_fetch(status_sequence):
    state = {"n": 0}

    def fetch(url, headers):
        i = state["n"]
        state["n"] += 1
        status = status_sequence[min(i, len(status_sequence) - 1)]
        if status == 200:
            return b"[]"
        raise PriceIngestError(f"GET {url} -> HTTP {status}", status=status)

    return fetch, state


def _fetch_tiingo(ingest, url, headers):
    """Call _fetch_with_retry the way a Tiingo pull does. The reference fix adds a `hourly_cap` kwarg
    threaded from `_Source.hourly_cap`; if that seam exists, pass it, else fall back to the plain call
    (so this test expresses intent against either the pre- or post-fix signature)."""
    if "hourly_cap" in inspect.signature(ingest._fetch_with_retry).parameters:
        return ingest._fetch_with_retry(url, headers, hourly_cap=True)
    return ingest._fetch_with_retry(url, headers)


def test_auth_403_is_not_retried(layout):
    # A 403 is an auth/entitlement refusal — it never clears on retry, so retrying just burns hourly
    # budget. The fix must fail fast on 403 (1 attempt), not spend all 3. RED today (403 retried 3x).
    fetch, calls = _counting_fetch([403, 403, 403])
    ingest = _ingest(fetch, layout)

    with pytest.raises(PriceIngestError):
        _fetch_tiingo(ingest, "https://api.tiingo.com/tiingo/daily/AAA/prices", {})
    assert calls["n"] == 1, (
        f"a 403 (auth refusal) was attempted {calls['n']} times — it never clears on retry and each "
        "attempt spends one of Tiingo's 50 hourly requests; fail fast on 403 (N4b)")


def test_hourly_cap_429_does_not_burn_the_budget_with_rapid_retries(layout):
    # Tiingo's cap is per-HOUR: a 429 cannot be cleared by a 1-2s backoff, so retrying within seconds
    # only spends more of the 50/hour budget. The fix must NOT hammer 3x in ~3s on a 429 for a per-hour
    # source — it should stop (soft-fault to next tick). RED today (429 retried to 3 attempts).
    fetch, calls = _counting_fetch([429, 429, 429])
    ingest = _ingest(fetch, layout)

    with pytest.raises(PriceIngestError):
        _fetch_tiingo(ingest, "https://api.tiingo.com/tiingo/daily/AAA/prices", {})
    assert calls["n"] == 1, (
        f"an hourly-cap (tiingo) 429 was hammered {calls['n']} times in seconds — the per-second "
        "backoff copied from SEC cannot reopen an hourly window and each retry burns another request; "
        "on a per-hour cap, stop after the first 429 and soft-fault to the next tick (N4a)")
