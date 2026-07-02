"""Safe SQLite backup — never raw-copy a live WAL database (spec §1c, CONTRACT, verbatim lesson).

Vendored from prophit_skunkworks/ltee_archive/s3_uploader.py (safe_upload_sqlite), archive
snapshot dated 2026-03-29, vendored 2026-07-02. No commit hash available (archive copy).

Changes from source, and why:
- The source shells out to the sqlite3 CLI (`subprocess.run(["sqlite3", db, ".backup tmp"])`).
  This port uses Python's native sqlite3.Connection.backup() — the same page-consistent snapshot
  guarantee with no dependency on a CLI binary being installed.
- The discipline is unchanged: any upload of the registry goes through this function's output,
  never through the live WAL file. Raw-copying a WAL-active database ships torn pages — a
  corruption bug you would otherwise find the hard way.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_sqlite(db_path: Path, dest: Path) -> Path:
    """Produce a consistent snapshot of a (possibly WAL-active) SQLite db at `dest`."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest
