"""§8b board-snapshot export — the pure markdown serialization layer (spec §8b/§11, design doc
2026-07-10-8b). Offline: no streamlit, no socket (the conftest network guard fails any real connection),
no fetch, no sensor — the export is a pure read of the stored folds.

The gate (doc §6): pure-read/no-recompute, no-drift-from-the-view-models, a correct self-describing
manifest, active = all-active INCLUDING shadow (reverted excluded), tick-collapse, and the filenames.
"""

from pathlib import Path

from prospector.dashboard import export, views
from prospector.identity.resolution import ResolutionMachine
from prospector.runner.runlog import RunLog, recent_runs, write_run_log
from prospector.store.event_store import EventStore
from prospector.store.registry import Registry

NOW = "2026-07-07T00:00:00Z"

LIVE = "xcorr-live000001"      # active, non-shadow (spawn + departure + ticks + verdict)
SHADOW = "disp-shadow0001"     # active, SHADOW dispersion (spawn + ticks)
REVERTED = "xcorr-revert001"   # reverted — must NOT appear in the report at all (the bound)


def _cfg(ceiling: int = 8, shadow_days: int = 90) -> dict:
    return {"oracle": {"active_lead_ceiling": ceiling}, "dispersion": {"shadow_days": shadow_days}}


def _seed(layout, registry) -> None:
    """A production-faithful seed: the working tables (resolution_queue via ResolutionMachine, runs via
    write_run_log) + a live lead with a tick run + a shadow dispersion lead + a reverted lead + a dormant
    launch + a fault + two runs with DIFFERENT config hashes (so config_changed is derivable)."""
    ResolutionMachine(registry, EventStore(layout, registry), None, None)  # creates resolution_queue
    store = EventStore(layout, registry)

    # A recent heartbeat.sent (M7-01): the dead-man's liveness now keys on this, not the last run, so the
    # manifest reads "heartbeat: OK" only when a heartbeat was actually sent within the floor.
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "_system", "type": "heartbeat.sent",
                  "payload": {"trigger": "cadence"}, "schema": 1})

    # A LIVE xcorr lead: spawn -> departure -> five silent ticks -> a verdict (still active, non-shadow).
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": LIVE, "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:01Z", "lead": LIVE, "type": "xcorr.departure",
                  "payload": {"display": "XLK×XLU", "z": 3.2, "market_stress": False}, "schema": 1})
    for i, z in enumerate((3.1, 3.0, 2.9, 2.8, 2.7)):
        store.append({"ts": f"2026-07-06T00:01:0{i}Z", "lead": LIVE, "type": "xcorr.tick",
                      "payload": {"z": z, "market_stress": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:02:00Z", "lead": LIVE, "type": "verdict",
                  "payload": {"verdict": "watch"}, "schema": 1})

    # A SHADOW dispersion lead: spawn (shadow) -> four ticks. Active-but-shadow.
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": SHADOW, "type": "lead.spawned",
                  "payload": {"spawner": "dispersion", "display": "XLK split", "shadow": True,
                              "spawned_at": "2026-07-06T00:00:00Z"}, "schema": 1})
    for i, z in enumerate((2.6, 2.55, 2.5, 2.45)):
        store.append({"ts": f"2026-07-06T00:03:0{i}Z", "lead": SHADOW, "type": "dispersion.tick",
                      "payload": {"z": z, "market_stress": False}, "schema": 1})

    # A REVERTED lead — folds to status=reverted; the report must NOT carry it.
    store.append({"ts": "2026-07-05T00:00:00Z", "lead": REVERTED, "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "OLD×PAIR", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-05T00:00:01Z", "lead": REVERTED, "type": "xcorr.reverted",
                  "payload": {"display": "OLD×PAIR"}, "schema": 1})

    # A dormant launch (survey + a dormant disposition) and a fault, both on _system.
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "_system", "type": "launch.unverified",
                  "payload": {"ticker": "NEWX", "series_id": "S000000009",
                              "detected_at": "2026-07-06T00:00:00Z"}, "schema": 1})
    # An UNLISTED detection (empty mf symbol) — filtered from the survey table, KEPT COUNTED as coverage.
    store.append({"ts": "2026-07-06T00:00:07Z", "lead": "_system", "type": "launch.unverified",
                  "payload": {"ticker": "", "series_id": "S000000BAD",
                              "detected_at": "2026-07-06T00:00:07Z"}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:05Z", "lead": "_system", "type": "launch",
                  "payload": {"series_id": "S000000009", "ticker": "NEWX",
                              "corroboration": "sectors_unresolved", "concentration_sectors": []},
                  "schema": 1})
    store.append({"ts": "2026-07-06T00:00:06Z", "lead": "_system", "type": "fault",
                  "payload": {"subsystem": "ingest.prices", "message": "XLK: empty price frame"},
                  "schema": 1})

    # Two runs, newest-first by ts, with DIFFERENT config hashes (config_changed on the latest = True).
    write_run_log(layout, registry, RunLog(run_id="r-old", ts="2026-07-05T00:00:00Z",
                                            date="2026-07-05", config_hash="hash-old-000", pushed=False))
    write_run_log(layout, registry, RunLog(run_id="r-new", ts="2026-07-06T00:00:00Z",
                                            date="2026-07-06", config_hash="hash-new-111", pushed=True))


def _render(layout, registry, now=NOW, cfg=None) -> str:
    states = views.fold_all_leads(registry)
    runs = recent_runs(registry)
    machine = ResolutionMachine(registry, EventStore(layout, registry), None, None)
    return export.board_snapshot_markdown(registry, states, runs, machine, cfg or _cfg(), now,
                                          str(layout.root))


# === pure-read / no-recompute (a readonly registry suffices; re-run is byte-identical) ==============

def test_export_is_pure_read_and_deterministic_readonly(layout, registry):
    # Seed with the writable fixture, then serve from a mode=ro Registry — the export must produce the
    # document with NO write/DDL/fetch (the readonly Registry would raise on any write), and re-running on
    # the unchanged store yields a byte-identical document (nothing to reward re-clicking — §5).
    _seed(layout, registry)
    registry.close()
    ro = Registry(layout.registry_path(), readonly=True)
    try:
        doc_a = _render(layout, ro)
        doc_b = _render(layout, ro)
    finally:
        ro.close()
    assert doc_a == doc_b                       # identical on an unchanged store (same `now`)
    assert doc_a.startswith("# Prospector — board snapshot")


# === no drift from the view-models ================================================================

def test_report_serializes_the_view_models_no_drift(layout, registry):
    _seed(layout, registry)
    doc = _render(layout, registry)
    states = views.fold_all_leads(registry)

    # Active-leads section carries the live lead (rank_active_leads), never the shadow/reverted.
    live_section = doc.split("## Active leads (live)")[1].split("## ")[0]
    assert LIVE in live_section and "XLK×XLU" in live_section
    assert SHADOW not in live_section and REVERTED not in live_section
    # Health carries the seeded fault verbatim; run history carries the run ids.
    assert "ingest.prices" in doc and "XLK: empty price frame" in doc
    assert "r-new" in doc and "r-old" in doc
    # Dormant pile carries the disposition; launches carry the ticker.
    assert "sectors_unresolved" in doc and "NEWX" in doc
    # Registry health matches the view-model (1 live, 1 shadow, 1 reverted).
    h = views.registry_health(states)
    assert f"**active_live**: {h['active_live']}" in doc and f"**reverted**: {h['reverted']}" in doc


def test_launches_section_drops_name_filters_unlisted_but_keeps_the_count(layout, registry):
    _seed(layout, registry)
    doc = _render(layout, registry)
    section = doc.split("## Launches (survey)")[1].split("## ")[0]
    assert "| ts | ticker | series_id | detected_at |" in section      # no `name` column
    assert "NEWX" in section                                           # a listed launch is surveyed
    assert "S000000BAD" not in section                                 # the unlisted series is NOT listed ...
    assert "1 unlisted (no-ticker) detection kept in the record" in section  # ... but kept COUNTED (coverage)


# === the manifest (self-describing header) ========================================================

def test_manifest_is_present_and_correct(layout, registry):
    _seed(layout, registry)
    doc = _render(layout, registry)
    assert f"**store**: `{layout.root}`" in doc
    assert f"**exported (UTC)**: {NOW}" in doc
    assert "**latest run**: `r-new`" in doc and "pushed=True" in doc and "faults=0" in doc
    assert "config_changed=true" in doc                 # hash-delta vs the prior run
    assert "**active (live) / ceiling**: 1 / 8" in doc
    assert "**shadow (dispersion burn-in)**: 1" in doc
    assert "**heartbeat**: OK" in doc


def test_manifest_shows_the_over_ceiling_banner(layout, registry):
    # Force over-ceiling (ceiling 0, 1 live lead): the banner rides the active line (the §8a tripwire).
    _seed(layout, registry)
    doc = _render(layout, registry, cfg=_cfg(ceiling=0))
    assert "**active (live) / ceiling**: 1 / 0 — ⚠ Over ceiling" in doc


# === active = all-active INCLUDING shadow; reverted excluded (the bound) ============================

def test_timelines_cover_all_active_incl_shadow_but_not_reverted(layout, registry):
    _seed(layout, registry)
    doc = _render(layout, registry)
    # Both active leads get a timeline section (live AND shadow) ...
    assert f"### {LIVE}" in doc and "· live" in doc
    assert f"### {SHADOW}" in doc and "· shadow" in doc
    # ... and the reverted lead appears NOWHERE in the report (dead leads never enter this file).
    assert REVERTED not in doc


# === tick-collapse ================================================================================

def test_tick_run_is_collapsed_to_one_line(layout, registry):
    _seed(layout, registry)
    doc = _render(layout, registry)
    # The five xcorr ticks collapse to one line with the LAST tick's z; the four dispersion ticks likewise.
    assert "5 ticks, 2026-07-06T00:01:00Z…2026-07-06T00:01:04Z, latest z = 2.7" in doc
    assert "4 ticks, 2026-07-06T00:03:00Z…2026-07-06T00:03:03Z, latest z = 2.45" in doc
    # State-relevant events stay verbatim; the ticks are NEVER listed as individual typed lines.
    assert "`xcorr.departure`" in doc and "`verdict`" in doc and "`lead.spawned`" in doc
    assert "`xcorr.tick`" not in doc and "`dispersion.tick`" not in doc


# === filenames + csv ==============================================================================

def test_filenames_are_self_describing_second_resolution_and_collision_free():
    assert export.board_snapshot_filename(NOW) == "prospector-board_20260707T000000Z.md"
    assert export.panel_csv_filename("active-leads", NOW) == "active-leads_20260707T000000Z.csv"
    # Different panels never collide even at the same instant (the friction the time-only name had).
    assert export.panel_csv_filename("run-history", NOW) != export.panel_csv_filename("dormant-pile", NOW)


def test_rows_to_csv_round_trips_a_list_of_dicts():
    import csv as _csv
    import io as _io
    rows = [{"lead": "xcorr-1", "latest_z": 3.2}, {"lead": "xcorr-2", "latest_z": None}]
    text = export.rows_to_csv(rows)
    parsed = list(_csv.DictReader(_io.StringIO(text)))
    assert [r["lead"] for r in parsed] == ["xcorr-1", "xcorr-2"]
    assert text.splitlines()[0] == "lead,latest_z"           # header from the first row's keys
    assert export.rows_to_csv([]) == ""
