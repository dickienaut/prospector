"""M7-DASH-01 — the dashboard/export dead-man must honor the CONFIGURED heartbeat cadence.

Cold-read finding (2026-07-14, against main @ 74a4394): PR #58's M7-03 fix relocated the OK/BROKEN
dead-man liveness to the dashboard (app.py) and the board-snapshot export (export.py), but BOTH
call sites HARDCODE `floor_days=7` instead of threading `cfg.schedule.heartbeat_cadence_days` — the
value the runner send-gate and the email floor (email_render.py:58) both honor. config/prospector.yaml
promises the cadence feeds "the send cadence AND the §8a silence floor (one clock, one source)", so the
hardcode breaks that on the very alarm layer the M7 fix was meant to harden:

  * cadence > 7 (e.g. fortnightly 14): a HEALTHY, not-yet-due system reads BROKEN on the dashboard and
    in the exported board snapshot -> cry-wolf on the dead-man (GPWS: the operator learns to ignore it).
  * cadence < 7 (e.g. 3): the dashboard reads OK while the runner considers the channel OVERDUE ->
    a false-NEGATIVE dead-man, the more dangerous direction.

The suite misses it because every existing test pins cadence == 7 (the default), so the hardcode
matches — the project's signature green-on-synthetic pattern.

These tests exercise the REAL call sites (app.py via AppTest, export.board_snapshot_markdown directly)
so they catch the hardcode where it lives — NOT views.heartbeat with a floor computed inside the test
(that would pass for the wrong reason: it would re-implement the fix and never touch the buggy caller).
They assert BEHAVIOUR (rendered liveness tracks the configured cadence), not implementation (any
threading of floor_days from cfg passes). Authored RED against main @ 74a4394; GREEN against the
reference fix. xfail(strict=True) is the QA->implementer handoff: GREEN in the gate now, flips to a loud
XPASS the moment the fix lands; the implementer removes the marker in the apply PR.
"""

import pytest

from prospector.dashboard import export
from prospector.store.event_store import EventStore
from prospector.store.envelope import SYSTEM_LEAD
from prospector.runner.runlog import RunLog, write_run_log, recent_runs
from prospector.identity.resolution import ResolutionMachine


NOW = "2026-07-14T22:30:00Z"
LAST_SENT_8D = "2026-07-06T22:30:00Z"   # 8 days before NOW


def _seed_8d_heartbeat_and_run(layout, registry):
    """A real store: a heartbeat.sent 8 days ago + one completed run today (runner-faithful seed)."""
    store = EventStore(layout, registry)
    store.append({"ts": LAST_SENT_8D, "lead": SYSTEM_LEAD, "type": "heartbeat.sent",
                  "payload": {"trigger": "cadence"}, "schema": 1})
    write_run_log(layout, registry, RunLog(run_id="r1", ts=NOW, date=NOW[:10], pushed=True))


def _write_cfg(tmp_path, cadence_days):
    """A config file with a non-default heartbeat cadence, else mirroring the shipped shape."""
    import textwrap
    p = tmp_path / "prospector.yaml"
    p.write_text(textwrap.dedent(f"""
        schedule:
          heartbeat_cadence_days: {cadence_days}
        oracle:
          active_lead_ceiling: 8
        dispersion:
          shadow_days: 90
    """).strip() + "\n")
    return p


# === the board-snapshot export must not cry wolf on a longer cadence (drives the REAL export path) ==

@pytest.mark.xfail(strict=True, reason="M7-DASH-01 RED-first: export.py:197 calls views.heartbeat with "
    "no floor_days (defaults to 7), so board_snapshot_markdown prints 'heartbeat: BROKEN' for a HEALTHY "
    "system on a >7d cadence. GREEN when export threads cfg.schedule.heartbeat_cadence_days; implementer "
    "removes this marker in the apply PR.")
def test_board_snapshot_export_honors_configured_cadence(layout, registry):
    # runner-faithful: build the resolution_queue table (N1) while writable, then seed fossils
    machine = ResolutionMachine(registry, EventStore(layout, registry), None, None)
    _seed_8d_heartbeat_and_run(layout, registry)
    cfg = {"schedule": {"heartbeat_cadence_days": 14}, "oracle": {"active_lead_ceiling": 8},
           "dispersion": {"shadow_days": 90}}
    runs = recent_runs(registry)
    md = export.board_snapshot_markdown(registry, [], runs, machine, cfg, NOW,
                                        store_path=str(layout.root))
    hb_line = next((ln for ln in md.splitlines() if "**heartbeat**" in ln), "")
    # 8 days of silence under a 14-day cadence is HEALTHY; a snapshot honoring cfg must not say BROKEN.
    assert "BROKEN" not in hb_line, (
        f"board snapshot cries BROKEN on a healthy 14d-cadence system: {hb_line!r}")


# === the Streamlit dashboard shell must not cry wolf either (drives the REAL app.py render) =========

@pytest.mark.xfail(strict=True, reason="M7-DASH-01 RED-first: app.py:81 hardcodes floor_days=7, so the "
    "Heartbeat metric reads BROKEN for a HEALTHY system on a 14-day cadence. GREEN when app.py threads "
    "cfg.schedule.heartbeat_cadence_days; implementer removes this marker in the apply PR.")
def test_dashboard_app_heartbeat_honors_configured_cadence(layout, registry, monkeypatch, tmp_path):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    # runner-faithful: build the resolution tables while writable (N1), then seed the fossils
    from prospector.identity.resolution import ResolutionMachine
    ResolutionMachine(registry, EventStore(layout, registry), None, None)
    _seed_8d_heartbeat_and_run(layout, registry)
    cfg_path = _write_cfg(tmp_path, 14)
    monkeypatch.setenv("PROSPECTOR_STORE", str(layout.root))
    monkeypatch.setenv("PROSPECTOR_CONFIG", str(cfg_path))   # N5: config path is env-overridable

    at = st_testing.AppTest.from_file("prospector/dashboard/app.py").run(timeout=60)
    assert not at.exception
    hb_metric = next((m for m in at.metric if m.label == "Heartbeat"), None)
    assert hb_metric is not None, "Heartbeat metric did not render"
    # 8 days silence under a 14-day cadence is HEALTHY; the metric must read OK, not BROKEN.
    assert hb_metric.value == "OK", (
        f"dashboard Heartbeat reads {hb_metric.value!r} on a healthy 14d-cadence system (cry-wolf)")
