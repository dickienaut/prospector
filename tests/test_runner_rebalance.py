"""§4d rebalance wired into the runner — the holdings-diff ACCRETION sensor, the LAST M4 sensor into
the runner (spec §9, build note docs/notes/2026-07-11-rebalance-runner-wiring.md). Tests are OFFLINE:
the HoldingsIngest fetch is injected over in-memory bodies (or the frozen files are pre-written), and
the conftest socket guard fails any real connection.

The acceptance gate (the build note's six + the two design forks, each with its own violation-test):
  - MATERIAL accretes: a basket with a live lead + a constituent add -> a `rebalance` on that lead;
  - daily DRIFT does NOT accrete: sub-threshold weight wiggle -> no event (materiality suppresses noise);
  - accretes onto ALL live leads (xcorr AND a shadow dispersion lead on the same basket);
  - [FORK 1 violation-test] a basket whose ONLY live lead is a SHADOW dispersion lead -> the rebalance
    lands ON IT (rebalance accretes and never pages, so it corroborates burn-in leads too — the thing a
    later refactor to the non-shadow helper would silently re-sever; docs/decisions/2026-07-12-...);
  - no live lead -> recorded on `_system` (kept, not surfaced), never onto a random lead;
  - [FORK 2 violation-test a] a broken/UNPARSEABLE current feed FAULTS that basket, the run continues;
  - [FORK 2 violation-test b] a FIRST-SIGHT basket (no prior frozen pull) SEEDS silently — NO fault,
    NO event (a cold start is not a malfunction — reserve faults for a broken feed);
  - NEVER spawns: `_run_rebalance` emits no `lead.spawned`;
  - same-tick re-run is IDEMPOTENT (no double-emit);
  - and, end-to-end, it fires inside a real `run_tick` and NEVER pushes (accretion is silent).

House convention: this file builds its own deps (no shared helper module). The fine-grained forks call
`_run_rebalance` directly for control; the last test drives the whole `run_tick` to prove the wiring.
"""

import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

from prospector.config import load_config
from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.holdings import HoldingsIngest, HoldingsIngestError
from prospector.ingest.prices import PriceIngest
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_rebalance
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-14T22:30:00Z"
TODAY = "2026-07-14"
PRIOR_DATE = "2026-07-13"
T_SEED = "2026-07-10T00:00:00Z"     # seeded leads/snapshots predate the tick

S_XLK = "S000006415"               # matches the XLK holdings fixture / identity seed
S_XLU = "S000006420"


# -- SPDR holdings bodies (declared SYNTHETIC — a valid-shaped file the real parser reads) ----------

def _spdr_csv(rows):
    """A minimal but real-shaped SPDR daily CSV: preamble, the Name/Weight header, holdings, a footer.
    `rows` are (name, ticker, identifier, weight_pct, sector); `parse_spdr_holdings` sniffs CSV-vs-xlsx
    by content, so a .xlsx-named frozen file holding these bytes parses fine. SYNTHETIC fixture."""
    lines = ["The Select Sector SPDR Trust", "Fund ticker: XLK", "As of 2026-07-14", "",
             "Name,Ticker,Identifier,Weight,Sector"]
    for name, tk, ident, w, sec in rows:
        lines.append(f"{name},{tk},{ident},{w},{sec}")
    lines += ["", "Holdings are subject to change."]
    return ("\n".join(lines) + "\n").encode("utf-8")


# prior: two identified holdings. today (material): the same two + an ADD (CCC). today (drift): the two
# with only sub-threshold (0.1%) weight wiggle — no add/drop. weights stay inside the [0.5,1.5] band.
PRIOR_BODY = _spdr_csv([("Apple", "AAA", "111", "60.00", "Tech"),
                        ("Banana", "BBB", "222", "40.00", "Tech")])
TODAY_ADD_BODY = _spdr_csv([("Apple", "AAA", "111", "60.00", "Tech"),
                            ("Banana", "BBB", "222", "40.00", "Tech"),
                            ("Cherry", "CCC", "333", "5.00", "Tech")])   # +CCC -> material
TODAY_DRIFT_BODY = _spdr_csv([("Apple", "AAA", "111", "60.10", "Tech"),
                              ("Banana", "BBB", "222", "39.90", "Tech")])  # ±0.1% -> immaterial
GARBAGE_BODY = b"not,a,holdings,file\njust,some,garbage,rows\n"            # no Name/Weight header -> raises


def _mf(rows):
    return {"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}


MF_BOTH = _mf([[1001, S_XLK, "C000019213", "XLK"], [1002, S_XLU, "C000019220", "XLU"]])
MF_XLK = _mf([[1001, S_XLK, "C000019213", "XLK"]])


def _holdings(layout, *, fetch=None, clock=TODAY):
    """A HoldingsIngest whose fetch is injected (default: raise — the frozen-present tests never fetch)
    and whose clock pins pulls to `clock` (matches the live runner's tick_date wiring)."""
    def _raise(url, headers):
        raise HoldingsIngestError("no fetch fixture (frozen file expected)", status=404)
    return HoldingsIngest(layout, fetch=fetch or _raise, clock=lambda: clock)


def _freeze(hi, series_id, date, ticker, body):
    write_atomic(hi.frozen_path(series_id, date, ticker), body)


def _deps(layout, registry, hi, cfg):
    """A focused stub: `_run_rebalance` reads only cfg/registry/layout/holdings_ingest, so a namespace
    with exactly those is clearer than constructing unused edgar/price/notifier clients (the full
    RunnerDeps is exercised by the end-to-end `run_tick` test below)."""
    return SimpleNamespace(cfg=cfg, registry=registry, layout=layout, holdings_ingest=hi)


def _seed_lead(store, layout, registry, lead, *, spawner, shadow):
    """Spawn a lead and MATERIALIZE its snapshot — the state `active_incl_shadow_lead_ids` reads
    (CONTRACT §4d: the materialized fold, never a re-fold). Predated so it exists before the tick."""
    store.append({"ts": T_SEED, "lead": lead, "type": "lead.spawned",
                  "payload": {"spawner": spawner, "display": lead, "shadow": shadow}, "schema": 1})
    write_snapshot(layout, registry, lead, fold(registry.events_for_lead(lead)),
                   reason="seed", ts=T_SEED)


def _rebalances(registry, lead):
    return [json.loads(r["payload"]) for r in registry.events_for_lead(lead, "rebalance")]


def _all_rebalance_leads(registry):
    return {lead for lead in registry.all_leads()
            for _ in registry.events_for_lead(lead, "rebalance")}


def _run(layout, registry, hi, current_mf, cfg):
    """Drive `_run_rebalance` once and return (faults, runlog) for assertions."""
    store = EventStore(layout, registry, clock=lambda: NOW)
    faults, runlog = [], RunLog(run_id="t", ts=NOW, date=TODAY)
    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, faults, runlog, current_mf)
    return faults, runlog


# -- 1. material rebalance accretes onto a live lead ------------------------------------------------

def test_material_rebalance_accretes_onto_live_xcorr_lead(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)
    _freeze(hi, S_XLU, TODAY, "XLU", PRIOR_BODY)  # XLU: today only -> seeds silently (no noise)

    store = EventStore(layout, registry, clock=lambda: NOW)
    pair = xcorr_lead_id([S_XLK, S_XLU])
    _seed_lead(store, layout, registry, pair, spawner="xcorr", shadow=False)

    faults, runlog = [], RunLog(run_id="t", ts=NOW, date=TODAY)
    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, faults, runlog, MF_BOTH)

    payloads = _rebalances(registry, pair)
    assert len(payloads) == 1                      # the rebalance landed on the live lead's timeline
    assert payloads[0]["series_id"] == S_XLK and payloads[0]["as_of"] == TODAY
    assert [a["identifier"] for a in payloads[0]["adds"]] == ["333"]   # CCC, the added constituent
    assert faults == [] and runlog.sensors["rebalance"] == "ran"


# -- 2. daily drift does NOT accrete (materiality suppresses noise) ---------------------------------

def test_sub_threshold_drift_does_not_accrete(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_DRIFT_BODY)   # only ±0.1% moves, < 0.5% threshold

    store = EventStore(layout, registry, clock=lambda: NOW)
    disp = dispersion_lead_id(S_XLK)
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)

    faults, runlog = [], RunLog(run_id="t", ts=NOW, date=TODAY)
    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, faults, runlog, MF_XLK)

    assert _all_rebalance_leads(registry) == set()    # the noise did not fire a rebalance
    assert faults == [] and runlog.sensors["rebalance"] == "ran"


# -- 3. accretes onto ALL live leads: an xcorr lead AND a shadow dispersion lead --------------------

def test_accretes_onto_both_xcorr_and_shadow_dispersion_lead(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)
    _freeze(hi, S_XLU, TODAY, "XLU", PRIOR_BODY)   # XLU seeds silently

    store = EventStore(layout, registry, clock=lambda: NOW)
    pair = xcorr_lead_id([S_XLK, S_XLU])
    disp = dispersion_lead_id(S_XLK)
    _seed_lead(store, layout, registry, pair, spawner="xcorr", shadow=False)
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)

    _run_rebalance(_deps(layout, registry, hi, cfg),
                   EventStore(layout, registry, clock=lambda: NOW), NOW, [],
                   RunLog(run_id="t", ts=NOW, date=TODAY), MF_BOTH)

    assert len(_rebalances(registry, pair)) == 1    # landed on the non-shadow xcorr lead
    assert len(_rebalances(registry, disp)) == 1    # AND on the shadow dispersion lead
    assert registry.events_for_lead(SYSTEM_LEAD, "rebalance") == []   # not stranded on _system


# -- 4. [FORK 1 violation-test] a SHADOW-only basket still receives the rebalance -------------------

def test_shadow_only_lead_receives_the_rebalance(layout, registry):
    # The fork's guard: if a future change swapped active_incl_shadow_lead_ids back to the non-shadow
    # helper, EVERY other test could still pass while this one — the only lead is a shadow dispersion
    # lead — silently re-severed. Rebalance accretes and never pages, so it MUST corroborate here.
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)

    store = EventStore(layout, registry, clock=lambda: NOW)
    disp = dispersion_lead_id(S_XLK)
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)  # ONLY a shadow lead

    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, [],
                   RunLog(run_id="t", ts=NOW, date=TODAY), MF_XLK)

    assert len(_rebalances(registry, disp)) == 1     # landed ON the shadow lead, not _system
    assert registry.events_for_lead(SYSTEM_LEAD, "rebalance") == []


# -- 5. no live lead -> recorded on _system (kept, not surfaced) ------------------------------------

def test_no_live_lead_records_on_system(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)

    faults, runlog = _run(layout, registry, hi, MF_XLK, cfg)   # no leads seeded at all

    sys_rebs = [json.loads(r["payload"]) for r in registry.events_for_lead(SYSTEM_LEAD, "rebalance")]
    assert len(sys_rebs) == 1 and sys_rebs[0]["series_id"] == S_XLK   # kept on _system, not dropped
    assert faults == [] and runlog.sensors["rebalance"] == "ran"


# -- 6. [FORK 2a] a broken/unparseable current feed FAULTS that basket, the run continues -----------

def test_broken_current_feed_faults_that_basket(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", GARBAGE_BODY)     # today's frozen body is unparseable

    faults, runlog = _run(layout, registry, hi, MF_XLK, cfg)

    assert len(faults) == 1 and faults[0]["subsystem"] == "sensor.rebalance"
    assert faults[0]["category"] == "operational"      # a broken feed pages (unlike the seed case)
    assert _all_rebalance_leads(registry) == set()     # nothing accreted on a body it couldn't read


# -- 7. [FORK 2b] a first-sight basket SEEDS silently — no fault, no event (pull-if-absent path) ----

def test_first_sight_basket_seeds_silently(layout, registry):
    # No frozen file at all: rebalance PULLS today (freeze-before-parse), finds NO prior date, and
    # seeds — the append-only cold start, exactly like launch/mandate. The build-note correction: this
    # must NOT fault (faulting ~11 baskets on day one is the day-one alarm burst §10 exists to prevent).
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout, fetch=lambda url, headers: TODAY_ADD_BODY)   # pull-if-absent returns a body

    faults, runlog = _run(layout, registry, hi, MF_XLK, cfg)

    assert faults == []                                     # a cold start is not a malfunction
    assert _all_rebalance_leads(registry) == set()          # nothing to diff yet -> no event
    assert runlog.sensors["rebalance"] == "seeded"
    assert hi.frozen_path(S_XLK, TODAY, "XLK").is_file()    # today's pull WAS frozen (next tick diffs it)


# -- 8. NEVER spawns — accretion only, no lead of its own -------------------------------------------

def test_rebalance_never_spawns(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)

    store = EventStore(layout, registry, clock=lambda: NOW)
    disp = dispersion_lead_id(S_XLK)
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)
    before = sum(len(registry.events_for_lead(l, "lead.spawned")) for l in registry.all_leads())

    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, [],
                   RunLog(run_id="t", ts=NOW, date=TODAY), MF_XLK)

    after = sum(len(registry.events_for_lead(l, "lead.spawned")) for l in registry.all_leads())
    assert after == before                          # rebalance appended no lead.spawned (accretion only)
    assert len(_rebalances(registry, disp)) == 1    # it DID accrete — proving the no-spawn isn't a no-op


# -- 9. same-tick re-run is idempotent (no double-emit) --------------------------------------------

def test_same_tick_rerun_is_idempotent(layout, registry):
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_BODY)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_ADD_BODY)

    store = EventStore(layout, registry, clock=lambda: NOW)
    disp = dispersion_lead_id(S_XLK)
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)
    deps = _deps(layout, registry, hi, cfg)

    _run_rebalance(deps, store, NOW, [], RunLog(run_id="t", ts=NOW, date=TODAY), MF_XLK)
    _run_rebalance(deps, store, NOW, [], RunLog(run_id="t", ts=NOW, date=TODAY), MF_XLK)  # re-run

    assert len(_rebalances(registry, disp)) == 1    # the (series_id, as_of=today) guard held


# -- 10. frozen_dates lists ISO dates, sorted, skipping stray dirs ----------------------------------

def test_frozen_dates_lists_iso_dates_sorted(layout, registry):
    hi = _holdings(layout)
    for d, body in [("2026-07-13", PRIOR_BODY), ("2026-07-11", PRIOR_BODY), ("2026-07-14", PRIOR_BODY)]:
        _freeze(hi, S_XLK, d, "XLK", body)
    write_atomic(layout.holdings_path(S_XLK, "not-a-date", "junk.txt"), b"x")  # a stray non-ISO dir

    assert hi.frozen_dates(S_XLK) == ["2026-07-11", "2026-07-13", "2026-07-14"]   # sorted, ISO only
    assert hi.frozen_dates("S000000000") == []   # a never-pulled basket -> the first-sight seed case


# -- 11. end-to-end: it fires inside a real run_tick and NEVER pushes -------------------------------

_XLK_HOLDINGS = (Path(__file__).parent / "fixtures" / "holdings" / "XLK_2026-07-02.csv").read_bytes()


def _xlk_minus_one():
    """The real XLK fixture with its first holding row removed — so today's full file re-ADDS it, a
    material rebalance on real-shaped data (the 'prove it on the real substrate' discipline)."""
    rows = list(csv.reader(io.StringIO(_XLK_HOLDINGS.decode("utf-8-sig"))))
    hi = next(i for i, r in enumerate(rows) if {"name", "weight"} <= {c.strip().lower() for c in r})
    del rows[hi + 1]                                   # drop the first real holding
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8")


class _FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def _edgar(layout, fetch):
    clock = _FakeClock()
    return EdgarClient("Test/1.0 (test@example.com)", fetch=fetch, clock=clock,
                       sleep=lambda s: setattr(clock, "t", clock.t + s),
                       persist=lambda name, body: write_atomic(layout.edgar_path(TODAY, name), body))


def _mf_only_fetch(mf):
    body = json.dumps(mf).encode("utf-8")
    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return body
        raise EdgarError(f"no fixture for {url}", status=404)   # submissions 404 -> no interference
    return fetch


def test_rebalance_fires_in_a_full_tick_and_never_pushes(layout, registry):
    cfg, cfg_hash = load_config(CONFIG)
    # Seed yesterday's mf (so launch sees nothing new) AND yesterday's XLK holdings minus one name.
    write_atomic(layout.edgar_path(PRIOR_DATE, "company_tickers_mf.json"),
                 json.dumps(MF_BOTH).encode("utf-8"))
    hi = HoldingsIngest(layout, fetch=lambda u, h: _XLK_HOLDINGS, clock=lambda: TODAY)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", _xlk_minus_one())

    # A pre-existing active xcorr lead (materialized) the rebalance can accrete onto.
    store = EventStore(layout, registry)
    pair = xcorr_lead_id([S_XLK, S_XLU])
    _seed_lead(store, layout, registry, pair, spawner="xcorr", shadow=False)

    notifier = NullNotifier()
    deps = RunnerDeps(
        layout=layout, registry=registry, event_store=EventStore(layout, registry),
        edgar_client=_edgar(layout, _mf_only_fetch(MF_BOTH)),
        price_ingest=PriceIngest(layout, fetch=lambda u, h: json.dumps(
            [{"date": "2024-01-01T00:00:00.000Z", "close": 200.0, "adjClose": 100.0,
              "splitFactor": 1.0}]).encode("utf-8"), clock=lambda: TODAY, sleep=lambda _s: None,
            api_token="tiingo-test-token"),
        holdings_ingest=hi, notifier=notifier, cfg=cfg, cfg_hash=cfg_hash,
        now=NOW, run_id="run_rebalance_e2e", monotonic=lambda: 0.0)
    runlog = run_tick(deps)

    payloads = _rebalances(registry, pair)
    assert len(payloads) == 1 and payloads[0]["series_id"] == S_XLK   # fired within the real tick
    assert runlog.sensors["rebalance"] == "ran"
    assert runlog.pushed is False and notifier.pushes == []           # accretion is SILENT — never pages
