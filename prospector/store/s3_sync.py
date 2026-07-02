"""Fire-and-forget S3 sync — pending blobs up, registry via safe backup (spec §7, CONTRACT).

Disciplines vendored from prophit_skunkworks/ltee_archive/s3_uploader.py (fire-and-forget,
safe_upload_sqlite), archive snapshot dated 2026-03-29, vendored 2026-07-02. No commit hash
available (archive copy).

Changes from source, and why:
- The pending set comes from the registry (`uploaded_at IS NULL`), not directory walks — the
  registry is the index (spec §7); a failed upload keeps uploaded_at NULL so the next run retries.
- Every object carries its SHA-256 as S3 metadata, extending the source's hash habit end-to-end.
- The client is injectable and boto3 is imported lazily, so disabled/offline runs (bucket=None)
  never touch AWS machinery at all.

The two invariants that must hold (spec §7 implementation notes + test 4):
- Uploads are fire-and-forget: `sync` never raises — a network failure must never crash the run.
- The live WAL registry.sqlite path is never handed to the client; only a `.backup` snapshot
  goes up (raw-copying a WAL-active database ships torn pages).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prospector.primitives.sqlite_backup import backup_sqlite
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

_REGISTRY_KEY = "registry.sqlite"


def _utc_now() -> str:
    """Bookkeeping clock — all record times are UTC (spec §9), Z-suffixed like every
    other timestamp in the store."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class SyncReport:
    uploaded: int = 0
    failed: int = 0
    disabled: bool = False
    error: str | None = None


class S3Sync:
    def __init__(self, bucket: str | None, client=None):
        self.bucket = bucket
        if client is None and bucket is not None:
            import boto3  # lazy: bucket=None (disabled) and injected-client paths never import it

            client = boto3.client("s3")
        self.client = client

    def sync(self, registry: Registry, layout: StoreLayout) -> SyncReport:
        """Upload every pending event and snapshot, then a safe snapshot of the registry itself.

        `uploaded` counts event/snapshot objects; the registry snapshot is bookkeeping, not
        counted. Registry `file_path` values are store-root-relative, so each doubles as the
        S3 key. Never raises: per-object failures increment `failed` (one bad object must not
        block the rest) and leave uploaded_at NULL for retry; anything else lands in `error`.
        """
        report = SyncReport()
        try:
            if self.bucket is None:
                report.disabled = True
                return report
            for table, pk in (("events", "event_id"), ("snapshots", "snapshot_id")):
                for row in registry.pending_uploads(table):
                    key = row["file_path"]
                    try:
                        self.client.upload_file(
                            str(layout.root / key), self.bucket, key,
                            ExtraArgs={"Metadata": {"sha256": row["sha256"]}})
                        registry.mark_uploaded(table, row[pk], _utc_now())
                        report.uploaded += 1
                    except Exception as e:
                        report.failed += 1
                        report.error = f"{type(e).__name__}: {e}"
            self.upload_registry(layout.registry_path())
        except Exception as e:
            report.error = f"{type(e).__name__}: {e}"
        return report

    def upload_registry(self, db_path: Path) -> None:
        """Upload the registry as the fixed key 'registry.sqlite' via a `.backup` snapshot in a
        temp dir, deleted after upload. The live WAL file path never reaches the client
        (spec test 4)."""
        with tempfile.TemporaryDirectory(prefix="prospector-registry-") as td:
            tmp = backup_sqlite(Path(db_path), Path(td) / _REGISTRY_KEY)
            self.client.upload_file(str(tmp), self.bucket, _REGISTRY_KEY)
