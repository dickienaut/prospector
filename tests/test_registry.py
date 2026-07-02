"""Registry: WAL-mode index over the envelope, (lead, ts, type) indexed, fold order stable,
upload bookkeeping and meta round-trip (spec §5/§7, CONTRACT)."""


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


def test_meta_get_set_round_trip(registry):
    assert registry.get_meta("no_such_key") is None
    registry.set_meta("config_hash", "abc123")
    assert registry.get_meta("config_hash") == "abc123"
    registry.set_meta("config_hash", "def456")  # upsert, not a second row
    assert registry.get_meta("config_hash") == "def456"
    # __init__ stamped the schema version
    assert registry.get_meta("schema_version") == "1"
