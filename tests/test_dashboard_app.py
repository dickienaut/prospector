"""Headless render smoke for the §11 Streamlit shell (app.py). SKIPPED unless the `dashboard` extra is
installed — streamlit is optional; the view-models (test_dashboard_views) carry the tested logic. This
guards the thin render layer against a regression that unit tests can't see: it runs app.py end-to-end
against a real store and asserts every panel renders with no exception. Offline: AppTest is headless (no
server, no socket); usage-stats telemetry is disabled so the network guard stays satisfied."""

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

from prospector.identity.resolution import ResolutionMachine
from prospector.runner.runlog import RunLog, write_run_log
from prospector.store.event_store import EventStore


def test_app_renders_all_panels_against_a_store(layout, registry, monkeypatch):
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    # N1 fix precondition: a read-only viewer cannot create working tables, so seed them the way a
    # runner tick does (resolution_queue via the ResolutionMachine _run_sensors constructs; runs via
    # write_run_log) while the fixture store is still writable — else the read-only dashboard would hit
    # `no such table: resolution_queue`. (The old smoke passed only because the buggy read-write viewer
    # created the table on the fly — a test that passed for the wrong reason.)
    ResolutionMachine(registry, EventStore(layout, registry), None, None)
    store = EventStore(layout, registry)
    # A live xcorr lead + a dormant launch + a fault + a run-log: something in every panel.
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "xcorr-abc1234567", "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:01Z", "lead": "xcorr-abc1234567", "type": "xcorr.departure",
                  "payload": {"display": "XLK×XLU", "z": 3.2, "market_stress": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "_system", "type": "launch.unverified",
                  "payload": {"ticker": "NEWX", "series_id": "S000000009",
                              "detected_at": "2026-07-06T00:00:00Z"}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "_system", "type": "fault",
                  "payload": {"subsystem": "sensor.xcorr", "message": "demo"}, "schema": 1})
    write_run_log(layout, registry, RunLog(run_id="r1", ts="2026-07-06T00:00:00Z",
                                           date="2026-07-06", pushed=True))
    monkeypatch.setenv("PROSPECTOR_STORE", str(layout.root))

    at = st_testing.AppTest.from_file("prospector/dashboard/app.py").run(timeout=60)

    assert not at.exception                                      # every panel rendered cleanly
    headers = [h.value for h in at.header]
    assert "Active leads" in headers and "Coverage / dormant pile" in headers
    assert any(m.label == "Heartbeat" for m in at.metric)       # the live xcorr lead surfaced
