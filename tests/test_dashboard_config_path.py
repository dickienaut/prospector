"""Regression: the dashboard config path must not be a bare hardcoded relative path (N5).

`app.py` reads `_CONFIG_PATH = Path("config") / "prospector.yaml"` — a CWD-relative path with NO env
override and NO existence guard. So `main()` calls `load_config(_CONFIG_PATH)` and raises a raw
`FileNotFoundError` from any working directory except the repo root. The asymmetry is the tell: the
STORE path one line above is BOTH env-overridable (`PROSPECTOR_STORE`) AND degrades with a friendly
`st.warning` when absent; the CONFIG path has neither. A scheduled/systemd/container launch from a
different CWD crashes the read-only surface with a traceback instead of a legible message.

(This is also why the existing test_dashboard_app.py smoke passes: pytest runs from the repo root, so
the relative config path resolves by accident of CWD — exactly the hidden assumption N5 is about.)

Two behaviours a fix must provide, mirroring the store path:
  * `test_missing_config_degrades_gracefully` — absent config from a non-root CWD is a clean message,
    not a raw exception (fix-agnostic: any non-crashing handling satisfies it);
  * `test_config_path_is_env_overridable` — a `PROSPECTOR_CONFIG` env var lets an operator point at the
    config from any CWD, the same escape hatch `PROSPECTOR_STORE` already gives the store.

Drives the real app.py via AppTest (the house harness — see test_dashboard_app.py). The app path is
absolute so AppTest still finds the script after we chdir away from the repo root.
"""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

import prospector.dashboard.app as _app_mod
from prospector.identity.resolution import ResolutionMachine
from prospector.runner.runlog import RunLog, write_run_log
from prospector.store.event_store import EventStore

_APP_PATH = _app_mod.__file__                                       # absolute -> survives chdir
_REAL_CONFIG = Path(_app_mod.__file__).parents[2] / "config" / "prospector.yaml"  # the repo's config


def _seed(layout, registry):
    """Something in every panel, so a config that IS found renders the full dashboard."""
    store = EventStore(layout, registry)
    # Runner-faithful seed: a real store has resolution_queue because the runner's ResolutionMachine
    # creates it. Construct one here WHILE THE STORE IS WRITABLE (the fixed dashboard opens it
    # read-only and cannot create tables — same requirement as test_dashboard_readonly.py's _seed).
    ResolutionMachine(registry, store, None, None)
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "xcorr-abc1234567", "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:01Z", "lead": "xcorr-abc1234567", "type": "xcorr.departure",
                  "payload": {"display": "XLK×XLU", "z": 3.2, "market_stress": False}, "schema": 1})
    write_run_log(layout, registry, RunLog(run_id="r1", ts="2026-07-06T00:00:00Z",
                                           date="2026-07-06", pushed=True))


def _run_from_nonroot_cwd(monkeypatch, tmp_path, layout):
    """Common setup: a valid, findable store (absolute PROSPECTOR_STORE) but a CWD with NO config/.
    This isolates the CONFIG path — the store guard passes, so main() reaches load_config."""
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    monkeypatch.setenv("PROSPECTOR_STORE", str(layout.root))        # store found regardless of CWD
    workdir = tmp_path / "elsewhere"                                # no config/ subdir here
    workdir.mkdir()
    monkeypatch.chdir(workdir)


def test_missing_config_degrades_gracefully(layout, registry, monkeypatch, tmp_path):
    # No PROSPECTOR_CONFIG, launched from a directory without config/. RED today: main() raises a raw
    # FileNotFoundError from load_config(Path("config")/"prospector.yaml"). A fix must handle it (a
    # warning-and-return like the store path, or a resolved path) — never a raw traceback.
    _seed(layout, registry)
    monkeypatch.delenv("PROSPECTOR_CONFIG", raising=False)
    _run_from_nonroot_cwd(monkeypatch, tmp_path, layout)

    at = st_testing.AppTest.from_file(_APP_PATH).run(timeout=60)

    assert not at.exception, (
        f"the dashboard crashed with a raw exception ({at.exception}) when launched from a non-root "
        "CWD with no config file — the config path is hardcoded relative with no existence guard, "
        "while the store path one line above degrades with a warning (N5)")


def test_config_path_is_env_overridable(layout, registry, monkeypatch, tmp_path):
    # PROSPECTOR_CONFIG points at the real config by absolute path; launched from a non-root CWD. RED
    # today: app.py ignores the env var and uses the hardcoded relative path -> FileNotFoundError.
    # GREEN after fix: the env override is honored, the config loads, the dashboard renders.
    _seed(layout, registry)
    monkeypatch.setenv("PROSPECTOR_CONFIG", str(_REAL_CONFIG))
    _run_from_nonroot_cwd(monkeypatch, tmp_path, layout)

    at = st_testing.AppTest.from_file(_APP_PATH).run(timeout=60)

    assert not at.exception, (
        f"PROSPECTOR_CONFIG was set to a valid absolute config path but the dashboard still crashed "
        f"({at.exception}) — the config path is not env-overridable, unlike PROSPECTOR_STORE (N5)")
    headers = [h.value for h in at.header]
    assert "Active leads" in headers, (
        "with PROSPECTOR_CONFIG set the dashboard should render fully from any CWD; the panels did not "
        "appear, so the env override was not honored (N5)")
