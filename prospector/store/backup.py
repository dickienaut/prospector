"""Local fossil-store backup — the dual-HDD durability layer (spec §7; build note
docs/notes/2026-07-11-store-durability-backup.md).

The store splits into two kinds of thing, and the split makes backup easy:
- **Append-only fossils** (`events/ snapshots/ ingest/ baselines/ runs/ registry/`) — immutable once
  written, so copying them mid-run just captures whatever is committed so far (you cannot corrupt an
  append-only file by reading it). This is the irreplaceable part; the whole record lives here.
- **`registry.sqlite`** (WAL) — the *derived* index, rebuildable from `events/`+`snapshots/` via
  `pros store reindex`. Copied via the SQLite **`.backup` API**, NEVER a raw file copy — raw-copying a
  WAL-active database ships torn pages (the vendored `sqlite_backup` / `s3_sync` discipline, verbatim).

`registry/` (the versioned fund-identity objects, `registry/funds/{series_id}.json`) is INCLUDED beyond
the build note's original tree list: those objects are **not** rebuilt by `pros store reindex` (it
rebuilds events/snapshots only — never the funds table), so they are irreplaceable from the fossils
alone and must be on the HDDs. See `docs/decisions/2026-07-12-store-durability-backup.md`.

FAIL-LOUD (build note §2): a configured target that is not mounted-and-blessed FAULTS the backup — a
silent skip of a missing drive is a backup that isn't happening. A target is valid iff it carries the
blessing marker (default `.prospector-backup-target`), a file the operator creates ONCE per drive. We
NEVER create the target dir or the marker: an unplugged drive's mount point vanishes, so the marker is
absent → the target faults, and we never silently write the "backup" onto the internal disk under
`/Volumes` (the exact footgun this guards). Best-effort-but-loud: a missing drive faults loudly WITHOUT
skipping the healthy drive — durability wants both copies whenever both are present.

READ-ONLY posture (build note §6): the backup READS the store (walk + copy + `.backup`) and WRITES only
to external targets — never to the store, never near execution. The firewall and read-only posture hold.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from prospector.primitives.sqlite_backup import backup_sqlite
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry
from prospector.store.reindex import rebuild_registry

# The append-only fossil trees (build note §1, + `registry/` per the decision record; + `captures/`
# per the M6 slice). registry.sqlite is a file at the store ROOT (not under any of these), handled
# separately via the `.backup` API — so a tree copy can never raw-copy the WAL db or its -wal/-shm
# sidecars. `captures/` (M6 discourse capture, §6) is INCLUDED because it is the one dataset that is
# BOTH irreplaceable AND un-backfillable — a search result / fetched page cannot be re-fetched as it was
# on the day. Same reasoning that added `registry/`: index-less blob trees the fossils can't rebuild
# must be on the HDDs (reindex touches only events/snapshots). See the M6 build note §3a.
FOSSIL_TREES = ("events", "snapshots", "ingest", "baselines", "runs", "registry", "captures")
DEFAULT_MARKER = ".prospector-backup-target"
REGISTRY_NAME = "registry.sqlite"

# Trees whose files are APPEND-ONLY or first-write-wins — content is FIXED once written, so the cheap
# size+mtime quick-check can never alias a change (there is no in-place rewrite to hide). events/ is
# append-only by constitution; runs/ writes one runlog per tick; captures/ is write-once; snapshots/ is
# first-write-wins (a rewrite is the SNAP-01 divergence FAULT, not normal operation). Every OTHER tree is
# REWRITTEN in place — ingest/ (a same-day holdings re-pull / same-accession SOI re-freeze OVERWRITES;
# both writers say "ingest/ is dated substrate, not the append-only record") and registry/ (fund-identity
# objects rewritten on an identity change) — where a same-size content change landing inside the
# _MTIME_WINDOW_S window aliases to "unchanged" and leaves a PERMANENTLY stale copy (BK-2). Those trees
# get a content tiebreak (see `_needs_copy(verify_content=…)`). The default is FAIL-SAFE: this lists the
# proven-immutable trees, so a NEW tree is content-verified (correct, at worst a small extra read) unless
# it is DELIBERATELY added here. events/ + snapshots/ are the bulk of the store, so cheap-skipping them
# keeps the per-run content-verify cost bounded to the small rewritten-in-place subset.
_APPEND_ONLY_TREES = frozenset({"events", "snapshots", "runs", "captures"})


class BackupError(Exception):
    """A backup that cannot proceed AT ALL — no targets configured. A per-target mount failure is NOT
    this: those are collected in `BackupReport.failures` so healthy targets still receive the data
    while the CLI still exits loudly (best-effort-but-loud, build note §2)."""


@dataclass
class TargetReport:
    target: str
    files_copied: int = 0
    files_skipped: int = 0
    bytes_copied: int = 0
    registry_backed_up: bool = False


@dataclass
class BackupReport:
    targets: list = field(default_factory=list)   # TargetReport per SUCCESSFUL target
    failures: list = field(default_factory=list)  # (target, reason) per unmounted/unblessed target


# rsync's `--modify-window`. External backup drives are usually exFAT/FAT, whose mtime resolution is coarse
# (~2 s): `shutil.copy2` writes the source mtime and the drive TRUNCATES it, so on the next run the source
# looks "newer" by a fraction of a second and an unchanged file re-copies forever (observed: a 160 MB store
# re-copying in full every run, 1/1194 skipped). A 2 s window absorbs that truncation; a genuine same-day
# `ingest/` re-pull is hours newer (or size-differs), so it still copies. (Was 1e-6 — far tighter than any
# real filesystem's granularity.)
_MTIME_WINDOW_S = 2.0


def _same_bytes(a: Path, b: Path, *, chunk: int = 65536) -> bool:
    """Byte-compare two files of KNOWN-equal size (the caller has already checked st_size). Early-exits on
    the first differing chunk, so identical files still read fully but a real change is caught immediately.
    Used ONLY as the size-equal-within-window tiebreak for rewritten-in-place trees, so it reads at most
    the small mutable subset of the store per run — never the append-only bulk (events/ + snapshots/)."""
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca, cb = fa.read(chunk), fb.read(chunk)
            if ca != cb:
                return False
            if not ca:
                return True


def _needs_copy(src: Path, dst: Path, *, verify_content: bool = False) -> bool:
    """rsync quick-check equivalent: copy when `dst` is missing, its size differs, or `src` is newer than
    `dst` by more than `_MTIME_WINDOW_S`. Append-only fossils never change (so they skip after the first
    copy), but `ingest/` files CAN be overwritten by a same-day re-pull (`holdings.pull`) — a bare
    skip-if-exists would miss that updated fossil, so the size/mtime check (not a bare existence check)
    keeps the mirror honest. The window tolerates coarse-mtime destination filesystems (exFAT/FAT) whose
    truncation would otherwise re-copy every unchanged file each run.

    BK-2: that same window can ALIAS a real change — a same-size in-place rewrite (ingest re-pull /
    registry identity update) landing within the window reads as 'unchanged' and leaves a PERMANENTLY
    stale copy (the source mtime never advances past dst+window again). `verify_content` (set by
    `backup_store` for the rewritten-in-place trees only — see `_APPEND_ONLY_TREES`) breaks that tie by
    CONTENT: when size is equal and the mtime is inside the window, compare the bytes and copy iff they
    differ. Append-only trees pass `verify_content=False` and keep the cheap size+mtime skip."""
    if not dst.exists():
        return True
    ss, ds = src.stat(), dst.stat()
    if ss.st_size != ds.st_size:
        return True
    if ss.st_mtime > ds.st_mtime + _MTIME_WINDOW_S:
        return True
    # size-equal and within the mtime window: the quick-check says "skip" — correct for an append-only
    # file (never rewritten), but for a rewritten-in-place tree this is the BK-2 aliasing case. Break the
    # tie by content so a same-size same-window rewrite is not silently left stale on the HDD.
    if verify_content:
        return not _same_bytes(src, dst)
    return False


def _mirror_tree(src_root: Path, dst_root: Path, *, verify_content: bool = False) -> tuple[int, int, int]:
    """Incrementally mirror one fossil tree; returns (copied, skipped, bytes_copied). `shutil.copy2`
    preserves mtime (so `_needs_copy` stays stable across runs). `*.tmp` atomic-writer leftovers are
    skipped, exactly as `reindex._scan` ignores them (they are not fossils). `verify_content` is passed
    through to `_needs_copy` — True only for rewritten-in-place trees (BK-2 aliasing tiebreak)."""
    copied = skipped = nbytes = 0
    if not src_root.is_dir():
        return 0, 0, 0
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or src.name.endswith(".tmp"):
            continue
        dst = dst_root / src.relative_to(src_root)
        if _needs_copy(src, dst, verify_content=verify_content):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
            nbytes += src.stat().st_size
        else:
            skipped += 1
    return copied, skipped, nbytes


def _blessed(target: Path, marker: str) -> bool:
    """True iff `target` carries the blessing marker — a file the operator creates ONCE per drive. We
    never create it: an unplugged drive's mount point vanishes so the marker is absent → fault, and we
    never write the backup onto the internal disk. It also distinguishes the intended drive from any
    other mount that happens to sit at the same path."""
    return (target / marker).is_file()


def backup_store(layout: StoreLayout, targets, *, marker: str = DEFAULT_MARKER,
                 registry_path: Path | None = None) -> BackupReport:
    """Mirror the append-only fossil trees + a WAL-safe registry snapshot to EVERY target.

    Best-effort-but-loud (build note §2): each unmounted/unblessed target is recorded in
    `report.failures` (the CLI turns a non-empty failures list into a non-zero exit) while every
    healthy target still receives the data — a missing drive must never cause the GOOD drive to be
    skipped, but it must still fault loudly. Raises `BackupError` only when NOTHING can proceed (no
    targets configured). The registry goes through `backup_sqlite` (`.backup` API), never a raw copy."""
    tgts = [Path(t) for t in targets]
    if not tgts:
        raise BackupError(
            "no backup targets configured (backup.targets is empty) — set the HDD mount paths")
    reg = Path(registry_path) if registry_path is not None else layout.registry_path()
    report = BackupReport()
    for t in tgts:
        if not _blessed(t, marker):
            report.failures.append(
                (str(t), f"not mounted-and-blessed (no {marker!r} marker) — refusing to write"))
            continue
        # A blessed target can still fail PARTWAY through the copy — the drive fills (ENOSPC), is
        # unplugged mid-mirror, or `.backup` errors. Without this guard that OSError propagates out of
        # backup_store, and because targets are a serial for-loop it (a) skips every LATER target — the
        # healthy second drive gets NOTHING — and (b) records no failure, so the CLI (which catches only
        # BackupError) prints a raw traceback instead of the designed FAULT line. That inverts
        # best-effort-but-loud exactly when a drive degrades. Record the per-target failure (the CLI
        # turns report.failures into a non-zero exit + a named FAULT line) and press on to the next
        # drive. The torn partial mirror left on the degraded drive is reconciled by the next run's
        # incremental _needs_copy pass. Broad `except Exception` is deliberate here: for a durability
        # mirror ANY per-target fault must fall through to the other drive, never abort the whole backup
        # — and it is still loud (recorded + non-zero exit), never a silent skip.
        try:
            r = TargetReport(target=str(t))
            for tree in FOSSIL_TREES:
                # rewritten-in-place trees (not append-only) get the BK-2 content tiebreak; the
                # append-only bulk keeps the cheap size+mtime skip.
                c, s, b = _mirror_tree(layout.root / tree, t / tree,
                                       verify_content=tree not in _APPEND_ONLY_TREES)
                r.files_copied += c
                r.files_skipped += s
                r.bytes_copied += b
            if reg.is_file():
                backup_sqlite(reg, t / REGISTRY_NAME)   # WAL-safe .backup, never a raw copy of a live db
                r.registry_backed_up = True
        except Exception as e:   # noqa: BLE001 — best-effort-but-loud: record and continue to the next drive
            report.failures.append(
                (str(t), f"copy failed mid-backup ({type(e).__name__}: {e}) — the record is NOT fully "
                         "backed up to this target; retry once the drive is healthy"))
            continue
        report.targets.append(r)
    return report


def verify_restore(backup_root, scratch_root=None) -> dict:
    """Prove a backup is RESTORABLE (build note §4 — "a backup you've never restored from is a hope").

    Copies the backup's fossil trees to a THROWAWAY scratch store (so the backup is never mutated),
    rebuilds the registry from them (`pros store reindex`, proving the fossils are complete and usable
    even if the registry copy were lost), and returns the counts to spot-check against the live store.
    Reindex rebuilds events/snapshots (so `pros lead list` reads the restored record); the fund-identity
    objects under `registry/` are copied through, so their file count is reported too. NOTE: reindex does
    NOT rebuild the funds TABLE from those objects (a named follow-up — see the decision record), so the
    `.backup` registry copy remains the instant-restore path for fund identity."""
    if scratch_root is not None:
        return _verify_into(Path(backup_root), Path(scratch_root))
    with tempfile.TemporaryDirectory(prefix="prospector-restore-") as td:
        return _verify_into(Path(backup_root), Path(td))


def _verify_into(backup_root: Path, scratch: Path) -> dict:
    for tree in FOSSIL_TREES:
        src = backup_root / tree
        if src.is_dir():
            shutil.copytree(src, scratch / tree, dirs_exist_ok=True)
    layout = StoreLayout(scratch)
    registry = Registry(layout.registry_path())
    try:
        counts = rebuild_registry(layout, registry)   # rebuild from the backed-up fossils alone
        leads = len(list(registry.all_leads()))
    finally:
        registry.close()
    funds_dir = scratch / "registry" / "funds"
    fund_objects = len(list(funds_dir.glob("*.json"))) if funds_dir.is_dir() else 0
    return {"leads": leads, "events_indexed": counts["events_indexed"],
            "snapshots_indexed": counts["snapshots_indexed"],
            "fund_objects": fund_objects, "skipped": counts["skipped"]}
