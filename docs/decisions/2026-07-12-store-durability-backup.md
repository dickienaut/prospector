# Store durability — `pros backup`: the `registry/` inclusion, the fail-loud blessing marker, best-effort-but-loud

*Decision record, 2026-07-12. Ratifies the calls made building the fossil-store backup (`store/backup.py`,
`pros backup`, `pros store verify-restore`) from the build note
`docs/notes/2026-07-11-store-durability-backup.md`. Governing: spec §7 (store layout). Branch
`store-durability-backup`.*

## Context

The append-only fossil store is the one asset that is **irreplaceable and un-backed-up** — it lives on
the Mini's local disk, and you cannot re-fetch two years of holdings/prices/filings *as they were on those
days*. `pros backup` mirrors the append-only trees + a WAL-safe registry snapshot to one or more HDD
targets; `pros store verify-restore` proves a backup restores. The command is a **read** of the store
(walk + copy + `.backup`), writing only to external targets — never to the store, never near execution, so
the firewall and read-only posture hold, and it is in the same allowed class as `store reindex` (computes
nothing new), **not** a run-now surface.

## Decision 1 — `registry/` is INCLUDED in the backed-up trees *(a build-note correction)*

The note's tree list was `events/ snapshots/ ingest/ baselines/ runs/`. That **omitted `registry/`** —
the versioned fund-identity objects `registry/funds/{series_id}.json`. Those are **not** reconstructed by
`pros store reindex`: reindex rebuilds the events and snapshots index only (it scans `events/` +
`snapshots/`), and it never rebuilds the `funds` table. So the fund objects are **irreplaceable from the
fossils alone** and must be on the HDDs. `FOSSIL_TREES` in `store/backup.py` includes `registry/`;
`registry.sqlite` (the derived WAL index) stays handled **separately** via the `.backup` API — a tree copy
can never raw-copy the WAL db or its `-wal`/`-shm` sidecars.

**Named follow-up (not this slice):** teach `pros store reindex` to also rebuild the `funds` table from the
`registry/funds/*.json` objects, so a fossils-only restore recovers fund identity too. Until then the
`.backup` registry copy is the instant fund-identity restore path, and both (the `.backup` copy **and** the
`registry/` objects) are on the HDDs — so nothing is lost; only the *reindex-from-fossils* path is
currently incomplete for funds. `verify_restore` reports the fund-object file count so the gap is visible.

## Decision 2 — fail-loud via a per-drive blessing marker, never a bare path check

The note: "faults loudly if a target is unmounted — a silent skip of a missing drive is a backup that
isn't happening." Implemented with a **blessing marker**: a target is valid iff it carries a marker file
(default `.prospector-backup-target`) the operator creates **once per drive**. We **never** create the
target directory or the marker.

**Why a marker, not just "does the path exist."** On macOS an unplugged drive's mount point (`/Volumes/…`)
simply vanishes. A naive `mkdir -p <target>` would then recreate the path **on the internal boot disk** and
write the "backup" there — silently succeeding while backing up nothing durable (the footgun). Requiring a
pre-existing marker means an unplugged drive faults (no marker present), we never write to a phantom path,
and — as a bonus — the marker distinguishes the *intended* backup drive from any other volume that happens
to mount at the same path. The blessing is a one-time operator step, captured in the Mac activation
checklist.

## Decision 3 — best-effort-but-loud across multiple targets

With two HDDs, if one is missing the backup **still writes to the healthy one** and **still faults loudly**
about the missing one (its failure is recorded in `report.failures`; the CLI turns a non-empty failures
list into a non-zero exit). Rationale: durability wants both copies whenever both are present — a missing
drive must never cause the *good* drive to be skipped — but the operator must still be told loudly that the
record is not fully backed up. `backup_store` raises `BackupError` only when nothing can proceed (no targets
configured), which is why the repo config ships `backup.targets: []`: `pros backup` faults until the Mini's
drive paths are set, rather than silently no-op'ing on a dev machine.

## Also decided (in passing)

- **Incremental by size/mtime, not bare existence.** Append-only fossils skip after the first copy, but
  `ingest/` files can be overwritten by a same-day re-pull (`holdings.pull`), so a bare skip-if-exists would
  miss that updated fossil. `_needs_copy` uses the rsync quick-check (missing / size-differs / src-newer).
- **Native Python copy, not shelling out to `rsync`/`sqlite3`.** Consistent with the repo's stated
  preference (see `primitives/sqlite_backup.py`, which ports the sqlite3-CLI `.backup` to the native
  `Connection.backup()` API precisely to avoid a CLI-binary dependency). `shutil.copy2` preserves mtime so
  the incremental check stays stable.
- **Cadence is not wired into `pros run`.** The "backup after each run" cadence is a launchd/wrapper concern
  (the scheduler runs `pros run && pros backup`), landing with the **M7 autonomy core** — not a code change
  to `run_tick` (which would blur the tick's scope). Until then: run `pros backup` manually or on a
  standalone timer (see the checklist).

## Scope / what did NOT change

No change to the store write path, the fold, or any sensor. `pros backup` and `pros store verify-restore`
are the only new surfaces (both reads; the pinned command-tree test is updated to include them). Offsite
(S3/Backblaze) as a third copy and bit-rot checksums remain deferred M7-hardening, named in the build note.
