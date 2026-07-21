"""The M5 runner skeleton — the thin spine (spec §9). Tests are OFFLINE: the EdgarClient's `fetch`
is injected and closed over in-memory fixtures, its rate-limiter clock/sleep are injected, and the
network guard (conftest) fails any real socket. The invariants under test are the load-bearing ones:

  - config honesty fires BEFORE any sensor (§9 run-order-1, subtle bit #1);
  - launches are recorded but do NOT push (§10 — launch is a silent stream);
  - a first run SEEDS the mf prior rather than flagging the universe (§9a);
  - an ingest failure is a SOFT fault that continues AND pushes (a fault always pushes, §9g/§10);
  - the run-log is written + indexed and is NOT a lead event (§9g);
  - two cold runs over identical inputs produce identical EVENTS (statelessness CONTRACT, §9);
  - the push is pinned to fold.state_changed (§10) — a real lead's status change pushes and
    snapshots, launch-only ticks do not;
  - the firewall holds (no portfolio read) and `pros run` is not a run-now surface.
"""

import json
from pathlib import Path

import pytest

from prospector.config import load_config
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.holdings import HoldingsIngest
from prospector.ingest.prices import PriceIngest, PriceIngestError
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.runner.runlog import recent_runs
from prospector.runner.runner import _compute_push
from prospector.store.envelope import SYSTEM_LEAD, canonical_json
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

# §9e: dispersion runs every tick now; a valid SPDR holdings body lets its membership parse, and the
# constituent-price pulls miss here, so it SKIPS cleanly (no fault/spawn) — these runner assertions hold.
_XLK_HOLDINGS = (Path(__file__).parent / "fixtures" / "holdings" / "XLK_2026-07-02.csv").read_bytes()

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-02T22:30:00Z"
PRIOR_DATE = "2026-07-01"

# mf_tickers rows are [cik, seriesId, classId, symbol] (see edgar.mf_tickers).
XLK_ROW = [1234, "S000006415", "C000019213", "XLK"]
NEW_ROW = [5678, "S000099999", "C000099999", "NEWX"]


def _mf(rows):
    return {"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}


def _mf_bytes(rows):
    return json.dumps(_mf(rows)).encode("utf-8")


class _FakeClock:
    """Monotonic-shaped clock for the EdgarClient rate limiter; `sleep` advances it, so throttling
    is deterministic and opens no real socket."""

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
    """Serve the mf-tickers map; 404 everything else (so a new ticker's submissions fetch fails and
    the launch parks in the retry queue — the simplest launch path, no submissions fixture)."""
    body = _mf_bytes(current_rows)

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return body
        raise EdgarError(f"no fixture for {url}", status=404)

    return fetch


def _tiingo_ok_body() -> bytes:
    """A minimal valid Tiingo EOD body (one row). The §9a prices ingest now runs EVERY tick through the
    primary source (tiingo, 2026-07-07), so tests that don't exercise prices just need a clean, parseable
    body per ticker — no fault, no push. adjClose (100.0) is the adjusted field the parser reads."""
    return json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 200.0, "adjClose": 100.0,
                        "splitFactor": 1.0}]).encode("utf-8")


def _price_fetch_ok(url, headers):
    return _tiingo_ok_body()


def _deps(layout, registry, fetch, *, now=NOW, notifier=None, event_store=None,
          cfg=None, cfg_hash=None, run_id="run_test", price_fetch=None):
    base_cfg, base_hash = load_config(CONFIG)
    return RunnerDeps(
        layout=layout, registry=registry,
        event_store=event_store if event_store is not None else EventStore(layout, registry),
        edgar_client=_edgar(layout, now[:10], fetch),
        # Frozen price pulls are pinned to the tick date so they land under prices_path deterministically.
        # api_token: the default source is now tiingo (config), whose header builder reads a token; a fake
        # one keeps the offline panel building. sleep no-op: the panel pulls 12+ tickers through the throttle.
        price_ingest=PriceIngest(layout, fetch=price_fetch or _price_fetch_ok, clock=lambda: now[:10],
                                 sleep=lambda _s: None, api_token="tiingo-test-token"),
        holdings_ingest=HoldingsIngest(layout, fetch=lambda u, h: _XLK_HOLDINGS, clock=lambda: now[:10]),

        notifier=notifier if notifier is not None else NullNotifier(),
        cfg=cfg if cfg is not None else base_cfg,
        cfg_hash=cfg_hash if cfg_hash is not None else base_hash,
        now=now, run_id=run_id, monotonic=lambda: 0.0)


def _seed_prior_mf(layout, rows, date=PRIOR_DATE):
    write_atomic(layout.edgar_path(date, "company_tickers_mf.json"), _mf_bytes(rows))


def _events(registry):
    return [r for lead in registry.all_leads() for r in registry.events_for_lead(lead)]


# -- first run seeds, flags nothing ---------------------------------------------------------

def test_first_run_seeds_prior_and_records_no_launches(layout, registry):
    # No prior frozen mf blob -> the runner seeds (today's map becomes tomorrow's prior) instead of
    # flagging the whole universe as launches (§9a). The current map is still frozen.
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW])))
    assert runlog.sensors["launch"] == "seeded"
    assert runlog.sensors["soi_corroboration"] == "ran"  # the §9d SLOT is reached (no pending -> no-op)
    assert registry.events_for_lead(SYSTEM_LEAD, "launch.unverified") == []
    assert layout.edgar_path(NOW[:10], "company_tickers_mf.json").is_file()  # frozen substrate
    assert runlog.pushed is False and runlog.config_changed is False


# -- launch recorded, but silent (no push) --------------------------------------------------

def test_launch_is_recorded_but_does_not_push(layout, registry):
    # A new (symbol, seriesId) vs the seeded prior -> launch.unverified nailed at detection; the
    # submissions fetch 404s so it parks in the retry queue (resolution.failed). NEITHER pushes:
    # launch is a silent stream (§10 anti-slot-machine), and a graceful ResolutionFailure is not a
    # fault. The dead-man stays quiet on a launch — exactly the intent.
    _seed_prior_mf(layout, [XLK_ROW])
    notifier = NullNotifier()
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW]),
                            notifier=notifier))

    unverified = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")
    assert len(unverified) == 1
    assert json.loads(unverified[0]["payload"])["ticker"] == "NEWX"
    assert registry.events_for_lead(SYSTEM_LEAD, "resolution.failed")  # parked, never dropped
    assert runlog.sensors["launch"] == "ran"
    assert notifier.pushes == []          # a launch never pages
    assert runlog.pushed is False
    assert runlog.faults == []            # a graceful resolution failure is not a fault


# -- config honesty fires before any sensor -------------------------------------------------

class _RecordingStore(EventStore):
    """Records the ORDER in which event types are appended, to prove config.changed precedes any
    sensor event (they share `now`, so ordering can't be read from the ts)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order: list[str] = []

    def append(self, raw):
        written = super().append(raw)
        self.order.append(written.envelope.type)
        return written


def test_config_change_is_fossilized_before_sensors_run(layout, registry):
    # Pre-seed a STALE config hash so check_config_honesty emits config.changed this tick; seed a
    # launch so there is a sensor event to order against. The CONTRACT: config.changed is appended
    # BEFORE launch.unverified (never act on an un-fossilized config, §9 run-order-1 / subtle bit #1).
    cfg, cfg_hash = load_config(CONFIG)
    registry.set_meta("last_config_hash", "STALEHASH")
    registry.set_meta("last_config_json", canonical_json({}))
    _seed_prior_mf(layout, [XLK_ROW])

    rec = _RecordingStore(layout, registry)
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW]),
                            event_store=rec, cfg=cfg, cfg_hash=cfg_hash))

    assert runlog.config_changed is True
    assert "config.changed" in rec.order and "launch.unverified" in rec.order
    assert rec.order.index("config.changed") < rec.order.index("launch.unverified")


# -- soft fault on ingest failure: continue AND push ----------------------------------------

def test_ingest_failure_is_a_soft_fault_that_continues_and_pushes(layout, registry):
    # The mf fetch 500s -> a SOFT fault on _system (subsystem ingest.mf_tickers), the run does not
    # abort (retries still run, the run-log is written), and BECAUSE there is a fault the runner
    # STILL pushes — a fault email beats silence (§9g/§10 dead-man).
    def fetch(url, headers):
        raise EdgarError("edgar is down", status=500)

    notifier = NullNotifier()
    runlog = run_tick(_deps(layout, registry, fetch, notifier=notifier))

    faults = registry.events_for_lead(SYSTEM_LEAD, "fault")
    assert any(json.loads(f["payload"])["subsystem"] == "ingest.mf_tickers" for f in faults)
    assert runlog.ingests["mf_tickers"] == "fault"
    assert runlog.sensors["identity_retries"] == "ran"   # the run continued past the fault
    assert runlog.pushed is True and len(notifier.pushes) == 1  # a fault always pushes


# -- §9a prices ingest: the sector-ETF panel is built and frozen ----------------------------

def test_prices_panel_is_built_and_frozen(layout, registry):
    # The runner builds the sector-ETF correlation grid every tick and FREEZES each pull before parse
    # (§3/§9a) — the shared substrate xcorr (§4a) will consume. Prove: every universe ticker's raw
    # body lands under prices_path (the frozen substrate), and the ingest ran clean.
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW])))
    assert runlog.ingests["prices"] == "ran"
    cfg, _ = load_config(CONFIG)
    tickers = list(cfg["universe"]["sectors"]) + [cfg["universe"]["market"]]
    for t in tickers:
        assert layout.prices_path("tiingo", NOW[:10], f"{t}.json").is_file()  # frozen substrate (§3)


def test_prices_per_ticker_failure_is_a_soft_fault(layout, registry):
    # One ticker's price fetch 404s; the others land, the grid still builds, the run goes on — a
    # per-unit SOFT fault (§9g), never a run-abort. The failed pull froze nothing (fetch raises before
    # write_atomic). (A fault pushes — that is the dead-man, not the subject of this test.)
    def price_fetch(url, headers):
        if "XLK" in url.upper():
            raise PriceIngestError("no XLK price fixture", status=404)
        return _tiingo_ok_body()

    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]), price_fetch=price_fetch))
    assert runlog.ingests["prices"] == "ran"                       # the grid still built from the rest
    faults = registry.events_for_lead(SYSTEM_LEAD, "fault")
    assert any(json.loads(f["payload"])["subsystem"] == "ingest.prices" for f in faults)
    assert not layout.prices_path("tiingo", NOW[:10], "XLK.json").is_file()  # failed pull froze nothing


def test_p1_guard_fails_closed_on_unverified_stooq_live_source(layout, registry):
    # P1 (§3): with Stooq forced as the live primary and stooq_adjusted_verified false, the guard fails
    # CLOSED — the prices ingest is a fault (no panel), recorded on _system. parse_stooq only ASSUMES
    # `Close` is adjusted; a live unverified Stooq would silently corrupt every return across a split.
    import copy
    cfg, cfg_hash = load_config(CONFIG)
    cfg = copy.deepcopy(cfg)
    cfg["prices"]["primary"] = "stooq"                       # force the unverified source live
    assert cfg["prices"]["stooq_adjusted_verified"] is False
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]), cfg=cfg, cfg_hash=cfg_hash))
    assert runlog.ingests["prices"] == "fault"
    faults = [json.loads(f["payload"]) for f in registry.events_for_lead(SYSTEM_LEAD, "fault")]
    assert any(f["subsystem"] == "ingest.prices" and "P1" in f["message"] for f in faults)
    # Fail-closed means NOTHING was pulled/frozen from the unverified source.
    assert not (layout.root / "ingest" / "prices" / "stooq").exists()


# -- run-log is written, indexed, and NOT a lead event --------------------------------------

def test_run_log_is_written_indexed_and_not_a_lead_event(layout, registry):
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW])))

    path = layout.runs_path(runlog.date, runlog.run_id)
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == "run_test" and on_disk["date"] == NOW[:10]

    rows = recent_runs(registry)
    assert len(rows) == 1 and rows[0]["run_id"] == "run_test"
    # Operational telemetry, not a lead: it never appears in the event record or as a lead.
    assert "run_test" not in registry.all_leads()
    assert registry.events_for_lead("run_test") == []


# -- statelessness: two cold runs produce identical events ----------------------------------

def test_two_cold_runs_produce_identical_events(tmp_path):
    # The statelessness CONTRACT (§9): the state IS the store, so two cold runs over identical
    # inputs on fresh stores fold to identical EVENTS. (event_id is a per-write uuid and the run-log
    # carries elapsed/run_id, so both are excluded — we compare (lead, type, ts, payload).)
    runs = []
    for name in ("a", "b"):
        layout = StoreLayout(tmp_path / name / "store")
        registry = Registry(layout.registry_path())
        try:
            _seed_prior_mf(layout, [XLK_ROW])
            run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW, NEW_ROW])))
            runs.append(sorted((r["lead"], r["type"], r["ts"], r["payload"])
                               for r in _events(registry)))
        finally:
            registry.close()
    assert runs[0] == runs[1]
    assert any(t == "launch.unverified" for _, t, _, _ in runs[0])  # non-trivial: a launch fired


# -- snapshot + push on a real lead's state change (the machinery, pinned to state_changed) -

def test_real_lead_state_change_snapshots_and_pushes(layout, registry):
    # A pre-existing active lead (a lead.spawned, no prior snapshot) crosses into an initial state:
    # state_changed(None, active) == ['status'] -> the runner snapshots it AND pushes. This pins the
    # snapshot/push machinery to fold.state_changed (§10), independent of the launch vertical.
    EventStore(layout, registry, clock=lambda: NOW).append(
        {"ts": "2026-07-01T00:00:00Z", "lead": "ld_x", "type": "lead.spawned",
         "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    notifier = NullNotifier()
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]), notifier=notifier))

    assert runlog.changed_leads.get("ld_x") == ["status"]
    assert layout.snapshot_path("ld_x", NOW).is_file()
    assert runlog.pushed is True and len(notifier.pushes) == 1


def test_compute_push_is_pinned_to_state_change_or_fault():
    # The §10 arbiter in isolation: a NON-shadow {status,shadow,verdict} delta pushes; a NEW/changed fault
    # pushes; nothing else does. Third arg is the prior run's faults (the nuisance-suppression comparand).
    boom = [{"subsystem": "ingest.mf_tickers", "message": "boom"}]
    assert _compute_push({}, [], []) is False                       # quiet tick: no delta, no fault
    assert _compute_push({"ld_x": ["status"]}, [], []) is True      # a non-shadow state change pages
    assert _compute_push({}, boom, []) is True                      # a NEW fault (no prior) pages
    # §10 NUISANCE-ALARM SUPPRESSION: the SAME fault as the prior run does NOT page (it rides the heartbeat);
    # a CHANGED message does; a state change pages regardless of the fault repeating.
    assert _compute_push({}, boom, boom) is False                   # recurring identical fault: suppressed
    assert _compute_push({}, boom, [{"subsystem": "ingest.mf_tickers", "message": "different"}]) is True
    assert _compute_push({"ld_x": ["status"]}, boom, boom) is True  # state change wins over a stale fault


# -- guards: the firewall and the runs_path shape -------------------------------------------

# The runner's firewall guard moved to `tests/test_firewall.py`, which sweeps the WHOLE package
# (this one listed 4 modules by hand; 48 others were unguarded). One rule, one home.


def test_runs_path_shape(layout):
    assert layout.runs_path("2026-07-02", "abc123") == layout.root / "runs" / "2026-07-02_abc123.json"


# -- M7-01: the runner owns the heartbeat cadence (catch-up on a slept-through cycle) ---------

class _RaisingHeartbeatNotifier(NullNotifier):
    """A notifier whose heartbeat send RAISES — proves a failed send does NOT advance the clock."""

    def heartbeat(self, payload):
        raise RuntimeError("smtp down")


def _seed_heartbeat(layout, registry, ts):
    from prospector.runner.runner import record_heartbeat_sent
    record_heartbeat_sent(EventStore(layout, registry), ts)


def test_heartbeat_catch_up_sends_one_and_records_the_fact(layout, registry):
    # A heartbeat 8 days before NOW -> a quiet daily tick (no --heartbeat) still sends ONE catch-up and
    # fossilizes exactly one new heartbeat.sent at now: the cycle the Mac slept through is made up, once.
    _seed_prior_mf(layout, [XLK_ROW])
    _seed_heartbeat(layout, registry, "2026-06-24T22:30:00Z")     # 8 days before NOW (2026-07-02)
    notifier = NullNotifier()
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]), notifier=notifier))

    assert len(notifier.heartbeats) == 1                          # exactly one catch-up heartbeat sent
    sent = registry.events_for_lead(SYSTEM_LEAD, "heartbeat.sent")
    assert len(sent) == 2 and sent[-1]["ts"] == NOW               # seed + one new, dated `now`
    assert json.loads(sent[-1]["payload"])["trigger"] == "cadence"
    assert runlog.event_counts.get("heartbeat.sent") == 1        # counted this tick (only the new one)


def test_within_cadence_tick_does_not_resend_the_heartbeat(layout, registry):
    _seed_prior_mf(layout, [XLK_ROW])
    _seed_heartbeat(layout, registry, "2026-07-01T22:30:00Z")     # 1 day before NOW -> within cadence
    notifier = NullNotifier()
    run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]), notifier=notifier))

    assert notifier.heartbeats == []                              # no catch-up (no double-paging)
    assert len(registry.events_for_lead(SYSTEM_LEAD, "heartbeat.sent")) == 1   # still just the seed


def test_failed_heartbeat_send_does_not_advance_the_clock(layout, registry):
    # THE CRITICAL edge (M7-01): a raising send must NOT record heartbeat.sent — else the dead-man goes
    # quiet believing it spoke. The failure surfaces as a notify.heartbeat fault, and the tick stays due.
    from prospector.runner.runner import heartbeat_is_due
    _seed_prior_mf(layout, [XLK_ROW])
    _seed_heartbeat(layout, registry, "2026-06-24T22:30:00Z")     # 8 days before NOW -> due
    runlog = run_tick(_deps(layout, registry, _fetch_mf_only([XLK_ROW]),
                            notifier=_RaisingHeartbeatNotifier()))

    assert len(registry.events_for_lead(SYSTEM_LEAD, "heartbeat.sent")) == 1   # NO new record — clock held
    assert any(f["subsystem"] == "notify.heartbeat" for f in runlog.faults)    # the failure is loud
    assert heartbeat_is_due(registry, NOW, {"schedule": {"heartbeat_cadence_days": 7}}) is True  # still due
