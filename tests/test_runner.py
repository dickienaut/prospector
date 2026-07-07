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
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.runner.runlog import recent_runs
from prospector.runner.runner import _compute_push
from prospector.store.envelope import SYSTEM_LEAD, canonical_json
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

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


def _deps(layout, registry, fetch, *, now=NOW, notifier=None, event_store=None,
          cfg=None, cfg_hash=None, run_id="run_test"):
    base_cfg, base_hash = load_config(CONFIG)
    return RunnerDeps(
        layout=layout, registry=registry,
        event_store=event_store if event_store is not None else EventStore(layout, registry),
        edgar_client=_edgar(layout, now[:10], fetch),
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
    # The §10 arbiter in isolation: a {status,shadow,verdict} delta pushes; a fault always pushes;
    # nothing else does (a silent tick with no delta and no fault stays quiet).
    assert _compute_push({}, []) is False
    assert _compute_push({"ld_x": ["status"]}, []) is True
    assert _compute_push({}, [{"subsystem": "ingest.mf_tickers", "message": "boom"}]) is True


# -- guards: the firewall and the runs_path shape -------------------------------------------

def test_runner_firewall_never_reads_portfolio():
    # The wall (CLAUDE.md): the runner never reaches into the portfolio system. Guard the specific
    # forbidden read across the whole package source.
    import prospector.runner.deps as deps_mod
    import prospector.runner.notify as notify_mod
    import prospector.runner.runlog as runlog_mod
    import prospector.runner.runner as runner_mod
    for mod in (runner_mod, deps_mod, notify_mod, runlog_mod):
        assert "portfolio.yaml" not in Path(mod.__file__).read_text(encoding="utf-8")


def test_runs_path_shape(layout):
    assert layout.runs_path("2026-07-02", "abc123") == layout.root / "runs" / "2026-07-02_abc123.json"
