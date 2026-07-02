"""Spec §10 test 2 — the failed-resolution path, scripted end to end from
tests/fixtures/resolution_failure.json. Detection day D: `launch.unverified` on `_system`
(ticker-only, `detected_at`) and `resolution.failed` land in the record, the queue row goes
'retrying'. Days D+1..D+10: daily retries increment attempts. Day D+11: escalation to the
manual queue — itself an event. Manual resolve then completes the two-phase launch with the
ORIGINAL `detected_at` and the `launch.unverified` back-reference (lag integrity, CONTRACT
§4c), and `launch_lag` provably reads only `detected_at`."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

import prospector.cli.main as cli_main
from prospector.identity.resolution import ResolutionMachine, VerificationError, launch_lag
from prospector.ingest.edgar import (MF_TICKERS_URL, EdgarClient, EdgarError,
                                     ResolutionFailure, resolve_ticker)
from prospector.store.envelope import SYSTEM_LEAD, parse_ts
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundRegistry, IdentityError

FIXTURES = Path(__file__).parent / "fixtures"
EDGAR = FIXTURES / "edgar"
SCENARIO = json.loads((FIXTURES / "resolution_failure.json").read_text(encoding="utf-8"))

UA = "Prospector-tests/1.0 (lyle.e.dickie@gmail.com)"

_FIXTURE_BY_URL = {
    MF_TICKERS_URL: "company_tickers_mf.json",
    "https://data.sec.gov/submissions/CIK0001516212.json": "heco_submissions.json",
    "https://data.sec.gov/submissions/CIK0001064641.json": "sectors_submissions.json",
}


def fixture_fetch(url, headers):
    if url not in _FIXTURE_BY_URL:
        raise EdgarError(f"no fixture for {url}", status=404)
    return (EDGAR / _FIXTURE_BY_URL[url]).read_bytes()


def make_client(fetch=fixture_fetch):
    """Fixture-backed client with a fake monotonic clock — no real waiting, no sockets."""
    mono = {"t": 0.0}

    def sleep(seconds):
        mono["t"] += seconds

    return EdgarClient(UA, fetch=fetch, clock=lambda: mono["t"], sleep=sleep)


class IsoClock:
    """Advancing UTC clock the scenario script moves day by day."""

    def __init__(self, start: str):
        self._now = parse_ts(start)

    def __call__(self) -> str:
        return self._now.isoformat(timespec="seconds").replace("+00:00", "Z")

    def advance(self, **delta) -> None:
        self._now += timedelta(**delta)


@pytest.fixture
def clock():
    return IsoClock(SCENARIO["detected_at"])


@pytest.fixture
def event_store(layout, registry, clock):
    return EventStore(layout, registry, clock=clock)


@pytest.fixture
def funds(layout, registry, event_store, clock):
    return FundRegistry(layout, registry, event_store, clock=clock)


@pytest.fixture
def machine(registry, event_store, funds, clock):
    return ResolutionMachine(registry, event_store, funds, make_client(),
                             retry_days=10, clock=clock)


def _detect(event_store, machine, clock):
    """Day D: the two-phase launch's first phase (§4c) plus the recorded failure (§2)."""
    unverified = event_store.append({
        "ts": clock(), "lead": SYSTEM_LEAD, "type": "launch.unverified",
        "payload": {"ticker": SCENARIO["ticker"], "name_raw": SCENARIO["name_raw"],
                    "detected_at": SCENARIO["detected_at"]},
        "schema": 1})
    failure = resolve_ticker(SCENARIO["ticker"], machine.edgar_client)
    assert isinstance(failure, ResolutionFailure)
    assert failure.reason == "not_in_mf_map"
    machine.record_failure(failure.ticker, failure.reason, failure.detail,
                           detected_at=SCENARIO["detected_at"],
                           unverified_event_id=unverified.event_id)
    return unverified


# -- the scripted scenario (spec test 2) -------------------------------------------------

def test_detection_retries_escalation_then_manual_resolution(machine, event_store, funds,
                                                             clock):
    unverified = _detect(event_store, machine, clock)

    # Day D: the failure is IN the record — countable, never silent.
    (failed,) = event_store.read_system(type="resolution.failed")
    assert failed.payload["ticker"] == "ZZZQ"
    assert failed.payload["reason"] == "not_in_mf_map"
    assert failed.payload["detail"]
    row = machine.queue_row("ZZZQ")
    assert row["status"] == "retrying"
    assert row["attempts"] == 1
    assert row["first_failed_at"] == SCENARIO["detected_at"]

    # Days D+1..D+10: daily retries; EDGAR still hasn't indexed ZZZQ.
    for day in range(1, 11):
        clock.advance(days=1)
        out = machine.run_retries()
        assert out == {"resolved": [], "retrying": ["ZZZQ"], "escalated": []}
        row = machine.queue_row("ZZZQ")
        assert row["status"] == "retrying"
        assert row["attempts"] == 1 + day
        assert row["last_attempt_at"] == clock()
    assert machine.manual_queue() == []
    # Retries are queue-row bookkeeping, not new failure events.
    assert len(event_store.read_system(type="resolution.failed")) == 1

    # Day D+11: the retry window (10 days) has lapsed — escalation, itself in the record.
    clock.advance(days=1)
    out = machine.run_retries()
    assert out == {"resolved": [], "retrying": [], "escalated": ["ZZZQ"]}
    first, second = event_store.read_system(type="resolution.failed")
    assert second.payload == {"ticker": "ZZZQ", "stage": "manual_queue"}
    (queued,) = machine.manual_queue()
    assert queued["ticker"] == "ZZZQ"
    assert queued["status"] == "manual"

    # The human resolves via the fixture's series id (EDGAR-verifiable against fixtures).
    entry = machine.resolve_manual(SCENARIO["ticker"],
                                   SCENARIO["manual_resolution"]["series_id"],
                                   note=SCENARIO["manual_resolution"]["note"])
    assert entry.series_id == "S000087750"
    assert entry.ticker_current == "ZZZQ"
    assert entry.first_seen == SCENARIO["detected_at"]  # the ORIGINAL datum, not resolve day
    assert funds.get("S000087750") == entry  # registry keyed on the series id

    (resolved,) = event_store.read_system(type="identity.resolved")
    assert resolved.payload == {"ticker": "ZZZQ", "series_id": "S000087750",
                                "method": "manual"}

    # The completing launch back-references detection: ORIGINAL detected_at + unverified_ref
    # (lag integrity, CONTRACT §4c) — while its envelope ts is resolution day, eleven days on.
    (launch,) = event_store.read_system(type="launch")
    assert launch.payload["detected_at"] == SCENARIO["detected_at"]
    assert launch.payload["unverified_ref"] == unverified.event_id
    assert launch.payload["series_id"] == "S000087750"
    assert launch.payload["ticker"] == "ZZZQ"
    assert launch.payload["category_draft"] is None
    assert launch.payload["concentration_industries"] == []
    assert launch.ts == clock() != SCENARIO["detected_at"]

    row = machine.queue_row("ZZZQ")
    assert row["status"] == "resolved"
    assert row["resolved_series_id"] == "S000087750"
    assert row["note"] == SCENARIO["manual_resolution"]["note"]
    assert machine.manual_queue() == []


def test_repeat_failure_keeps_first_failed_at(machine, event_store, clock):
    machine.record_failure("ZZZQ", "not_in_mf_map", "absent")
    clock.advance(days=2)
    machine.record_failure("ZZZQ", "http_error", "edgar down",
                           detected_at=SCENARIO["detected_at"])
    row = machine.queue_row("ZZZQ")
    assert row["first_failed_at"] == SCENARIO["detected_at"]  # the window counts from day one
    assert row["last_attempt_at"] == clock()
    assert row["attempts"] == 2
    assert row["detected_at"] == SCENARIO["detected_at"]  # a late detected_at still lands
    assert len(event_store.read_system(type="resolution.failed")) == 2


# -- lag math reads detected_at ONLY (lag-integrity CONTRACT §4c) --------------------------

def test_launch_lag_reads_detected_at_and_nothing_else():
    payload = {"detected_at": SCENARIO["detected_at"],  # 2026-07-02T13:00:00Z
               "ts": "2026-07-13T13:00:00Z"}  # a decoy resolution-time field, never read
    lag = launch_lag("2026-06-02T13:00:00Z", payload)
    # T(structural) -> T(launch): detection 30 days after the structural firing.
    assert lag == timedelta(days=30)
    # The natural direction signs itself: a launch detected BEFORE the structural ts is
    # negative lag, not a swapped subtraction.
    assert launch_lag("2026-07-04T13:00:00Z", payload) == timedelta(days=-2)


def test_launch_lag_raises_keyerror_without_detected_at():
    with pytest.raises(KeyError):
        launch_lag("2026-06-02T13:00:00Z", {"ticker": "ZZZQ",
                                            "ts": "2026-07-13T13:00:00Z"})


# -- manual resolution is validated AND verified (no bypass in v1) --------------------------

def test_resolve_manual_rejects_malformed_series_id(machine, registry, funds):
    with pytest.raises(IdentityError):
        machine.resolve_manual("ZZZQ", "ZZZQ")  # a bare ticker where a series id belongs
    with pytest.raises(IdentityError):
        machine.resolve_manual("ZZZQ", "S12")
    assert registry.event_count() == 0
    assert funds.all_funds() == []


def test_resolve_manual_verifies_series_exists_on_edgar(machine, registry, funds):
    with pytest.raises(VerificationError):
        machine.resolve_manual("ZZZQ", "S000000001")  # well-formed, absent from the MF map
    assert registry.event_count() == 0
    assert funds.all_funds() == []


def test_resolve_manual_verifies_prospectus_filing(registry, event_store, funds, clock):
    def no_prospectus_fetch(url, headers):
        if url == "https://data.sec.gov/submissions/CIK0001516212.json":
            return json.dumps({
                "cik": "0001516212", "name": "SSGA Active Trust",
                "filings": {"recent": {"accessionNumber": ["0001193125-26-000001"],
                                       "filingDate": ["2026-05-01"], "form": ["NPORT-P"],
                                       "primaryDocument": ["doc.xml"]}}}).encode("utf-8")
        return fixture_fetch(url, headers)

    machine = ResolutionMachine(registry, event_store, funds,
                                make_client(no_prospectus_fetch), clock=clock)
    with pytest.raises(VerificationError):
        machine.resolve_manual("ZZZQ", "S000087750")
    assert registry.event_count() == 0
    assert funds.all_funds() == []


# -- the CLI surface over the same queue (spec §8c) ------------------------------------------

def test_cli_queue_and_resolve_complete_the_pending_launch(machine, event_store, clock,
                                                           store_root, monkeypatch):
    unverified = _detect(event_store, machine, clock)
    clock.advance(days=11)
    machine.run_retries()  # escalate to the manual queue
    monkeypatch.setattr(cli_main, "_client_factory", make_client)  # offline seam, no env vars
    runner = CliRunner()

    queued = runner.invoke(cli_main.cli, ["identity", "queue", "--store", str(store_root)])
    assert queued.exit_code == 0, queued.output
    assert queued.output.startswith("ZZZQ\t")
    assert SCENARIO["detected_at"] in queued.output

    resolved = runner.invoke(cli_main.cli, [
        "identity", "resolve", "ZZZQ", "--series-id", "S000087750",
        "-m", "resolved from the heartbeat queue", "--store", str(store_root)])
    assert resolved.exit_code == 0, resolved.output
    assert "ZZZQ -> S000087750" in resolved.output

    # The CLI path is the same machine: original detected_at + back-reference preserved.
    (launch,) = event_store.read_system(type="launch")
    assert launch.payload["detected_at"] == SCENARIO["detected_at"]
    assert launch.payload["unverified_ref"] == unverified.event_id
    (resolved_event,) = event_store.read_system(type="identity.resolved")
    assert resolved_event.payload["method"] == "manual"
    assert machine.queue_row("ZZZQ")["status"] == "resolved"

    emptied = runner.invoke(cli_main.cli, ["identity", "queue", "--store", str(store_root)])
    assert emptied.exit_code == 0, emptied.output
    assert emptied.output.strip() == ""


def test_cli_resolve_rejects_an_unverifiable_series_id(machine, event_store, clock,
                                                       store_root, monkeypatch):
    _detect(event_store, machine, clock)
    monkeypatch.setattr(cli_main, "_client_factory", make_client)
    runner = CliRunner()
    result = runner.invoke(cli_main.cli, [
        "identity", "resolve", "ZZZQ", "--series-id", "S000000001",
        "--store", str(store_root)])
    assert result.exit_code != 0
    assert "cannot verify" in result.output
    assert event_store.read_system(type="identity.resolved") == []


def test_cli_queue_on_absent_store_neither_crashes_nor_creates(tmp_path):
    absent = tmp_path / "nope"
    runner = CliRunner()
    result = runner.invoke(cli_main.cli, ["identity", "queue", "--store", str(absent)])
    assert result.exit_code == 0, result.output
    assert not absent.exists()  # a read surface must not conjure a store
