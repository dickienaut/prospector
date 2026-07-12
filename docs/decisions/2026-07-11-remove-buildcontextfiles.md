# Removed the `BuildContextFiles/` folder

*Decision record, 2026-07-11. Deleted the top-level `BuildContextFiles/` folder — an initial-inspiration
context dump that played no role in the project. Recorded so the removal is traceable and the "where did it
go / was provenance lost?" question is answered: **nothing was lost.***

## What was removed

The 11 tracked files under `BuildContextFiles/`: `prospector-v1-spec-rev3-2026-07-01.md`,
`thesis-smoke-detector-design-brief.md`, and `ltee_archive/` (`archiver.py`, `registry.py`, `s3_uploader.py`,
`forensics.py`, `schemas.py`, `snapshot_policy.py`, `__init__.py`, `ltee_archive.md`, `archive_manifest.json`).
(rho-G had already been removed from here earlier — see `2026-07-11-docs-reorganization.md`.)

## Why it was safe (verified by read-only audit before deletion)

- **No dependency.** A repo-wide search for `BuildContextFiles` found only 2 prose mentions in `docs/` — no
  Python import, no test fixture, no config/`pyproject`/`uv.lock` entry resolves to it. `BuildContextFiles/` is
  not a package on any path. Deleting it broke no code, test, or build (`uv run pytest` stays green).
- **Nothing unique lost.** The 2 markdown files are **byte-identical (SHA-256)** to
  `docs/history/prospector-v1-spec-rev3-2026-07-01.md` and `docs/origins/thesis-smoke-detector-design-brief.md`.
  The `ltee_archive/` bundle is a **pre-port raw snapshot** whose canonical source is the **sibling repo
  `prophit_skunkworks/ltee_archive/`** (per the "Vendored store provenance" section of `CLAUDE.md`), already
  consumed and rewritten into `prospector/primitives/` (`atomic.py`, `sqlite_backup.py`) with provenance
  headers that cite the sibling repo — never `BuildContextFiles/`. So the folder held nothing the sibling repo
  (its true source) and the repo's own docs did not already carry.
- **Git-recoverable.** All 11 files were tracked; this removal preserves every byte in history
  (`git show <sha>:BuildContextFiles/…` restores any of them). Consistent with the repo's "never truly lose
  the past" — removed from the working tree, not from history.

## Two stale references left as-is (deliberately)

`docs/decisions/2026-07-11-docs-reorganization.md:65` (an immutable decision fossil) and
`docs/notes/prospector_full_review_claude_science.md:461` (a dated QA-review snapshot) each mention
`BuildContextFiles/` in passing. Both are **left verbatim** — editing them would rewrite the past, and each
remains true as a historical statement. The now-stale path is harmless (it names no live dependency).
