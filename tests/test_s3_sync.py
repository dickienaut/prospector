"""Fire-and-forget S3 sync (spec §7 + §10 test 4, CONTRACT): pending blobs go up under
their registry file_path keys with sha256 metadata, failures are reported and retried but
never raised, and the live WAL registry.sqlite never reaches the client — only a `.backup`
snapshot does. A hand-rolled spy client records every call; one happy path runs against
moto's in-process S3 (offline: moto intercepts at the botocore layer, so the conftest
network guard never sees a socket)."""

import sqlite3
from pathlib import Path

import pytest

import prospector.store.s3_sync as s3_sync_module
from prospector.fold.snapshots import write_snapshot
from prospector.primitives.sqlite_backup import backup_sqlite
from prospector.store.envelope import parse_ts
from prospector.store.event_store import EventStore
from prospector.store.s3_sync import S3Sync, SyncReport

BUCKET = "prospector-test"


class SpyClient:
    """boto3-shaped spy: records every method call with its args; raises on demand."""

    def __init__(self, fail_keys=()):
        self.calls = []
        self._fail_keys = set(fail_keys)

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
        self.calls.append({"method": "upload_file", "Filename": Filename,
                           "Bucket": Bucket, "Key": Key, "ExtraArgs": ExtraArgs})
        if Key in self._fail_keys:
            raise ConnectionError(f"injected network failure for {Key}")

    def __getattr__(self, name):  # any other client method: recorded, never an error
        def record(*args, **kwargs):
            self.calls.append({"method": name, "args": args, "kwargs": kwargs})
        return record

    def uploads(self):
        return [c for c in self.calls if c["method"] == "upload_file"]

    def keys(self):
        return [c["Key"] for c in self.uploads()]


@pytest.fixture
def populated(layout, registry):
    """Two events + one snapshot, all pending (fresh store: nothing uploaded yet)."""
    store = EventStore(layout, registry)
    written = [
        store.append({"ts": "2026-07-01T00:00:00Z", "lead": "ld_one", "type": "lead.spawned",
                      "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False},
                      "schema": 1}),
        store.append({"ts": "2026-07-02T00:00:00Z", "lead": "ld_one", "type": "xcorr.tick",
                      "payload": {"z": 2.9}, "schema": 1}),
    ]
    snap = write_snapshot(layout, registry, "ld_one", {"status": "active", "event_count": 2},
                          "state_change", "2026-07-02T00:00:00Z")
    return {"written": written,
            "snapshot_key": snap.relative_to(layout.root).as_posix()}


# -- happy path: keys, metadata, bookkeeping ---------------------------------------

def test_pending_blobs_upload_under_registry_keys_with_sha_metadata(populated, layout,
                                                                    registry):
    spy = SpyClient()
    report = S3Sync(BUCKET, client=spy).sync(registry, layout)

    assert report == SyncReport(uploaded=3, failed=0, disabled=False, error=None)
    expected = {w.file_path: w.sha256 for w in populated["written"]}
    expected[populated["snapshot_key"]] = registry.latest_snapshot("ld_one")["sha256"]
    blob_uploads = [c for c in spy.uploads() if c["Key"] != "registry.sqlite"]
    assert {c["Key"] for c in blob_uploads} == set(expected)
    for c in blob_uploads:
        # file_path doubles as the S3 key: the local file is that same string under root.
        assert c["Filename"] == str(layout.root / c["Key"])
        assert c["Bucket"] == BUCKET
        assert c["ExtraArgs"] == {"Metadata": {"sha256": expected[c["Key"]]}}

    for table in ("events", "snapshots"):
        assert registry.pending_uploads(table) == []
        for row in registry.conn.execute(f"SELECT uploaded_at FROM {table}"):
            parse_ts(row["uploaded_at"])  # set after success, ISO-8601 UTC


def test_second_sync_uploads_nothing_new(populated, layout, registry):
    S3Sync(BUCKET, client=SpyClient()).sync(registry, layout)
    spy2 = SpyClient()
    report2 = S3Sync(BUCKET, client=spy2).sync(registry, layout)

    assert report2 == SyncReport(uploaded=0, failed=0, disabled=False, error=None)
    # Only the registry snapshot goes up again — bookkeeping, not counted, not a re-upload.
    assert spy2.keys() == ["registry.sqlite"]


# -- fire-and-forget: failures reported, never raised, always retried ---------------

def test_failed_upload_is_reported_not_raised_and_retried_next_run(populated, layout,
                                                                   registry):
    victim = populated["written"][0]
    spy = SpyClient(fail_keys={victim.file_path})
    report = S3Sync(BUCKET, client=spy).sync(registry, layout)  # must not raise

    assert report.uploaded == 2 and report.failed == 1 and report.disabled is False
    assert "ConnectionError" in report.error and victim.file_path in report.error
    # One bad object never blocks the rest: the other event and the snapshot still went up.
    assert set(spy.keys()) >= {populated["written"][1].file_path, populated["snapshot_key"]}

    row = registry.conn.execute("SELECT uploaded_at FROM events WHERE event_id = ?",
                                (victim.event_id,)).fetchone()
    assert row["uploaded_at"] is None  # stays NULL -> next run retries
    assert [r["event_id"] for r in registry.pending_uploads("events")] == [victim.event_id]

    retry = SpyClient()
    report2 = S3Sync(BUCKET, client=retry).sync(registry, layout)
    assert report2.uploaded == 1 and report2.failed == 0
    assert victim.file_path in retry.keys()


def test_registry_upload_failure_lands_in_error_never_an_exception(populated, layout,
                                                                   registry):
    spy = SpyClient(fail_keys={"registry.sqlite"})
    report = S3Sync(BUCKET, client=spy).sync(registry, layout)  # must not raise
    assert report.uploaded == 3 and report.failed == 0
    assert report.error is not None and "ConnectionError" in report.error


# -- spec §10 test 4 (CONTRACT): the live WAL file never reaches the client ---------

def test_live_registry_and_wal_never_reach_the_client(populated, layout, registry,
                                                      monkeypatch):
    backup_calls = []

    def recording_backup(db_path, dest):
        backup_calls.append({"src": Path(db_path), "dest": Path(dest)})
        return backup_sqlite(db_path, dest)

    monkeypatch.setattr(s3_sync_module, "backup_sqlite", recording_backup)

    live = layout.registry_path()
    assert Path(str(live) + "-wal").exists()  # the live db IS WAL-active during sync
    spy = SpyClient()
    report = S3Sync(BUCKET, client=spy).sync(registry, layout)
    assert report.failed == 0 and report.error is None

    filenames = [c["Filename"] for c in spy.uploads()]
    assert str(live) not in filenames  # the live path never handed to the client
    assert not any(f.endswith("-wal") or f.endswith("-shm") for f in filenames)

    [reg_call] = [c for c in spy.uploads() if c["Key"] == "registry.sqlite"]
    assert reg_call["Filename"] != str(live)
    # The uploaded file is exactly the .backup API's output for the live db...
    assert backup_calls == [{"src": live, "dest": Path(reg_call["Filename"])}]
    # ...and the backup temp is cleaned up after the upload.
    assert not Path(reg_call["Filename"]).exists()


# -- disabled: bucket=None touches nothing ------------------------------------------

def test_bucket_none_is_disabled_with_zero_client_calls(populated, layout, registry):
    spy = SpyClient()
    report = S3Sync(None, client=spy).sync(registry, layout)

    assert report == SyncReport(uploaded=0, failed=0, disabled=True, error=None)
    assert spy.calls == []
    # Nothing marked: everything stays pending for when a bucket is configured.
    assert len(registry.pending_uploads("events")) == 2
    assert len(registry.pending_uploads("snapshots")) == 1


def test_bucket_none_never_builds_a_boto3_client():
    assert S3Sync(None).client is None


# -- one end-to-end pass against moto's in-process S3 -------------------------------

def test_happy_path_against_moto_s3(populated, layout, registry, tmp_path, monkeypatch):
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(var, "testing")  # fake creds: the credential chain stays local
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")

    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        report = S3Sync(BUCKET, client=client).sync(registry, layout)

        assert report == SyncReport(uploaded=3, failed=0, disabled=False, error=None)
        keys = {o["Key"] for o in client.list_objects_v2(Bucket=BUCKET)["Contents"]}
        assert keys == {w.file_path for w in populated["written"]} \
            | {populated["snapshot_key"], "registry.sqlite"}

        w = populated["written"][0]
        head = client.head_object(Bucket=BUCKET, Key=w.file_path)
        assert head["Metadata"]["sha256"] == w.sha256

        # The mirrored registry snapshot is a healthy database with the synced rows.
        body = client.get_object(Bucket=BUCKET, Key="registry.sqlite")["Body"].read()
        mirror = tmp_path / "mirror.sqlite"
        mirror.write_bytes(body)
        conn = sqlite3.connect(str(mirror))
        try:
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()
