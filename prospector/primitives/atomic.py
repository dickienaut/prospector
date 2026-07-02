"""Atomic write + SHA-256 discipline (spec §1a, CONTRACT).

Vendored from prophit_skunkworks/ltee_archive/archiver.py (save_checkpoint's tmp-then-rename +
post-write hash pattern), archive snapshot dated 2026-03-29, vendored 2026-07-02. No commit hash
available (archive copy, not a git checkout).

Changes from source, and why:
- Added fsync on the file before rename and on the containing directory after rename. The source
  relied on rename atomicity alone; the spec requires the full tmp -> fsync -> rename discipline
  so a torn write is impossible even across power loss.
- Tmp files get a random suffix in the same directory (rename atomicity requires same
  filesystem; the suffix tolerates concurrent writers). Store scans must ignore "*.tmp".
- Generalized from torch.save to bytes/JSON — no torch in this repo.
- Kept the source's post-write hash habit, hardened into a read-back verify.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from prospector.store.envelope import canonical_json


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, data: bytes) -> str:
    """Write bytes so that readers only ever see a complete, fsynced file.

    tmp (same dir, random suffix) -> write -> flush -> fsync(fd) -> rename -> fsync(dir),
    then read back and verify the SHA-256. Returns the hex digest.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid4().hex[:8]}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
        # fsync the directory so the rename itself is durable, not just the bytes.
        # os.fsync on file and dir only (no macOS F_FULLFSYNC): dev box is macOS, prod is Linux.
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    expected = hashlib.sha256(data).hexdigest()
    actual = sha256_file(path)
    if actual != expected:
        raise OSError(f"post-write hash mismatch at {path}: {actual} != {expected}")
    return actual


def write_json_atomic(path: Path, obj) -> str:
    """Canonical-JSON write_atomic. Returns the SHA-256 of the written bytes."""
    return write_atomic(path, canonical_json(obj).encode("utf-8"))
