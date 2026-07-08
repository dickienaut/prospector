"""Regression: the _run_sensors PROLOGUE must be inside a soft-fault boundary (N6).

The runner's design claim is per-unit fault granularity: "one fund's 404 never blinds the others" —
each ingest/sensor call is wrapped in its own try/except that records a SCOPED soft fault and lets the
rest of the tick proceed (§9g). But the prologue of `_run_sensors` runs OUTSIDE every one of those
boundaries:

    retry_days = int((deps.cfg.get("identity") or {}).get("retry_days", 10))   # <- raises on "ten"
    machine = ResolutionMachine(deps.registry, store, FundRegistry(...), ...)
    _panel = _build_sector_panel(...)

So a single bad config value that only the RETRY queue uses — `identity.retry_days: "ten"` — throws
before the first sensor boundary, escapes `_run_sensors` entirely, and is caught only by run_tick's
outermost backstop as ONE `subsystem="runner"` FATAL fault. The whole sensor+ingest phase is blinded:
no mf ingest, no launch recording, no xcorr — by a typo in the retry window. That is the exact inverse
of the granularity the design promises.

The fix (either option satisfies these tests): wrap the prologue in its own soft-fault boundary, or
validate `identity.retry_days` at config-load so a bad value faults as a scoped `config` fault with the
launch sensor still running. Self-contained harness (house convention — see test_runner_*.py).
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
    body = _mf_bytes(current_rows)

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return body
        raise EdgarError(f"no fixture for {url}", status=404)

    return fetch


def _price_ok(url, headers):
    return json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 200.0, "adjClose": 100.0,
                        "splitFactor": 1.0}]).encode("utf-8")


def _deps(layout, registry, fetch, *, cfg, cfg_hash):
    return RunnerDeps(
        layout=layout, registry=registry, event_store=EventStore(layout, registry),
        edgar_client=_edgar(layout, NOW[:10], fetch),
        price_ingest=PriceIngest(layout, fetch=_price_ok, clock=lambda: NOW[:10],
                                 sleep=lambda _s: None, api_token="tiingo-test-token"),
        notifier=NullNotifier(), cfg=cfg, cfg_hash=cfg_hash,
        now=NOW, run_id="run_test", monotonic=lambda: 0.0)


def _seed_prior_mf(layout, rows, date=PRIOR_DATE):
    write_atomic(layout.edgar_path(date, "company_tickers_mf.json"), _mf_bytes(rows))


def test_bad_retry_days_does_not_blind_the_whole_sensor_phase(layout, registry):
    # A launch IS present this tick (NEW_ROW vs the seeded prior), and identity.retry_days is a typo.
    # The retry-window typo must not prevent the launch from being RECORDED — capture-first (§4c) is
    # the load-bearing invariant, and it does not depend on the retry window at all.
    _seed_prior_mf(layout, [XLK_ROW])
    cfg, _ = load_config(CONFIG)
    bad = dict(cfg)
    bad["identity"] = {**(cfg.get("identity") or {}), "retry_days": "ten"}  # non-integer typo

    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW]),
                            cfg=bad, cfg_hash="deadbeefcafe"))

    # RED today: the int("ten") in the prologue escapes to the backstop, so runlog.fatal is True, the
    # only fault is subsystem="runner", and launch.unverified is empty — the whole phase was blinded.
    unverified = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")
    subsystems = [f.get("subsystem") for f in runlog.faults]

    assert not runlog.fatal, (
        f"a bad identity.retry_days made the WHOLE tick fatal (faults={subsystems}) — the prologue "
        "runs outside every soft-fault boundary, so a retry-window typo blinds the entire sensor "
        "phase (N6)")
    assert len(unverified) == 1, (
        f"the launch was not recorded (launch.unverified={len(unverified)}) — a config value only the "
        "retry queue uses blinded capture-first launch recording (§4c). A bad retry_days should be a "
        "SCOPED fault with the launch sensor still running (N6)")


def test_bad_retry_days_is_a_scoped_fault_not_a_runner_fatal(layout, registry):
    # Complements the above: the failure must localize. A bad retry_days should surface as a config- or
    # identity-scoped fault, NOT as the single catch-all subsystem="runner" backstop fault (which is
    # reserved for genuinely-unexpected escapes, §9g).
    _seed_prior_mf(layout, [XLK_ROW])
    cfg, _ = load_config(CONFIG)
    bad = dict(cfg)
    bad["identity"] = {**(cfg.get("identity") or {}), "retry_days": "ten"}

    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW]),
                            cfg=bad, cfg_hash="deadbeefcafe"))
    subsystems = [f.get("subsystem") for f in runlog.faults]

    assert subsystems and subsystems != ["runner"], (
        f"the only fault was the catch-all backstop (faults={subsystems}) — a foreseeable bad-config "
        "value should be caught in a scoped boundary (config/identity), not escape to the runner "
        "backstop that is meant for the unforeseeable (N6)")
