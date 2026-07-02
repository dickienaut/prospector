"""Reactive snapshot policy (spec §5, adaptive-snapshot CONTRACT): immediate on state change,
dense while active, weekly floor when quiet. All decisions pure — the clock is injected."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from prospector.fold.snapshots import (SnapshotConfig, SnapshotDecision, should_snapshot,
                                       write_snapshot)
from prospector.primitives.atomic import sha256_file

NOW = datetime(2026, 7, 14, 13, 0, 0, tzinfo=timezone.utc)
CFG = SnapshotConfig.from_cfg({"active": "daily", "quiet": "weekly"})

ACTIVE = {"status": "active", "shadow": False, "verdict": "none"}
REVERTED = {"status": "reverted", "shadow": False, "verdict": "none"}


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# -- SnapshotConfig.from_cfg --------------------------------------------------

def test_from_cfg_named_intervals():
    cfg = SnapshotConfig.from_cfg({"active": "daily", "quiet": "weekly"})
    assert cfg.active_interval == timedelta(days=1)
    assert cfg.quiet_floor == timedelta(days=7)
    assert SnapshotConfig.from_cfg({"active": "hourly", "quiet": "daily"}).active_interval \
        == timedelta(hours=1)


def test_from_cfg_integer_days():
    cfg = SnapshotConfig.from_cfg({"active": 2, "quiet": 14})
    assert cfg.active_interval == timedelta(days=2)
    assert cfg.quiet_floor == timedelta(days=14)


def test_from_cfg_defaults_match_spec():
    cfg = SnapshotConfig.from_cfg({})
    assert cfg.active_interval == timedelta(days=1)
    assert cfg.quiet_floor == timedelta(days=7)


@pytest.mark.parametrize("bad", ["monthly", 0, -1, True, 1.5, None])
def test_from_cfg_rejects_unrecognized(bad):
    with pytest.raises(ValueError):
        SnapshotConfig.from_cfg({"active": bad})


# -- should_snapshot ----------------------------------------------------------

def test_state_change_snapshots_immediately_regardless_of_last_ts():
    just_now = iso(NOW - timedelta(seconds=1))
    for state in (ACTIVE, REVERTED):
        decision = should_snapshot(state, just_now, ["status"], NOW, CFG)
        assert decision == SnapshotDecision(save=True, reason="state_change")


def test_active_lead_crossing_daily_boundary_saves():
    decision = should_snapshot(ACTIVE, iso(NOW - timedelta(hours=25)), [], NOW, CFG)
    assert decision == SnapshotDecision(save=True, reason="active_daily")
    # Boundary is inclusive: exactly one interval elapsed saves.
    at_boundary = should_snapshot(ACTIVE, iso(NOW - timedelta(days=1)), [], NOW, CFG)
    assert at_boundary.reason == "active_daily"


def test_active_lead_inside_interval_no_save():
    decision = should_snapshot(ACTIVE, iso(NOW - timedelta(hours=1)), [], NOW, CFG)
    assert decision == SnapshotDecision(save=False, reason=None)


@pytest.mark.parametrize("state", [REVERTED, {"status": None}, {}])
def test_quiet_lead_only_weekly_floor(state):
    inside = should_snapshot(state, iso(NOW - timedelta(days=3)), [], NOW, CFG)
    assert inside == SnapshotDecision(save=False, reason=None)
    past_floor = should_snapshot(state, iso(NOW - timedelta(days=8)), [], NOW, CFG)
    assert past_floor == SnapshotDecision(save=True, reason="quiet_weekly")


def test_never_snapshotted_lead_saves():
    assert should_snapshot(ACTIVE, None, [], NOW, CFG) \
        == SnapshotDecision(save=True, reason="active_daily")
    assert should_snapshot(REVERTED, None, [], NOW, CFG) \
        == SnapshotDecision(save=True, reason="quiet_weekly")


def test_decision_is_pure_function_of_args():
    args = (ACTIVE, iso(NOW - timedelta(days=2)), [], NOW, CFG)
    assert should_snapshot(*args) == should_snapshot(*args)


# -- write_snapshot -----------------------------------------------------------

def test_write_snapshot_writes_file_and_registry_row(layout, registry):
    ts = "2026-07-14T13:00:00Z"
    state = {"status": "active", "event_count": 3, "latest_z": 2.7}
    path = write_snapshot(layout, registry, "lead_abc", state, "state_change", ts)

    assert path == layout.snapshot_path("lead_abc", ts)
    assert path.exists()
    # The file is the state plus its reason: the fossil record alone carries why this
    # snapshot exists, so reindex can recover it (spec §7).
    assert json.loads(path.read_text(encoding="utf-8")) == {**state, "reason": "state_change"}

    row = registry.latest_snapshot("lead_abc")
    assert row is not None
    assert row["snapshot_id"] == "lead_abc:20260714T130000Z"
    assert row["lead"] == "lead_abc"
    assert row["ts"] == ts
    assert row["reason"] == "state_change"
    # Store-root-relative, like event rows — the same string doubles as the S3 key (§7).
    assert row["file_path"] == "snapshots/lead_abc/20260714T130000Z.json"


def test_write_snapshot_idempotent_on_same_lead_ts(layout, registry):
    ts = "2026-07-14T13:00:00Z"
    state = {"status": "active", "event_count": 3}
    first = write_snapshot(layout, registry, "lead_abc", state, "state_change", ts)
    second = write_snapshot(layout, registry, "lead_abc", state, "active_daily", ts)

    assert first == second
    count = registry.conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE lead = ?", ("lead_abc",)).fetchone()[0]
    assert count == 1
    # INSERT OR IGNORE keeps the first row: the original reason survives the replay.
    assert registry.latest_snapshot("lead_abc")["reason"] == "state_change"
    # First write wins on disk too — the replay's reason never rewrites the file, so the
    # indexed sha256 still matches the bytes.
    assert json.loads(first.read_text(encoding="utf-8"))["reason"] == "state_change"
    assert registry.latest_snapshot("lead_abc")["sha256"] == sha256_file(first)


def test_write_snapshot_distinct_ts_gets_own_row(layout, registry):
    write_snapshot(layout, registry, "lead_abc", {"status": "active"},
                   "active_daily", "2026-07-14T13:00:00Z")
    write_snapshot(layout, registry, "lead_abc", {"status": "active"},
                   "active_daily", "2026-07-15T13:00:00Z")
    count = registry.conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE lead = ?", ("lead_abc",)).fetchone()[0]
    assert count == 2
    assert registry.latest_snapshot("lead_abc")["ts"] == "2026-07-15T13:00:00Z"
