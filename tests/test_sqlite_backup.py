"""Safe SQLite backup (spec §1c, CONTRACT): the registry is only ever shipped as a
`.backup`-API snapshot. These tests back up a genuinely WAL-active database — sidecar on
disk, writer connection open, even a write transaction in flight — and prove the copy is
complete, consistent, and blind to uncommitted work (raw-copying the live file would ship
torn pages, the bug the vendored discipline exists to prevent)."""

import json
import sqlite3
from pathlib import Path

from prospector.primitives.sqlite_backup import backup_sqlite

_ROW_SQL = ("INSERT INTO events (event_id, ts, lead, type, schema, payload, sha256, "
            "file_path, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")


def _insert_rows(registry, n):
    for i in range(n):
        registry.insert_event(
            event_id=f"ev{i:04d}", ts="2026-07-01T00:00:00Z", lead="ld_bak",
            type="xcorr.tick", schema=1, payload_json=json.dumps({"z": 2.5 + i}),
            sha256="0" * 64,
            file_path=f"events/ld_bak/20260701T000000Z_xcorr.tick_ev{i:04d}.json",
            ingested_at="2026-07-01T00:00:00Z")


def _open_readonly(path: Path) -> sqlite3.Connection:
    # The backup inherits WAL mode from the source's header; a read-only open of a WAL
    # database with no live writer needs immutable=1 (no -shm to attach, none created).
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def test_backup_of_live_wal_registry_is_complete_and_consistent(layout, registry, tmp_path):
    _insert_rows(registry, 20)
    # The registry fixture's connection stays open: WAL is genuinely active and the
    # committed pages live in the -wal sidecar, not (yet) the main file.
    wal = Path(str(layout.registry_path()) + "-wal")
    assert wal.exists() and wal.stat().st_size > 0

    dest = backup_sqlite(layout.registry_path(), tmp_path / "mirror" / "registry.sqlite")

    ro = _open_readonly(dest)
    try:
        assert ro.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 20
        ids = {r[0] for r in ro.execute("SELECT event_id FROM events")}
        assert ids == {f"ev{i:04d}" for i in range(20)}
        assert ro.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        ro.close()


def test_backup_during_open_write_transaction_sees_committed_rows_only(layout, registry,
                                                                       tmp_path):
    _insert_rows(registry, 5)
    writer = sqlite3.connect(str(layout.registry_path()))
    writer.isolation_level = None  # explicit transaction control
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(_ROW_SQL, ("uncommitted", "2026-07-02T00:00:00Z", "ld_bak",
                                  "xcorr.tick", 1, "{}", "0" * 64,
                                  "events/ld_bak/20260702T000000Z_xcorr.tick_x.json",
                                  "2026-07-02T00:00:00Z"))
        # Backup while the write lock is held and the insert is in flight: WAL readers
        # never block on writers, and the snapshot is of the last commit.
        dest = backup_sqlite(layout.registry_path(), tmp_path / "registry.sqlite")
    finally:
        writer.rollback()
        writer.close()

    ro = _open_readonly(dest)
    try:
        assert ro.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 5
        assert ro.execute("SELECT COUNT(*) FROM events WHERE event_id = 'uncommitted'"
                          ).fetchone()[0] == 0
        assert ro.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        ro.close()
