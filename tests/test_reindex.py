"""Registry repair (spec §7): the events/ and snapshots/ trees are the truth and the registry
is only the index over them, so deleting registry.sqlite and reindexing must reproduce every
record column exactly — only the operational bookkeeping (ingested_at, uploaded_at) is
recomputed, because the files do not carry it. A snapshot's reason IS carried (write_snapshot
embeds it in the file), so repair recovers the true reason; only a file without one falls back
to 'reindexed'. Scans ignore *.tmp and dotfiles; malformed files are counted skipped, never
indexed, never a crash."""

import json
from pathlib import Path

import pytest

from prospector.fold.snapshots import write_snapshot
from prospector.store.envelope import parse_ts
from prospector.store.event_store import EventStore
from prospector.store.registry import Registry
from prospector.store.reindex import rebuild_registry

FIXED_NOW = "2026-07-02T09:00:00Z"

EVENT_RECORD_COLUMNS = ("event_id", "ts", "lead", "type", "schema", "payload",
                        "sha256", "file_path")
# reason is a record column: the snapshot file embeds it, so reindex reproduces it exactly.
SNAPSHOT_RECORD_COLUMNS = ("snapshot_id", "lead", "ts", "reason", "file_path", "sha256")


def _event(lead, ts, type_, payload):
    return {"ts": ts, "lead": lead, "type": type_, "payload": payload, "schema": 1}


@pytest.fixture
def populated(layout, registry):
    """A small live store: two leads + a _system event + one snapshot."""
    store = EventStore(layout, registry, clock=lambda: FIXED_NOW)
    store.append(_event("ld_one", "2026-07-01T00:00:00Z", "lead.spawned",
                        {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}))
    store.append(_event("ld_one", "2026-07-02T00:00:00Z", "xcorr.tick", {"z": 2.9}))
    store.append(_event("ld_two", "2026-07-03T00:00:00Z", "lead.spawned",
                        {"spawner": "dispersion", "display": "semis", "shadow": True}))
    store.append(_event("_system", "2026-07-04T00:00:00Z", "config.changed",
                        {"diff": {"added": {}, "removed": {}, "changed": {}}}))
    write_snapshot(layout, registry, "ld_one", {"status": "active", "event_count": 2},
                   "state_change", "2026-07-02T00:00:00Z")
    return store


def _record_rows(reg, table, columns):
    rows = reg.conn.execute(f"SELECT * FROM {table}").fetchall()
    return sorted(tuple(row[c] for c in columns) for row in rows)


def _delete_registry(layout):
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(layout.registry_path()) + suffix)
        if p.exists():
            p.unlink()


def _fresh_registry(layout, registry):
    registry.close()
    _delete_registry(layout)
    return Registry(layout.registry_path())


# -- the acceptance path: lose the index, rebuild it from the files ---------------

def test_reindex_reproduces_record_columns(populated, layout, registry):
    original_events = _record_rows(registry, "events", EVENT_RECORD_COLUMNS)
    original_snapshots = _record_rows(registry, "snapshots", SNAPSHOT_RECORD_COLUMNS)

    fresh = _fresh_registry(layout, registry)
    try:
        counts = rebuild_registry(layout, fresh)
        assert counts == {"events_indexed": 4, "snapshots_indexed": 1, "skipped": 0}
        assert _record_rows(fresh, "events", EVENT_RECORD_COLUMNS) == original_events
        assert _record_rows(fresh, "snapshots", SNAPSHOT_RECORD_COLUMNS) \
            == original_snapshots
    finally:
        fresh.close()


def test_reindex_recomputes_operational_columns(populated, layout, registry):
    fresh = _fresh_registry(layout, registry)
    try:
        rebuild_registry(layout, fresh)
        for row in fresh.conn.execute("SELECT * FROM events").fetchall():
            parse_ts(row["ingested_at"])  # valid ISO-8601 UTC — but mtime, not the original
            assert row["uploaded_at"] is None  # next sync re-uploads
        # The snapshot file embeds its reason, so reindex recovers the true one.
        assert fresh.latest_snapshot("ld_one")["reason"] == "state_change"
    finally:
        fresh.close()


def test_reindex_falls_back_to_reindexed_without_embedded_reason(layout, registry):
    """A snapshot file without an embedded reason (foreign, or written before the reason
    was embedded) still indexes — with the honest placeholder, never a crash."""
    path = layout.snapshots_root() / "ld_legacy" / "20260702T000000Z.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "active"}), encoding="utf-8")
    rebuild_registry(layout, registry)
    assert registry.latest_snapshot("ld_legacy")["reason"] == "reindexed"


def test_reindex_indexes_subsecond_snapshot_stems(layout, registry):
    """ts_compact emits a sub-second filename (`…_ffffffZ`) when two snapshots land in the same
    wall-clock second; reindex must round-trip it via `ts_from_compact`, not skip it. Regression:
    the inverse was missing, so parsing the stem as whole-second-only (`%Y%m%dT%H%M%SZ`) threw on the
    sub-second form and the `except` silently counted it `skipped` — the stem is the ONLY carrier of a
    snapshot's ts, so a skipped sub-second snapshot is lost from a rebuilt index."""
    ts = "2026-07-02T00:00:00.123456Z"
    write_snapshot(layout, registry, "ld_sub", {"status": "active", "event_count": 1},
                   "state_change", ts)
    original = _record_rows(registry, "snapshots", SNAPSHOT_RECORD_COLUMNS)

    fresh = _fresh_registry(layout, registry)
    try:
        counts = rebuild_registry(layout, fresh)
        assert counts == {"events_indexed": 0, "snapshots_indexed": 1, "skipped": 0}
        assert _record_rows(fresh, "snapshots", SNAPSHOT_RECORD_COLUMNS) == original
        # microseconds survive the filename round-trip (ts_compact -> stem -> ts_from_compact)
        assert fresh.latest_snapshot("ld_sub")["ts"] == ts
    finally:
        fresh.close()


# -- INSERT OR IGNORE: reindex never clobbers a live registry ----------------------

def test_reindex_into_live_registry_preserves_original_bookkeeping(populated, layout,
                                                                   registry):
    counts = rebuild_registry(layout, registry)
    assert counts == {"events_indexed": 4, "snapshots_indexed": 1, "skipped": 0}
    assert registry.event_count() == 4
    for row in registry.conn.execute("SELECT * FROM events").fetchall():
        assert row["ingested_at"] == FIXED_NOW  # first ingest wins, mtime never overwrote it
    assert registry.latest_snapshot("ld_one")["reason"] == "state_change"


def test_reindex_is_idempotent(populated, layout, registry):
    fresh = _fresh_registry(layout, registry)
    try:
        first = rebuild_registry(layout, fresh)
        second = rebuild_registry(layout, fresh)
        assert first == second
        assert fresh.event_count() == 4
    finally:
        fresh.close()


# -- scan hygiene: tmp files and dotfiles invisible, malformed files skipped -------

def test_tmp_files_and_dotfiles_ignored_entirely(populated, layout, registry):
    lead_dir = layout.events_root() / "ld_one"
    (lead_dir / ".20260701T000000Z_x_y.json.ab12cd34.tmp").write_text("{ torn",
                                                                      encoding="utf-8")
    (lead_dir / "leftover.tmp").write_text("{ torn", encoding="utf-8")
    (lead_dir / ".DS_Store").write_bytes(b"\x00")
    hidden = layout.events_root() / ".hidden"
    hidden.mkdir()
    (hidden / "20260701T000000Z_fault_beef.json").write_text("{}", encoding="utf-8")
    (layout.snapshots_root() / "ld_one" / ".DS_Store").write_bytes(b"\x00")

    fresh = _fresh_registry(layout, registry)
    try:
        # Ignored means not indexed AND not skipped — they are artifacts, not records.
        assert rebuild_registry(layout, fresh) \
            == {"events_indexed": 4, "snapshots_indexed": 1, "skipped": 0}
    finally:
        fresh.close()


def test_malformed_files_are_skipped_never_indexed(populated, layout, registry):
    bad_dir = layout.events_root() / "ld_bad"
    bad_dir.mkdir()
    # Valid JSON, invalid envelope (naive ts).
    (bad_dir / "20260705T000000Z_fault_deadbeef.json").write_text(
        json.dumps({"ts": "2026-07-05T00:00:00", "lead": "ld_bad", "type": "fault",
                    "payload": {}, "schema": 1}), encoding="utf-8")
    # Not JSON at all.
    (bad_dir / "20260706T000000Z_fault_cafef00d.json").write_text("{ torn write",
                                                                  encoding="utf-8")
    # No event_id separator in the name.
    (bad_dir / "notanevent.json").write_text("{}", encoding="utf-8")
    snap_dir = layout.snapshots_root() / "ld_one"
    (snap_dir / "garbage.json").write_text("{}", encoding="utf-8")   # unparseable ts stem
    (snap_dir / "20260708T000000Z.json").write_text("{ torn", encoding="utf-8")  # not JSON

    fresh = _fresh_registry(layout, registry)
    try:
        counts = rebuild_registry(layout, fresh)
        assert counts == {"events_indexed": 4, "snapshots_indexed": 1, "skipped": 5}
        assert fresh.events_for_lead("ld_bad") == []
    finally:
        fresh.close()


def test_reindex_of_empty_or_missing_trees_is_zero(layout, registry):
    assert rebuild_registry(layout, registry) \
        == {"events_indexed": 0, "snapshots_indexed": 0, "skipped": 0}
