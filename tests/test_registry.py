"""Registry: WAL-mode index over the envelope, (lead, ts, type) indexed, fold order stable,
upload bookkeeping and meta round-trip (spec §5/§7, CONTRACT)."""

import sqlite3

import pytest

from prospector.store.registry import Registry


def _insert(registry, event_id, ts, *, lead="lead_a", type="xcorr.tick"):
    return registry.insert_event(
        event_id=event_id, ts=ts, lead=lead, type=type, schema=1,
        payload_json='{"z":1.0}', sha256="0" * 64,
        file_path=f"events/{lead}/{ts}_{type}_{event_id}.json",
        ingested_at="2026-07-02T09:00:00Z")


def test_wal_journal_mode_active(registry):
    mode = registry.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_lead_ts_type_index_exists(registry):
    row = registry.conn.execute(
        "SELECT tbl_name FROM sqlite_master WHERE type='index' "
        "AND name='idx_events_lead_ts_type'").fetchone()
    assert row is not None
    assert row["tbl_name"] == "events"


def test_events_for_lead_orders_by_ts_then_event_id(registry):
    # Inserted deliberately out of order, with a ts tie to exercise the event_id tiebreak.
    _insert(registry, "cc", "2026-07-14T13:00:02Z")
    _insert(registry, "bb", "2026-07-14T13:00:01Z")
    _insert(registry, "aa", "2026-07-14T13:00:01Z")
    _insert(registry, "dd", "2026-07-14T13:00:00Z")
    rows = registry.events_for_lead("lead_a")
    assert [(r["ts"], r["event_id"]) for r in rows] == [
        ("2026-07-14T13:00:00Z", "dd"),
        ("2026-07-14T13:00:01Z", "aa"),
        ("2026-07-14T13:00:01Z", "bb"),
        ("2026-07-14T13:00:02Z", "cc"),
    ]


def test_pending_uploads_mark_uploaded_round_trip(registry):
    _insert(registry, "e1", "2026-07-14T13:00:00Z")
    _insert(registry, "e2", "2026-07-14T13:00:01Z")
    pending = registry.pending_uploads("events")
    assert [r["event_id"] for r in pending] == ["e1", "e2"]

    registry.mark_uploaded("events", "e1", "2026-07-14T14:00:00Z")
    pending = registry.pending_uploads("events")
    assert [r["event_id"] for r in pending] == ["e2"]

    row = registry.conn.execute(
        "SELECT uploaded_at FROM events WHERE event_id = 'e1'").fetchone()
    assert row["uploaded_at"] == "2026-07-14T14:00:00Z"


def test_upload_table_name_is_validated_fail_closed(registry):
    # sql-assert: the table name is interpolated into the SQL. The guard must fail CLOSED even under
    # `python -O` (which strips `assert`) — an unknown table must never reach a query. The literal-dict
    # lookup raises KeyError; it never builds `SELECT * FROM <arbitrary>`.
    with pytest.raises(KeyError):
        registry.pending_uploads("events; DROP TABLE events")
    with pytest.raises(KeyError):
        registry.mark_uploaded("evil", "e1", "2026-07-14T14:00:00Z")


def test_meta_get_set_round_trip(registry):
    assert registry.get_meta("no_such_key") is None
    registry.set_meta("config_hash", "abc123")
    assert registry.get_meta("config_hash") == "abc123"
    registry.set_meta("config_hash", "def456")  # upsert, not a second row
    assert registry.get_meta("config_hash") == "def456"
    # __init__ stamped the schema version
    assert registry.get_meta("schema_version") == "1"


# -- N1: the read-only firewall at the substrate ---------------------------------------------

def test_readonly_registry_refuses_writes(registry, layout):
    # A read-only Registry (the §11 dashboard's connection) must not be able to mutate the store —
    # the firewall enforced by the substrate, not a comment.
    ro = Registry(layout.registry_path(), readonly=True)
    try:
        assert ro.readonly is True
        with pytest.raises(sqlite3.OperationalError):
            ro.conn.execute("CREATE TABLE _x (a)")
            ro.conn.commit()
    finally:
        ro.close()


def test_readonly_registry_sees_fresh_wal_writes(registry, layout):
    # The design-thread freshness catch: the live viewer opens mode=ro (WAL-readable), NOT immutable=1,
    # so it must see the runner's LATEST committed writes — or it silently renders stale state, its own
    # quiet dishonesty. Prove it end-to-end: a mode=ro Registry, re-queried after the writable
    # connection commits a NEW event to the WAL store, sees it. (immutable=1 would fail this — it tells
    # SQLite the file never changes and would miss the un-checkpointed WAL write.)
    _insert(registry, "aa", "2026-07-14T13:00:00Z")  # committed to the WAL
    ro = Registry(layout.registry_path(), readonly=True)
    try:
        assert [r["event_id"] for r in ro.events_for_lead("lead_a")] == ["aa"]
        _insert(registry, "bb", "2026-07-14T13:00:01Z")  # a fresh tick's write, committed
        ids = [r["event_id"] for r in ro.events_for_lead("lead_a")]
        assert ids == ["aa", "bb"], (
            f"the mode=ro viewer did not see a freshly-committed WAL write ({ids}) — it is showing "
            "stale state. mode=ro must be WAL-readable; immutable=1 would cause exactly this (N1)")
    finally:
        ro.close()
