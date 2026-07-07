"""§9d — the deferred SOI-corroboration retry pass in the runner (spec §9b/§9d, SUBTLE BIT #3).

The test IS the gate (the discipline for §9d, the subtlest of the four bits): it must prove the pass
actually FIRES on late-arriving sectors — not merely that it is called — and three things specifically:
  1. it fires when sectors land: a launch recorded `sectors_unresolved`, its SOI arrives, the pass runs
     and accretes a `match` onto the overlapping lead (not the ∅-and-never-fires trap);
  2. it reaches back with `detected_at` preserved as T2 (the lag measures to the ORIGINAL detection,
     not to when the SOI happened to arrive);
  3. it stays dormant gracefully when the target isn't resolvable (`resolve_soi_target` -> None): the
     launch stays `sectors_unresolved`, is re-attempted next cycle, and the run continues (§9g).

Plus the §9f enumeration property: the work-list is FOLDED from the launch events (a later `match`
supersedes the `sectors_unresolved`, so a resolved launch drops off), never a side table.

Offline: the EdgarClient fetch is injected over in-memory fixtures + the real frozen TEKX SOI; the
socket guard (conftest) fails any real connection.
"""

import json
from datetime import timedelta
from pathlib import Path

from prospector.config import load_config
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.prices import PriceIngest
from prospector.primitives.atomic import write_atomic
from prospector.runner.deps import RunnerDeps
from prospector.runner.notify import NullNotifier
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_soi_corroboration
from prospector.sensors.launch_corroboration import cross_stream_lag, pending_soi_resolution
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry

CONFIG = Path("config") / "prospector.yaml"
FIX = Path(__file__).parent / "fixtures" / "soi"
JUL2025 = (FIX / "tekx_soi_2025-07-31.htm").read_bytes()

NOW = "2025-08-15T22:30:00Z"         # a plausible resolution time — shortly after the SOI posts, and
                                     # within the retry horizon of DETECTED (~340 days < 365)
SPAWN = "2023-01-25T00:00:00Z"       # T1 — the structural (xcorr) lead's birth
DETECTED = "2024-09-09T00:00:00Z"    # T2 — the launch's ORIGINAL detection (preserved through §9d)

# Real TEKX SOI coordinates (see tests/fixtures/soi/*.source.txt).
TEKX_SID, TEKX_CIK = "S000087749", 1516212
ACCESSION, SOI_DOC = "0001410368-25-011151", "NPORT_J9C7_54705771_0725.htm"
# The anchor (entry.name) MUST be a stable unique STEM, never a dated title (§9b): TEKX was "SPDR
# Galaxy…" in the Jul-2025 filing and "State Street Galaxy…" later, so key on the stem that survives.
ANCHOR = "Transformative Tech Accelerators"
# Sector-ETF universe series (only two need registering for the XLK×XLU pair the launch overlaps).
S_XLK, S_XLU = "S000006415", "S000006417"
PAIR = xcorr_lead_id([S_XLK, S_XLU])

SUBS_URL = f"https://data.sec.gov/submissions/CIK{TEKX_CIK:010d}.json"
INDEX_URL = (f"https://www.sec.gov/Archives/edgar/data/{TEKX_CIK}/"
             f"{ACCESSION.replace('-', '')}/index.json")
DOC_URL = (f"https://www.sec.gov/Archives/edgar/data/{TEKX_CIK}/"
           f"{ACCESSION.replace('-', '')}/{SOI_DOC}")


def _entry(series_id, ticker, cik, name):
    return FundEntry(series_id=series_id, class_ids=[], cik=cik, ticker_current=ticker,
                     name=name, issuer="SSGA Active Trust", category_draft=None,
                     concentration_industries=[], prospectus_accession="0001-25-1",
                     holdings_source="issuer_daily", first_seen=DETECTED, verified_at=DETECTED)


def _subs(rows):
    forms, dates, accs, docs = ([r[i] for r in rows] for i in range(4))
    return {"name": "SSGA Active Trust", "filings": {"recent": {
        "form": forms, "filingDate": dates, "accessionNumber": accs, "primaryDocument": docs}}}


def _soi_fetch(*, subs_rows, index_names, serve_doc=True):
    """An EdgarClient fetch closure serving submissions + accession index + the SOI document."""
    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs(subs_rows)).encode()
        if url == INDEX_URL:
            return json.dumps({"directory": {"item": [{"name": n} for n in index_names]}}).encode()
        if url == DOC_URL and serve_doc:
            return JUL2025
        raise EdgarError(f"no fixture for {url}", status=404)
    return fetch


def _edgar(layout, fetch):
    t = {"v": 0.0}
    return EdgarClient("Test/1.0 (test@example.com)", fetch=fetch, clock=lambda: t["v"],
                       sleep=lambda s: t.__setitem__("v", t["v"] + s),
                       persist=lambda name, body: write_atomic(layout.edgar_path(NOW[:10], name), body))


def _deps(layout, registry, event_store, fetch):
    cfg, cfg_hash = load_config(CONFIG)
    return RunnerDeps(layout=layout, registry=registry, event_store=event_store,
                      edgar_client=_edgar(layout, fetch),
                      price_ingest=PriceIngest(layout, fetch=lambda url, headers: b""),  # inert: _run_soi_corroboration never builds the panel
                      notifier=NullNotifier(),
                      cfg=cfg, cfg_hash=cfg_hash, now=NOW, run_id="run_test",
                      monotonic=lambda: 0.0)


def _seed(layout, registry, event_store, *, detected_at=DETECTED, spawn=True):
    """Seed the fossil record: sector-ETF + TEKX registry entries, an active xcorr lead, and a launch
    already recorded `sectors_unresolved` (as the holdings corroboration pass would emit it)."""
    funds = FundRegistry(layout, registry, event_store, clock=lambda: NOW)
    funds.upsert(_entry(S_XLK, "XLK", 1001, "Tech Select"))
    funds.upsert(_entry(S_XLU, "XLU", 1002, "Utilities Select"))
    funds.upsert(_entry(TEKX_SID, "TEKX", TEKX_CIK, ANCHOR))
    if spawn:
        event_store.append({"ts": SPAWN, "lead": PAIR, "type": "lead.spawned",
                            "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False},
                            "schema": 1})
    event_store.append({"ts": detected_at, "lead": SYSTEM_LEAD, "type": "launch",
                        "payload": {"series_id": TEKX_SID, "ticker": "TEKX",
                                    "detected_at": detected_at, "unverified_ref": "u1",
                                    "concentration_sectors": [], "corroboration": "sectors_unresolved"},
                        "schema": 1})
    return funds


# === §9f enumeration: the work-list is folded from the events, resolved launches drop off ==========

def test_pending_soi_resolution_folds_the_worklist_and_supersedes():
    da = "2026-07-01T00:00:00Z"
    unresolved = {"ts": da, "event_id": "a", "payload": {"series_id": "S1", "detected_at": da,
                                                         "corroboration": "sectors_unresolved"}}
    # A later `match` on a lead SUPERSEDES the _system sectors_unresolved -> S1 drops off the work-list.
    resolved = {"ts": "2026-07-05T00:00:00Z", "event_id": "b",
                "payload": {"series_id": "S1", "detected_at": da, "corroboration": "match"}}
    # A resolved-launch record (register_launch's launch, no `corroboration` field) is never pending.
    recorded = {"ts": da, "event_id": "c", "payload": {"series_id": "S2", "detected_at": da}}
    assert [p["series_id"] for p in pending_soi_resolution([unresolved], NOW, 180)] == ["S1"]
    assert pending_soi_resolution([unresolved, resolved], NOW, 180) == []
    assert pending_soi_resolution([recorded], NOW, 180) == []


def test_pending_soi_resolution_ages_out_past_the_horizon():
    old = "2020-01-01T00:00:00Z"  # far older than 180 days before NOW
    ev = {"ts": old, "event_id": "a", "payload": {"series_id": "S1", "detected_at": old,
                                                  "corroboration": "sectors_unresolved"}}
    assert pending_soi_resolution([ev], NOW, 180) == []          # aged out -> dormant-terminal
    assert [p["series_id"] for p in pending_soi_resolution([ev], NOW, 100_000)] == ["S1"]  # wide horizon


# === Property 1 + 2: it FIRES when sectors land, reaching back with detected_at preserved as T2 =====

def test_soi_corroboration_fires_when_sectors_land_and_preserves_t2(layout, registry):
    event_store = EventStore(layout, registry)
    funds = _seed(layout, registry, event_store)
    deps = _deps(layout, registry, event_store,
                 _soi_fetch(subs_rows=[("NPORT-EX", "2025-08-01", ACCESSION, "primary_doc.xml")],
                            index_names=["primary_doc.xml", SOI_DOC, f"{ACCESSION}-index.htm"]))
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_soi_corroboration(deps, event_store, NOW, faults, runlog, funds)

    # 1. It fired: a `match` accreted onto the overlapping XLK×XLU lead (not ∅-and-never-fires).
    matches = [e for e in event_store.read_lead(PAIR, "launch")
               if e.payload.get("corroboration") == "match"]
    assert len(matches) == 1, "the SOI pass must accrete a match onto the overlapping lead"
    assert matches[0].payload["series_id"] == TEKX_SID
    assert matches[0].payload["soi_accession"] == ACCESSION       # resolved via resolve_soi_target
    # 2. It reached back: detected_at preserved as T2 (the lag measures to detection, not SOI arrival).
    assert matches[0].payload["detected_at"] == DETECTED
    lead_events = [{"type": "lead.spawned", "ts": SPAWN},
                   *({"type": "launch", "ts": e.ts, "payload": e.payload}
                     for e in event_store.read_lead(PAIR, "launch"))]
    assert cross_stream_lag(lead_events) == timedelta(days=593)   # T2(2024-09-09) − T1(2023-01-25)
    # The launch drops off the work-list now that it's resolved (§9f supersession).
    remaining = [{"ts": r["ts"], "event_id": r["event_id"], "payload": json.loads(r["payload"])}
                 for lead in registry.all_leads() for r in registry.events_for_lead(lead, "launch")]
    assert pending_soi_resolution(remaining, NOW, 180) == []
    assert faults == [] and runlog.sensors["soi_corroboration"] == "ran"


# === Property 3: it stays dormant GRACEFULLY when the target isn't resolvable (not-yet) =============

def test_soi_corroboration_stays_dormant_when_soi_not_indexed_yet(layout, registry):
    event_store = EventStore(layout, registry)
    funds = _seed(layout, registry, event_store)
    # Submissions carry NO SOI-family form yet (EDGAR hasn't indexed the NPORT-EX) -> resolve_soi_target
    # returns None. The pass must leave the launch sectors_unresolved and continue (a not-yet, §9d).
    deps = _deps(layout, registry, event_store,
                 _soi_fetch(subs_rows=[("485BPOS", "2024-09-01", "0001-24-1", "p.htm")],
                            index_names=[]))
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_soi_corroboration(deps, event_store, NOW, faults, runlog, funds)

    assert [e for e in event_store.read_lead(PAIR, "launch")] == []   # nothing accreted
    # The launch is STILL pending — re-attempted next cycle, not lost, not faulted.
    remaining = [{"ts": r["ts"], "event_id": r["event_id"], "payload": json.loads(r["payload"])}
                 for lead in registry.all_leads() for r in registry.events_for_lead(lead, "launch")]
    assert [p["series_id"] for p in pending_soi_resolution(remaining, NOW, 365)] == [TEKX_SID]
    assert faults == [] and runlog.sensors["soi_corroboration"] == "ran"  # a not-yet is not a fault


def test_soi_corroboration_dormant_no_match_when_no_live_lead(layout, registry):
    # SOI resolves reliably, but there is NO active lead to overlap (xcorr/dispersion are their own
    # SLOTs): the launch is recorded dormant_no_match on _system, honestly — never a phantom match.
    event_store = EventStore(layout, registry)
    funds = _seed(layout, registry, event_store, spawn=False)  # no structural lead
    deps = _deps(layout, registry, event_store,
                 _soi_fetch(subs_rows=[("NPORT-EX", "2025-08-01", ACCESSION, "primary_doc.xml")],
                            index_names=["primary_doc.xml", SOI_DOC, f"{ACCESSION}-index.htm"]))
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_soi_corroboration(deps, event_store, NOW, faults, runlog, funds)

    dormant = [e for e in event_store.read_system("launch")
               if e.payload.get("corroboration") == "dormant_no_match"]
    assert len(dormant) == 1 and dormant[0].payload["detected_at"] == DETECTED
    assert faults == []


# === Soft fault: a per-launch failure is recorded and the pass goes on (§9g) ========================

def test_soi_corroboration_per_launch_failure_is_a_soft_fault(layout, registry):
    event_store = EventStore(layout, registry)
    funds = _seed(layout, registry, event_store)
    # resolve_soi_target succeeds, but the document fetch (fetch_body) 500s inside soi.scan -> a soft
    # fault on _system; the pass records it and continues (never a run-abort).
    def fetch(url, headers):
        if url == SUBS_URL:
            return json.dumps(_subs([("NPORT-EX", "2025-08-01", ACCESSION, "primary_doc.xml")])).encode()
        if url == INDEX_URL:
            return json.dumps({"directory": {"item": [
                {"name": "primary_doc.xml"}, {"name": SOI_DOC},
                {"name": f"{ACCESSION}-index.htm"}]}}).encode()
        raise EdgarError("edgar down", status=500)  # the SOI document fetch fails

    deps = _deps(layout, registry, event_store, fetch)
    faults, runlog = [], RunLog(run_id="r", ts=NOW, date=NOW[:10])

    _run_soi_corroboration(deps, event_store, NOW, faults, runlog, funds)

    assert any(f["subsystem"] == "soi.corroboration" for f in faults)
    assert [e for e in event_store.read_lead(PAIR, "launch")] == []  # no match on the fetch failure
