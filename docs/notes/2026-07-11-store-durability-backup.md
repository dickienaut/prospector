# Store durability — the fossil backup: build note (2026-07-11)

> **Status: CODE BUILT 2026-07-12** — `store/backup.py` (`backup_store`, `verify_restore`) +
> `pros backup` + `pros store verify-restore`, 10 offline tests (`tests/test_backup.py`). The
> **physical activation** (attach + bless the two HDDs, first backup, the one-time restore test) is a
> pending **Mac session** — see the checklist `docs/notes/2026-07-12-mac-backup-activation-checklist.md`.
> Two calls beyond this note (ratified `docs/decisions/2026-07-12-store-durability-backup.md`):
> `registry/` is INCLUDED in the backed-up trees (corrected below), and fail-loud uses a per-drive
> blessing marker.

*Build note for Claude Code. The one asset in the whole project that is **irreplaceable and un-backed-up**:
the append-only fossil store. Code and docs live in git (distributed, every clone a full copy); the store does
not — it's the runtime record on the Mini's local disk, and you cannot re-fetch two years of historical
holdings/prices/filings *as they were on those days*. If the Mini's disk dies today, the record is gone. This
lands a dual-HDD backup so it isn't. Governing: spec §7 (store layout). **Read the real store tree and any
existing backup/CLI helper first** — wire to what's there.*

## 1. The reassuring shape (why this is robust, not fragile)

The store splits into two kinds of thing, and the split makes backup easy:
- **Append-only fossils** — `events/`, `snapshots/`, `ingest/`, `baselines/`, `runs/`, **`registry/`**
  *(the last added 2026-07-12 — see the correction under §2)*. Immutable once written. **rsync-safe at any
  time:** copying them mid-run just captures whatever's committed so far; you cannot corrupt an append-only
  file by reading it. This is the irreplaceable part.
- **`registry.sqlite`** (WAL) — the *derived index*, **rebuildable** from `events/` + `snapshots/` via
  `pros store reindex`. The one mutable file, and the one you don't strictly need to back up cleanly, because
  it regenerates.

So the critical data is rsync-safe and the one tricky file is disposable. The append-only discipline pays off
here exactly as everywhere else.

## 2. Scope — the backup mechanism

A `pros backup` subcommand (prefer a CLI command, consistent with the writers' home; a script is acceptable)
that:
- **rsyncs the append-only trees** (`events/ snapshots/ ingest/ baselines/ runs/ registry/`) to **both
  HDDs**. Incremental — append-only means only new/changed files copy, fast even as the store grows.

  > **Correction (2026-07-12).** This originally listed `events/ snapshots/ ingest/ baselines/ runs/` —
  > omitting **`registry/`** (the versioned fund-identity objects, `registry/funds/{series_id}.json`).
  > Those are **not** rebuilt by `pros store reindex` (it rebuilds events/snapshots only, never the funds
  > table), so they are irreplaceable from the fossils alone and MUST be on the HDDs. Added to the tree
  > list; implemented as `FOSSIL_TREES` in `store/backup.py`. Ratified
  > `docs/decisions/2026-07-12-store-durability-backup.md`. (A separate named follow-up: teach reindex to
  > rebuild the funds table from those objects — until then the `.backup` registry copy is the instant
  > fund-identity restore.) Recorded, not silently rewritten.
- **safe-copies `registry.sqlite`** to both HDDs via the **SQLite backup API**
  (`sqlite3 SRC ".backup DEST"`, WAL-safe) — **not** a raw `cp` (a raw copy of a WAL DB mid-write can be
  inconsistent). Or omit it and rely on `reindex` at restore — but a safe-copy makes restore instant, so
  include it.
- **Targets both HDD mount points** (config `backup.targets: [...]`), and **faults loudly if a target is
  unmounted** — a silent skip of a missing drive is a backup that isn't happening; surface it (fail-loud
  discipline).

## 3. Cadence

**After each `pros run`** (a post-run step) — new data lands *and* the store is quiescent (no run in progress,
so the registry safe-copy is clean). Every run's data is on both HDDs within seconds. (The fossils are
rsync-safe anytime, so a decoupled scheduled rsync also works; post-run is cleanest — prompt capture +
guaranteed registry quiescence.) The "backup after run" wiring pairs with the **M7 autonomy core** (the
scheduler runs `pros run` then `pros backup`); until then, run `pros backup` manually after each run, or on a
standalone launchd timer.

## 4. [CRITICAL] Verify the restore — a backup you've never restored from is a hope, not a backup

Include a **restore test** and run it once, now, while the store is small:
- Point a throwaway `PROSPECTOR_STORE` at a copy of an HDD backup.
- Run `pros store reindex` (rebuilds the registry from the backed-up fossils — proving the fossils are
  complete and usable even if the registry copy were lost).
- Confirm `pros lead list` and the dashboard read it, and a spot-check of counts matches the live store.

This proves the backup is **usable**, not merely that files copied. An untested backup discovered broken
*after* the disk dies is the worst outcome — this step rules it out.

## 5. Deferred, named

- **Offsite (S3 / Backblaze) as a third copy** — the two HDDs cover disk-death, not fire/theft. Offsite is
  **M7-hardening, deferred** (and note: S3-as-*backup* differs from S3-as-*primary-store*, the full production
  design, also deferred). Dual-local now; offsite when it earns it. The mechanism here (rsync / `.backup` to
  targets) extends to an S3 target trivially when that day comes.
- **Checksums / bit-rot detection** on the HDDs — a later refinement; rsync + the restore-test suffices now.

## 6. Discipline

The backup is a **read** of the store (rsync + `.backup`), never a write to it, never near execution. The
firewall and read-only posture hold. Durability, not a new capability surface.
