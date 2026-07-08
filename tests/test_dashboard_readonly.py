"""Regression: the §11 dashboard must be READ-ONLY at the storage layer (finding N1).

app.py's module docstring states the §11 CONTRACT: "read-only ... never mutates the store." But the
comment "# read-only" at the ResolutionMachine construction is the ONLY enforcement — at the storage
layer the viewer opens the store READ-WRITE. Merely rendering the dashboard:
  - Registry.__init__ runs `PRAGMA journal_mode=WAL` + executescript(_DDL) + commit()  (registry.py)
  - recent_runs() -> _ensure_table() runs executescript(_DDL) + commit()                (runlog.py)
  - ResolutionMachine.__init__ runs executescript(_DDL) + commit()                       (resolution.py)
So viewing (a) flips the runner's DB into WAL mode and creates -wal/-shm sidecars — a persistent
mutation; and (b) on a store the operator mounts read-only (the natural way to ENFORCE the firewall),
the first write raises `sqlite3.OperationalError: attempt to write a readonly database` and the page
dies with an unhandled exception before it renders.

test_dashboard_app.py's smoke uses a WRITABLE tmp store, so it exercises only the happy path and
cannot catch either failure. These tests add the read-only-mount and the store-immutability cases.

Run under a non-root uid (chmod-based read-only is a no-op for root); the read-only-mount test
self-skips if the platform lets the write through, so it never yields a false pass.

NOTE ON WHY WE DON'T TEST FOR -wal/-shm SIDECARS: the store is LEGITIMATELY in WAL mode already —
the runner's Registry opens WAL on every write, so the sidecars are the runner's doing, not the
viewer's, and they appear/disappear with checkpoint/close timing (a flaky, invalid discriminator).
The robust signals are instead: (a) the viewer must render against a genuinely read-only-mounted
store, and (b) rendering must not MUTATE any store file (mtime/size). A proper read-only viewer
(`sqlite3.connect("file:...?mode=ro", uri=True)`, no DDL/PRAGMA/commit) satisfies both; the current
read-write viewer fails both.

SECOND-ORDER FINDING (documented on the read-only-mount test below): opening the VIEWER read-only is
necessary but NOT sufficient for a read-only MOUNT. A WAL-mode store cannot be read on read-only
media even by a correct mode=ro connection, because SQLite must write the -shm wal-index to read the
WAL. Serving the store read-only therefore ALSO requires checkpointing it out of WAL first — a fact
the original N1 write-up glossed. `immutable=1` sidesteps it but is unsafe against the live runner
(it tells SQLite the file never changes, so concurrent runner writes are invisible / may corrupt the
read), so it is NOT the right general answer.
"""

import os
import stat

import pytest

from prospector.identity.resolution import ResolutionMachine
from prospector.runner.runlog import RunLog, write_run_log
from prospector.store.event_store import EventStore

st_testing = pytest.importorskip("streamlit.testing.v1")


def _seed(layout, registry):
    """Seed the store the way a RUNNER TICK leaves it — this is the production-faithful precondition
    for a read-only viewer. A raw event seed alone is NOT enough: the runner creates the working
    tables (`runs` via write_run_log, `resolution_queue` via the ResolutionMachine it constructs in
    _run_sensors) on every tick, so by the time any dashboard opens they exist. Constructing a
    ResolutionMachine here (while the fixture store is still writable) reproduces that — WITHOUT it a
    correctly read-only viewer would hit `no such table: resolution_queue`. (NOTE: the existing
    test_dashboard_app.py smoke test omits this and passes only because the current buggy dashboard
    opens read-WRITE and creates the table on the fly — that seed must gain this line when N1 is
    fixed, or the smoke test flips red for the right reason.)"""
    ResolutionMachine(registry, EventStore(layout, registry), None, None)  # creates resolution_queue
    store = EventStore(layout, registry)
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "xcorr-abc1234567", "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:01Z", "lead": "xcorr-abc1234567", "type": "xcorr.departure",
                  "payload": {"display": "XLK×XLU", "z": 3.2, "market_stress": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "_system", "type": "launch.unverified",
                  "payload": {"ticker": "NEWX", "series_id": "S000000009",
                              "detected_at": "2026-07-06T00:00:00Z"}, "schema": 1})
    write_run_log(layout, registry, RunLog(run_id="r1", ts="2026-07-06T00:00:00Z",
                                            date="2026-07-06", pushed=True))


def _render(store_root, monkeypatch):
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    monkeypatch.setenv("PROSPECTOR_STORE", str(store_root))
    return st_testing.AppTest.from_file("prospector/dashboard/app.py").run(timeout=60)


def _journal_mode(db):
    import sqlite3
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()


def test_viewing_does_not_flip_the_stores_journal_mode(layout, registry, monkeypatch):
    # A durable, observable mutation that a fully-seeded store still exposes (the file-content snapshot
    # does NOT, because the dashboard's CREATE TABLE IF NOT EXISTS DDL is a steady-state no-op that
    # writes nothing): the read-write viewer runs `PRAGMA journal_mode=WAL` on open. When an operator
    # has PREPARED the store for read-only serving by checkpointing it out of WAL into rollback-journal
    # (delete) mode — the state the read-only-mount test below shows is *required* to serve a WAL store
    # read-only — that PRAGMA silently flips the persistent journal mode back to WAL. A read-only
    # (mode=ro) viewer cannot and does not. RED today (journal mode goes delete -> wal on view); GREEN
    # once the viewer opens read-only. No chmod, so meaningful regardless of uid.
    _seed(layout, registry)
    registry.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    registry.conn.execute("PRAGMA journal_mode=DELETE")
    registry.conn.commit()
    registry.close()

    db = layout.registry_path()
    assert _journal_mode(db) == "delete"  # precondition: store prepared for read-only serving

    at = _render(layout.root, monkeypatch)
    assert not at.exception, f"dashboard raised while rendering: {at.exception}"

    assert _journal_mode(db) == "delete", (
        "viewing the dashboard flipped the store's persistent journal_mode delete -> wal — the viewer "
        "opened the store read-WRITE and ran `PRAGMA journal_mode=WAL`, a durable mutation of a store "
        "an operator had prepared for read-only serving; a read-only (mode=ro) viewer cannot (N1)")


def test_dashboard_renders_against_a_readonly_store(layout, registry, monkeypatch, tmp_path):
    # The firewall enforced the natural way: the operator mounts the store read-only. A true read-only
    # viewer renders; the current RW viewer raises "attempt to write a readonly database". RED today.
    #
    # SUBTLE PRECONDITION (a finding in its own right — see the module note): fixing the VIEWER to
    # mode=ro is necessary but NOT sufficient for a read-only MOUNT. A WAL-mode store cannot be opened
    # read-only on read-only media at all — SQLite must write the -shm wal-index to read the WAL, so
    # even a correct mode=ro viewer raises "attempt to write a readonly database". Read-only-mount
    # operation therefore ALSO requires the store to be checkpointed out of WAL first (or immutable=1,
    # which is unsafe against the live runner — it voids SQLite's warranty on a file that still
    # changes). We reproduce the realistic correct setup: checkpoint + return to rollback-journal mode
    # (what a "prepare store for read-only serving" step must do) BEFORE the read-only mount.
    _seed(layout, registry)
    registry.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    registry.conn.execute("PRAGMA journal_mode=DELETE")
    registry.conn.commit()
    registry.close()

    db = layout.registry_path()
    original = stat.S_IMODE(os.stat(db).st_mode)
    # Make the db AND its directory read-only (a write of any kind — WAL PRAGMA, DDL, commit, or a
    # -shm/-wal sidecar — now fails at the OS layer, the way an immutable mount enforces the firewall).
    os.chmod(db, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    os.chmod(db.parent, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)

    # Guard against a false pass: if this platform/uid lets a write through, the read-only premise
    # doesn't hold and the test can't prove anything — skip rather than pass.
    import sqlite3
    try:
        probe = sqlite3.connect(str(db))
        probe.execute("CREATE TABLE _probe_ro (x)")
        probe.commit()
        probe.close()
        pytest.skip("store is not actually read-only for this uid (root?); N1 test is meaningless")
    except sqlite3.OperationalError:
        pass  # good: the store really is read-only
    finally:
        try:
            probe.close()
        except Exception:
            pass

    try:
        at = _render(layout.root, monkeypatch)
        assert not at.exception, (
            f"dashboard crashed on a read-only store instead of rendering — the viewer opened it "
            f"read-write (WAL/DDL/commit) rather than mode=ro (N1): {at.exception}")
    finally:
        os.chmod(db.parent, 0o700)
        os.chmod(db, original)
