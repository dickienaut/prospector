"""§10 nuisance-alarm suppression must hold for a PERSISTENT fault whose MESSAGE moves every tick.

The QA finding (docs/notes/email_nuisance_suppression_findings.md): `_compute_push` suppresses a recurring fault
by comparing this tick's `_fault_signature` — `frozenset((subsystem, message))`, MESSAGE-EXACT — to the
prior run's. That is correct only if a persisting fault renders the SAME message each tick. The live price
path does not: `ingest.prices` HTTP faults embed the fetch URL (`prices.py`), and the Tiingo URL carries
`?startDate=…&endDate=…` (Yahoo carries `period1`/`period2` epochs) — both derive from the run date, so a
persistent identical failure (a lapsed Tiingo sub → HTTP 403, the case §10/rev6 says the sender closes)
renders a DIFFERENT message every day → a different signature → it pages EVERY day. That is the GPWS
"cried wolf" failure the smoke-detector brief §2.4 names, silently reopened on the live path.

The existing coverage misses it two ways, both because the message it tests is stable:
  - `test_runner.py::test_compute_push_is_pinned_to_state_change_or_fault` uses a hardcoded `"boom"`;
  - `test_runner_notify.py` drives the EDGAR `mf_tickers` fault, whose URL carries NO dates.
No test drives a PRICE fault, whose URL moves. These tests do.

Each test is RED against current `main` (the moving dates defeat suppression) and GREEN after the fix
(a stable suppression key, separate from the display message — see the reference patch). They are
fix-AGNOSTIC: they assert the push DECISION over real fault text, never a particular key scheme.
House convention (per `test_runner_notify.py`): reuse the production-faithful `test_runner` harness.
"""

import pytest

from prospector.ingest.prices import PriceIngestError, _tiingo_url
from prospector.runner import run_tick
from prospector.runner.notify import NullNotifier
from prospector.runner.runner import _compute_push, _emit_fault, required_pull_start
from tests.test_runner import CONFIG, XLK_ROW, _deps, _fetch_mf_only
from prospector.config import load_config


class _NoopStore:
    """`_emit_fault` appends to the `faults` list (what we read) and then tries `store.append` (the fossil
    write, in a swallow-all try/except). The test only needs the list, so the store is a no-op."""
    def append(self, event: dict) -> None:
        pass


_NOOP_STORE = _NoopStore()


# --- how the runner actually renders an ingest.prices HTTP fault, reproduced faithfully -------------

def _price_fault_for_day(day: int, ticker: str = "NVDA", status: int = 403) -> dict:
    """The fault dict `_build_sector_panel` appends on a persistent price HTTP error, for a given run day,
    built EXACTLY as the runner builds it — via the real `_emit_fault`, so the test tracks the production
    shape (message AND whatever stable `key` the runner attaches) rather than a hand-rolled strawman.

    `message` is `f"{t}: {e}"` where `e` is the real `PriceIngestError(f"GET {url} -> HTTP {s}")` and
    `url` is the REAL `_tiingo_url(start, end)`; `end` is the run date and `start` is
    `required_pull_start(end)` — both move day to day (the volatile token). Whether the fault ALSO carries
    a stable suppression `key` is exactly what's under test: before the fix `_emit_fault` writes none, so
    the signature falls back to the moving message; after the fix it writes `(ticker, status)`."""
    now_date = f"2026-07-{day:02d}"
    cfg, _ = load_config(CONFIG)
    start = required_pull_start(now_date, cfg)
    url = _tiingo_url(ticker, start, now_date)
    e = PriceIngestError(f"GET {url} -> HTTP {status}", status=status)
    faults: list = []
    # Pass the SAME stable key the fixed runner passes at this site (`(ticker, status)`). Fix-agnostic:
    # if `_emit_fault` doesn't yet accept `key=` (pre-fix signature), fall back to the plain call — the
    # fault then carries only the moving message, exactly the pre-fix production shape. Either way the
    # dict is built by the REAL `_emit_fault`, never hand-rolled.
    try:
        _emit_fault(_NOOP_STORE, "ingest.prices", f"{ticker}: {e}", f"{now_date}T00:00:00Z", faults,
                    key=f"{ticker}:{status}")
    except TypeError:
        _emit_fault(_NOOP_STORE, "ingest.prices", f"{ticker}: {e}", f"{now_date}T00:00:00Z", faults)
    return faults[0]


# === UNIT: the arbiter over a real, moving price-fault message (mirrors test_runner's unit test) =====

def test_persistent_price_fault_suppresses_across_ticks():
    # The SAME failure (lapsed sub → 403 on NVDA) on two consecutive daily ticks. The messages differ
    # ONLY in the URL's startDate/endDate — it is the same fault and must page once, then be suppressed.
    tick1 = [_price_fault_for_day(10)]
    tick2 = [_price_fault_for_day(11)]
    assert tick1[0]["message"] != tick2[0]["message"], \
        "precondition: the price-fault message moves day to day (the whole point)"

    assert _compute_push({}, tick1, []) is True          # day 1: a NEW fault pages (correct today)
    # day 2: the SAME persistent failure must NOT page again — it rides the weekly heartbeat.
    assert _compute_push({}, tick2, tick1) is False, \
        "a persistent identical price failure must suppress across ticks (moving URL dates must not " \
        "read as a new fault) — else the lapsed-sub alarm pages every day (GPWS 'cried wolf')"


def test_a_changed_price_status_still_pages():
    # The guard against an over-coarse fix: a 403 (auth) → 500 (server) transition on the same ticker is
    # a genuinely CHANGED fault and must ALWAYS page. Must be GREEN today AND stay GREEN after the fix.
    # This pins the STATUS dimension of the (ticker, status) key.
    day1 = [_price_fault_for_day(10, status=403)]
    day2 = [_price_fault_for_day(11, status=500)]
    assert _compute_push({}, day2, day1) is True


def test_a_different_failing_ticker_still_pages():
    # The MIRROR of the status guard (design thread): the suppression key has TWO load-bearing dimensions —
    # (ticker, status). A DIFFERENT failing ticker (AAPL:403 vs the prior tick's NVDA:403) is a different
    # fault and must page. Without this, "simplify the key to subsystem+status" would look harmless yet
    # silently swallow a new-ticker failure — this test makes that refactor fail. Pin BOTH dimensions, or
    # the never-coarsen-the-key invariant is just a comment.
    nvda = [_price_fault_for_day(10, ticker="NVDA", status=403)]
    aapl = [_price_fault_for_day(11, ticker="AAPL", status=403)]
    assert _compute_push({}, aapl, nvda) is True


# === INTEGRATION: the same thing end-to-end over the REAL run_tick (mirrors test_runner_notify) =====

def _raise_price(url, headers):
    # A persistent price HTTP failure (lapsed Tiingo sub → 403). Raised from the injected price fetch, so
    # it flows through the REAL PriceIngest.pull → _build_sector_panel → _emit_fault with the real URL.
    raise PriceIngestError(f"GET {url} -> HTTP 403", status=403)


def _tick(layout, registry, *, day: int, notifier):
    """One real tick on the shared store, price fetch failing, distinct run_id + `now` (a later day) so
    `_load_prior_faults` reads the genuinely-prior run. mf/holdings are the harness defaults (only prices
    fail), so the tick's ONLY faults are the moving ingest.prices ones."""
    now = f"2026-07-{day:02d}T22:30:00Z"
    deps = _deps(layout, registry, _fetch_mf_only([XLK_ROW]), now=now,
                 notifier=notifier, run_id=f"run_{day:02d}", price_fetch=_raise_price)
    return run_tick(deps)


def test_persistent_price_fault_pages_once_over_real_ticks(layout, registry):
    notifier = NullNotifier()
    r1 = _tick(layout, registry, day=10, notifier=notifier)
    r2 = _tick(layout, registry, day=11, notifier=notifier)
    r3 = _tick(layout, registry, day=12, notifier=notifier)
    # The lapsed-sub failure persists identically; it must page ONCE (day 10, new), then ride the
    # heartbeat (days 11-12) — NOT three pages. The runlog still records the fault every tick (the
    # fossil stays whole); only the push is suppressed.
    assert r1.pushed is True, "the first occurrence of the price fault must page"
    assert r2.pushed is False and r3.pushed is False, \
        "a persistent price fault must page once, then be suppressed — the moving URL dates must not " \
        "make each tick look like a new fault"
    assert len(notifier.pushes) == 1


# === E2 (secondary finding): a FLAPPING fault pages on every recurrence — deferred design ===========

@pytest.mark.xfail(reason="E2: _compute_push compares only to the immediately-prior run, so a fault that "
                          "clears then returns pages on every recurrence. The 'escalate-then-fall-silent "
                          "over an N-day window' shape is a deferred design choice (doc option 3); this "
                          "flips to XPASS the moment it lands.", strict=True)
def test_flapping_fault_does_not_page_on_every_recurrence():
    # Stable message (isolate the FLAPPING dimension from the volatile-message one). present → clear →
    # present. Desired: the return does NOT page (it fired recently, within the suppression window).
    fault = [{"subsystem": "ingest.mf_tickers", "message": "edgar is down"}]
    assert _compute_push({}, fault, []) is True            # t1: new fault pages
    assert _compute_push({}, [], fault) is False           # t2: clears (rides heartbeat)
    # t3: the SAME fault returns; prior run had none. TODAY this pages (prior empty). DESIRED: suppressed.
    assert _compute_push({}, fault, []) is False
