"""WAL-mode SQLite registry — the queryable index over the append-only store (spec §5/§7, CONTRACT).

Structure vendored from prophit_skunkworks/ltee_archive/registry.py (WAL pragma, executescript
init, Row factory, metadata/blob split), archive snapshot dated 2026-03-29, vendored 2026-07-02.
No commit hash available (archive copy).

Critical inversion from the source (spec §5): Prophit's registry uses wide typed metric columns
(one column per metric) because its metric set is fixed. The Prospector's whole premise is
unforeseen event types, so the events table is the ENVELOPE — ts/lead/type/schema columns plus a
JSON `payload` blob column, indexed on (lead, ts, type). A new event type needs no migration and
no new column. Do not re-introduce typed metric columns.

The registry holds envelope rows, payload JSON, and file paths — never blob contents (snapshots,
ingest pulls, captures stay on disk/S3). It is an INDEX: the events/ tree is the truth, and
`rebuild()`-style repair (pros store reindex) reconstructs rows from files.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    ts           TEXT NOT NULL,
    lead         TEXT NOT NULL,
    type         TEXT NOT NULL,
    schema       INTEGER NOT NULL,
    payload      TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    ingested_at  TEXT NOT NULL,
    uploaded_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_lead_ts_type ON events(lead, ts, type);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    lead         TEXT NOT NULL,
    ts           TEXT NOT NULL,
    reason       TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    uploaded_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_lead_ts ON snapshots(lead, ts);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Registry:
    def __init__(self, db_path: Path, readonly: bool = False):
        """`readonly=True` opens the store for a READ-ONLY surface (the §11 dashboard, N1). It must
        NEVER mutate the store, so it opens the db `mode=ro` and skips the WAL PRAGMA, the DDL
        `executescript`, and every commit — merely viewing then cannot flip `journal_mode`, create
        -wal/-shm sidecars, take a write lock that contends with the live runner, or crash on a
        genuinely read-only mount. The read-write path (the runner) is unchanged.

        `mode=ro` — deliberately NOT `mode=ro&immutable=1`. `mode=ro` is WAL-READABLE: on the live
        (writable-dir) store it sees the runner's latest un-checkpointed writes, so the viewer never
        shows stale state. `immutable=1` tells SQLite the file never changes — it would miss those WAL
        writes (a quietly-dishonest stale viewer) and is unsafe against the live runner; it belongs only
        to a checkpointed read-only-MEDIA deploy, which is a documented, deferred precondition (M7)."""
        self.db_path = Path(db_path)
        self.readonly = readonly
        if readonly:
            # No mkdir, no PRAGMA, no DDL, no commit — a pure reader over the fossil record.
            self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                        check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        # M7-06 belt (with the single-writer lock as the primary — see prospector/store/run_lock.py):
        # writer-vs-writer contention is structurally gone once one tick holds the run.lock, but the
        # residual is the brief lock the SQLite `.backup` API takes if a MANUAL `pros backup` overlaps a
        # tick. busy_timeout turns that from an immediate SQLITE_BUSY error into a short wait. Hardcoded —
        # promote to config only if it ever actually needs tuning (the config-under-real-pain rule).
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(_DDL)
        if self.get_meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()

    # -- events ------------------------------------------------------------

    def insert_event(self, *, event_id: str, ts: str, lead: str, type: str, schema: int,
                     payload_json: str, sha256: str, file_path: str, ingested_at: str) -> bool:
        """INSERT OR IGNORE — re-ingesting the same event_id is idempotent.
        Returns True if a row was inserted. There is no update/delete for events, ever."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO events
               (event_id, ts, lead, type, schema, payload, sha256, file_path, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, ts, lead, type, schema, payload_json, sha256, file_path, ingested_at))
        self.conn.commit()
        return cur.rowcount == 1

    def events_for_lead(self, lead: str, type: str | None = None) -> list[sqlite3.Row]:
        """Ordered by (ts, event_id) — the fold's total order."""
        if type is None:
            q = "SELECT * FROM events WHERE lead = ? ORDER BY ts, event_id"
            return self.conn.execute(q, (lead,)).fetchall()
        q = "SELECT * FROM events WHERE lead = ? AND type = ? ORDER BY ts, event_id"
        return self.conn.execute(q, (lead, type)).fetchall()

    def events_by_type(self, type: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM events WHERE type = ? ORDER BY ts, event_id", (type,)).fetchall()

    def all_leads(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT lead FROM events ORDER BY lead").fetchall()
        return [r["lead"] for r in rows]

    def event_count(self, lead: str | None = None) -> int:
        if lead is None:
            return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE lead = ?", (lead,)).fetchone()[0]

    # -- snapshots ----------------------------------------------------------

    def insert_snapshot(self, *, snapshot_id: str, lead: str, ts: str, reason: str,
                        file_path: str, sha256: str) -> bool:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO snapshots
               (snapshot_id, lead, ts, reason, file_path, sha256) VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot_id, lead, ts, reason, file_path, sha256))
        self.conn.commit()
        return cur.rowcount == 1

    def latest_snapshot(self, lead: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM snapshots WHERE lead = ? ORDER BY ts DESC, snapshot_id DESC LIMIT 1",
            (lead,)).fetchone()

    # -- upload bookkeeping (operational, not record content) ---------------

    def pending_uploads(self, table: str) -> list[sqlite3.Row]:
        # sql-assert: the table name is interpolated into the SQL, so it must be gated by a REAL guard —
        # `assert` is stripped by `python -O`, which would leave the f-string ungated on a bug/attacker
        # value. A literal-dict lookup fails CLOSED even under -O: an unknown table raises KeyError and
        # never reaches a query. (Both callers pass literals today; this removes the -O footgun.)
        query = {"events": "SELECT * FROM events WHERE uploaded_at IS NULL ORDER BY ts",
                 "snapshots": "SELECT * FROM snapshots WHERE uploaded_at IS NULL ORDER BY ts"}[table]
        return self.conn.execute(query).fetchall()

    def mark_uploaded(self, table: str, key: str, uploaded_at: str) -> None:
        # sql-assert (see pending_uploads): validate the interpolated identifier by a literal-dict lookup,
        # not a `-O`-strippable assert — the pk is baked into each literal statement.
        sql = {"events": "UPDATE events SET uploaded_at = ? WHERE event_id = ?",
               "snapshots": "UPDATE snapshots SET uploaded_at = ? WHERE snapshot_id = ?"}[table]
        self.conn.execute(sql, (uploaded_at, key))
        self.conn.commit()

    # -- meta ----------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
