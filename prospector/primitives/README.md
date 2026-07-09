# `prospector/primitives/` — CONTRACT-level write disciplines

The lowest layer of the store: the two write disciplines that make the fossil record trustworthy
(spec §1). Every durable write in the pipeline ultimately goes through here, so a torn write or a
corrupt registry snapshot is structurally impossible rather than a bug you find the hard way. These
are **built** and stable; they change only via the design thread (spec §1 is CONTRACT).

## Vendored provenance (do not strip)

Both modules were **vendored** from the sibling repo's `prophit_skunkworks/ltee_archive/` (archive
snapshot dated **2026-03-29**, vendored **2026-07-02**), with the trading ontology stripped and the
schema inverted to **envelope + JSON-payload**. The module docstrings record exactly what changed
from the source and why — **keep those provenance headers**. Hard rules: do **not** import anything
from the sibling repo's `models/` (capacity and opacity — forbidden), and do **not** re-introduce
wide typed-metric columns to the events table (the inversion to a JSON payload was deliberate).

## Modules

- **`atomic.py`** — Atomic write + SHA-256 discipline (§1a CONTRACT: a write either lands whole or
  not at all, carrying a content hash). `write_atomic()` does `tmp (same dir, random suffix) →
  write → flush → fsync(fd) → rename → fsync(dir)`, then **reads the file back and verifies** the
  SHA-256, returning the hex digest; `write_json_atomic()` is the canonical-JSON wrapper. Subtle
  bits: the dir-fsync makes the *rename itself* durable (not just the bytes) so a torn write is
  impossible even across power loss — the source relied on rename atomicity alone; tmp files use a
  same-directory random suffix (rename atomicity needs the same filesystem), so **store scans must
  ignore `*.tmp`**.
- **`sqlite_backup.py`** — Safe SQLite snapshot (§1c CONTRACT, a verbatim lesson): **never
  raw-copy a live WAL database** — that ships torn pages. `backup_sqlite()` uses Python's native
  `sqlite3.Connection.backup()` for a page-consistent snapshot with no dependency on the `sqlite3`
  CLI binary. Any upload/copy of the registry goes through this function's output, never through the
  live WAL file.

## Important to know

- These primitives are pure infrastructure — they encode *how* to write safely, never *what* the
  events mean. The envelope/payload shape lives above them in `store/`.

## See also

- Spec §1 (§1a atomic write, §1c WAL-safe backup) in
  `docs/prospector-v1-spec-rev14-2026-07-08.md`; `ARCHITECTURE.md` §2 (module map, rows for
  `primitives/atomic.py` and `primitives/sqlite_backup.py`) and its vendoring note.
- The vendoring policy in the repo constitution (`CLAUDE.md` → "Vendored store provenance").
