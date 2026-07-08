"""Regression: the tick must be idempotent on the SAME store within a UTC day (finding N2).

The runner's own docstring claims: "two cold runs over the same store produce identical events"
(statelessness CONTRACT, §9). The existing tests/test_runner.py::test_two_cold_runs_produce_identical_events
proves a WEAKER thing — two SEPARATE fresh stores, each run ONCE — so it never exercises a re-tick
against a store that already holds this day's events.

A same-UTC-day re-run is a real operational path: a cron catch-up after a missed/late tick, or an
operator re-running `pros run` after the soft-fault path returned a RunLog (that path deliberately
invites a manual retry, §9g). Because `_load_prior_mf_snapshot` selects the prior mf blob from dates
STRICTLY < today (`d.name < current_date`), the second run of the same day sees the UNCHANGED prior,
re-detects the identical new (symbol, seriesId), and `register_launch` re-emits launch.unverified +
resolution.failed with a fresh uuid4 event_id — nothing dedupes. That double-writes the append-only
fossil the launch-lag / §9f enumeration reads from, and re-issues the EDGAR fetches.

Self-contained harness, matching the house convention (test_runner_mandate/_xcorr/_soi_corroboration
each build their own RunnerDeps rather than importing a sibling test module — tests/ is a package with
no shared helper module).
"""

import json
from pathlib import Path

from prospector.config import load_config
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.prices import PriceIngest
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-02T22:30:00Z"
PRIOR_DATE = "2026-07-01"

# mf_tickers rows are [cik, seriesId, classId, symbol] (see edgar.mf_tickers).
XLK_ROW = [1234, "S000006415", "C000019213", "XLK"]
NEW_ROW = [5678, "S000099999", "C000099999", "NEWX"]


def _mf_bytes(rows):
    return json.dumps({"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}).encode()


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _edgar(layout, tick_date, fetch):
    clock = _FakeClock()
    return EdgarClient("Test/1.0 (test@example.com)", fetch=fetch, clock=clock,
                       sleep=lambda s: setattr(clock, "t", clock.t + s),
                       persist=lambda name, body: write_atomic(
                           layout.edgar_path(tick_date, name), body))


def _fetch_mf_only(current_rows):
    """Serve the mf-tickers map; 404 everything else, so a new ticker's submissions fetch fails and
    the launch parks in the retry queue — the simplest launch path (no submissions fixture)."""
    body = _mf_bytes(current_rows)

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return body
        raise EdgarError(f"no fixture for {url}", status=404)

    return fetch


def _tiingo_ok_body():
    return json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 200.0, "adjClose": 100.0,
                        "splitFactor": 1.0}]).encode("utf-8")


def _deps(layout, registry, fetch, *, now=NOW):
    cfg, cfg_hash = load_config(CONFIG)
    return RunnerDeps(
        layout=layout, registry=registry, event_store=EventStore(layout, registry),
        edgar_client=_edgar(layout, now[:10], fetch),
        price_ingest=PriceIngest(layout, fetch=lambda u, h: _tiingo_ok_body(),
                                 clock=lambda: now[:10], sleep=lambda _s: None,
                                 api_token="tiingo-test-token"),
        notifier=NullNotifier(), cfg=cfg, cfg_hash=cfg_hash,
        now=now, run_id="run_test", monotonic=lambda: 0.0)


def _seed_prior_mf(layout, rows, date=PRIOR_DATE):
    write_atomic(layout.edgar_path(date, "company_tickers_mf.json"), _mf_bytes(rows))


def _events(registry):
    return [r for lead in registry.all_leads() for r in registry.events_for_lead(lead)]


def _run_once(layout, registry):
    # A new (symbol, seriesId) vs the seeded prior -> exactly one launch.unverified per HONEST tick.
    return run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW])))


def test_same_store_retick_same_day_does_not_double_write(layout, registry):
    # The invariant the docstring actually claims: run the SAME store twice on the SAME UTC day and
    # the append-only record must be unchanged by the second run (a re-tick is a no-op, not a
    # duplicate). RED today: the second run re-emits launch.unverified (1 -> 2).
    _seed_prior_mf(layout, [XLK_ROW])

    _run_once(layout, registry)
    after_first = sorted((r["lead"], r["type"], r["ts"], r["payload"]) for r in _events(registry))
    unverified_first = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")
    assert len(unverified_first) == 1  # sanity: the first tick recorded the launch exactly once

    _run_once(layout, registry)  # re-tick, same store, same UTC day, same inputs
    after_second = sorted((r["lead"], r["type"], r["ts"], r["payload"]) for r in _events(registry))
    unverified_second = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")

    assert len(unverified_second) == 1, (
        f"re-tick double-wrote the fossil: launch.unverified went "
        f"{len(unverified_first)} -> {len(unverified_second)} (N2)")
    assert after_second == after_first, (
        "a same-day re-tick changed the append-only record; the statelessness CONTRACT (§9) says "
        "two runs over the same store produce identical events")


def test_same_day_retick_with_a_moving_clock_still_dedupes(layout, registry):
    # The production reality the fixed-clock tests above can't show: two ticks the SAME UTC day have
    # DIFFERENT `now` timestamps (a cron catch-up / an operator re-run hours later). `detected_at` = now
    # MOVES between them, so a (ticker, detected_at) dedup key would NOT match and would double-write —
    # the reference diff's key passes the fixed-clock test but leaves this real hole. Keying on the
    # stable series_id (the HECO identity) closes it.
    _seed_prior_mf(layout, [XLK_ROW])
    fetch = _fetch_mf_only([XLK_ROW, NEW_ROW])
    run_tick(_deps(layout, registry, fetch, now="2026-07-02T09:00:00Z"))
    run_tick(_deps(layout, registry, fetch, now="2026-07-02T14:30:00Z"))  # same UTC day, later clock

    unverified = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")
    assert len(unverified) == 1, (
        f"a same-day re-tick with a moved clock double-wrote launch.unverified ({len(unverified)}) — "
        "dedup must key on the stable series_id, not (ticker, detected_at) which moves with `now` (N2)")
    assert len(registry.events_for_lead(SYSTEM_LEAD, "resolution.failed")) == 1


def test_three_reticks_do_not_accumulate_resolution_failures(layout, registry):
    # The same defect compounds the retry queue: each re-tick re-parks the same launch, so
    # resolution.failed accretes 1 -> 2 -> 3. Guards against a partial fix that dedupes
    # launch.unverified but leaves the resolution path re-enqueuing.
    _seed_prior_mf(layout, [XLK_ROW])
    for _ in range(3):
        _run_once(layout, registry)

    failed = registry.events_for_lead(SYSTEM_LEAD, "resolution.failed")
    assert len(failed) == 1, (
        f"three re-ticks accumulated {len(failed)} resolution.failed events for one launch — the "
        "retry queue is re-enqueuing on every same-day re-run (N2)")
