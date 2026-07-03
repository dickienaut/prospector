"""Launch sensor (spec §4c, milestone 4 — detection + two-phase recording).

The MF-ticker-map diff surfaces new registrations; each is recorded two-phase
(`launch.unverified` -> resolve -> `launch` | retry queue) with the detection timestamp nailed
BEFORE resolution, so a late resolution never moves the launch datum (lag integrity §4c). Every
unverified detection lands on `_system`, keying no lead. The corroboration hook and
holdings-derived concentration are the deferred next slice
(docs/decisions/2026-07-03-launch-sensor-capture-first.md) — this slice is the capture backbone."""

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from prospector.identity.resolution import ResolutionMachine, launch_lag
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.sensors.launch import new_registrations, scan
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundRegistry

FIXTURES = Path(__file__).parent / "fixtures"
EDGAR = FIXTURES / "edgar"
MF = json.loads((EDGAR / "company_tickers_mf.json").read_text(encoding="utf-8"))

UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"
NOW = "2026-07-03T12:00:00Z"  # one scan pass = one detection moment

_FIXTURE_BY_URL = {
    MF_TICKERS_URL: "company_tickers_mf.json",
    "https://data.sec.gov/submissions/CIK0001516212.json": "heco_submissions.json",
    "https://data.sec.gov/submissions/CIK0001064641.json": "sectors_submissions.json",
}


def fixture_fetch(url, headers):
    if url not in _FIXTURE_BY_URL:
        raise EdgarError(f"no fixture for {url}", status=404)
    return (EDGAR / _FIXTURE_BY_URL[url]).read_bytes()


def make_client():
    """Fixture-backed client with a fake monotonic clock — no real waiting, no sockets."""
    mono = {"t": 0.0}
    return EdgarClient(UA, fetch=fixture_fetch, clock=lambda: mono["t"],
                       sleep=lambda s: mono.__setitem__("t", mono["t"] + s))


@pytest.fixture
def event_store(layout, registry):
    return EventStore(layout, registry, clock=lambda: NOW)


@pytest.fixture
def funds(layout, registry, event_store):
    return FundRegistry(layout, registry, event_store, clock=lambda: NOW)


@pytest.fixture
def machine(registry, event_store, funds):
    return ResolutionMachine(registry, event_store, funds, make_client(),
                             retry_days=10, clock=lambda: NOW)


def _without(mf, symbol):
    """A snapshot with `symbol`'s row dropped — the 'prior' pull before that fund appeared."""
    out = copy.deepcopy(mf)
    idx = {f: i for i, f in enumerate(out["fields"])}
    out["data"] = [r for r in out["data"] if str(r[idx["symbol"]]).upper() != symbol]
    return out


def _with_extra(mf, row):
    out = copy.deepcopy(mf)
    out["data"] = out["data"] + [row]
    return out


# -- detection: the snapshot diff IS the new-registration signal ------------------------------

def test_new_registrations_are_exactly_the_added_pairs():
    added = new_registrations(MF, _without(MF, "HECO"))
    assert added == [("HECO", "S000087750")]   # State Street Galaxy — the reused ticker's new series
    assert new_registrations(MF, MF) == []      # nothing changed -> nothing flagged
    # A pair already present is never re-flagged, only genuinely new ones.
    assert all(sym != "XLK" for sym, _ in new_registrations(MF, _without(MF, "HECO")))


# -- immediate resolution: a resolvable new fund is recorded and completed in one pass --------

def test_scan_records_then_immediately_resolves_a_known_fund(machine, event_store, funds,
                                                             registry):
    out = scan(MF, _without(MF, "HECO"), machine, NOW)
    assert out == {"resolved": ["HECO"], "queued": []}

    # Phase one: the detection timestamp is in the record on _system, keying no lead.
    (unv,) = event_store.read_system(type="launch.unverified")
    assert unv.payload == {"ticker": "HECO", "name_raw": None, "detected_at": NOW}
    assert unv.ts == NOW
    (unv_row,) = registry.events_for_lead(SYSTEM_LEAD, "launch.unverified")

    # Phase two: resolved immediately -> identity.resolved(auto) + the completing launch.
    (resolved,) = event_store.read_system(type="identity.resolved")
    assert resolved.payload == {"ticker": "HECO", "series_id": "S000087750", "method": "auto"}
    (launch,) = event_store.read_system(type="launch")
    assert launch.payload["ticker"] == "HECO"
    assert launch.payload["series_id"] == "S000087750"
    assert launch.payload["detected_at"] == NOW                  # the ORIGINAL detection datum
    assert launch.payload["unverified_ref"] == unv_row["event_id"]   # back-reference to phase one
    assert launch.payload["concentration_industries"] == []     # holdings-derived: deferred slice

    # Registry keyed on the series id; no failure, nothing queued.
    assert funds.get("S000087750") is not None
    assert event_store.read_system(type="resolution.failed") == []
    assert machine.manual_queue() == []


# -- unresolvable new fund: recorded now, verification parked in the retry queue --------------

def test_scan_records_then_queues_an_unresolvable_fund(machine, event_store):
    ghost = [9999, "S000099999", "C000099999", "ZZZQ"]  # absent from the fixture MF map
    out = scan(_with_extra(MF, ghost), MF, machine, NOW)
    assert out == {"resolved": [], "queued": ["ZZZQ"]}

    # The timestamp is already safe even though verification could not complete.
    (unv,) = event_store.read_system(type="launch.unverified")
    assert unv.payload["ticker"] == "ZZZQ" and unv.payload["detected_at"] == NOW
    (failed,) = event_store.read_system(type="resolution.failed")
    assert failed.payload["ticker"] == "ZZZQ"
    assert failed.payload["reason"] == "not_in_mf_map"
    assert event_store.read_system(type="launch") == []          # no launch until it verifies
    row = machine.queue_row("ZZZQ")
    assert row["status"] == "retrying"
    assert row["detected_at"] == NOW                             # the datum rides into the queue


# -- lag integrity: the completing launch's datum is detected_at, read by launch_lag ----------

def test_cross_stream_lag_reads_the_detection_datum(machine, event_store):
    scan(MF, _without(MF, "HECO"), machine, NOW)
    (launch,) = event_store.read_system(type="launch")
    # A structural firing 90 days before the launch -> +90d, the packaging-follows-structure lag.
    assert launch_lag("2026-04-04T12:00:00Z", launch.payload) == timedelta(days=90)


# -- a cold scan (empty prior) would flag the whole universe — the runner must seed the prior --

def test_cold_scan_flags_everything_a_reminder_to_seed_the_prior_snapshot():
    # Documents the one sharp edge: new_registrations against an empty prior is the whole map,
    # which is why the runner freezes a seed snapshot at deploy rather than scanning cold (§9).
    empty = {"fields": MF["fields"], "data": []}
    assert len(new_registrations(MF, empty)) == len(MF["data"])
