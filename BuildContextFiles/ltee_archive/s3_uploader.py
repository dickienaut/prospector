"""S3 upload utilities for the Lenski Ledger archive.

Handles post-graduation uploads and provides building blocks for the
cron-based sync scripts. All uploads are fire-and-forget — network
failures must never crash the training loop.
"""

import os
import subprocess
import tempfile
from pathlib import Path


class S3ArchiveUploader:

    def __init__(self, bucket="prophit-brains-archive", prefix=""):
        import boto3
        self.bucket = bucket
        self.prefix = prefix
        self.s3 = boto3.client("s3")

    def upload_file(self, local_path, s3_key, storage_class="STANDARD"):
        """Upload a single file to S3."""
        self.s3.upload_file(
            str(local_path), self.bucket, s3_key,
            ExtraArgs={"StorageClass": storage_class},
        )

    def upload_generation_metadata(self, archive_root, lineage, generation):
        """Upload all metadata files for a generation (no .pt checkpoints).

        Uploads: gen_meta.json, dna config, telemetry.jsonl, exploit_log.json, sidecar/*.json
        """
        root = Path(archive_root)
        gen_dir = root / lineage / f"gen_{generation:03d}"
        s3_prefix = f"{self.prefix}ltee_archive/{lineage}/gen_{generation:03d}"

        if not gen_dir.exists():
            return

        # Upload individual metadata files
        for pattern in ["gen_meta.json", f"dna_{lineage}.json", "telemetry.jsonl", "exploit_log.json"]:
            path = gen_dir / pattern
            if path.exists():
                self.upload_file(path, f"{s3_prefix}/{pattern}")

        # Upload sidecar directory
        sidecar_dir = gen_dir / "sidecar"
        if sidecar_dir.exists():
            for json_file in sidecar_dir.glob("*.json"):
                self.upload_file(json_file, f"{s3_prefix}/sidecar/{json_file.name}")

    def upload_checkpoint(self, ckpt_path, s3_key):
        """Upload a .pt checkpoint with Intelligent-Tiering storage class."""
        self.upload_file(ckpt_path, s3_key, storage_class="INTELLIGENT_TIERING")

    def safe_upload_sqlite(self, db_path):
        """Safely backup and upload SQLite database.

        Uses sqlite3 .backup API to produce a consistent snapshot,
        then uploads the backup file. Never raw-syncs a live WAL database.
        """
        db_path = str(db_path)
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            subprocess.run(
                ["sqlite3", db_path, f".backup {tmp_path}"],
                check=True, capture_output=True, text=True,
            )
            self.upload_file(tmp_path, f"{self.prefix}registry.sqlite")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
