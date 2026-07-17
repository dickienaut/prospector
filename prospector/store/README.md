# `prospector/store/` — the append-only fossil record + its queryable index

This is the system's memory (spec §5/§7). Everything a sensor observes lands here as an immutable
event; everything a reader asks lands here as a query. The design is **append-only by
construction, not by convention**: there is no update, delete, or mutate surface anywhere in this
package. The `events/` tree on disk (and, mirrored, in S3) is the **truth**; the SQLite `registry`
is only a queryable **index** projected over it — reindexable from the files at any time. Status:
**fully built** (Milestone 1 for the store primitives, Milestone 2 for the fund registry — see
`ARCHITECTURE.md` §9). No stubs or deferred slices live here.

## Modules

- **`envelope.py`** — the frozen **five-field** event envelope (`ts`, `lead`, `type`, `payload`,
  `schema`) and its `validate()` gate. **CONTRACT:** exactly those five keys — a missing *or extra*
  top-level key is rejected; all extension happens *inside* `payload`. `type` is a deliberately
  **open vocabulary**, never an enum — an unforeseen event type is the system's whole premise.
  `canonical_json()` gives stable bytes → stable SHA-256 across processes; `ts` must be explicit UTC.
- **`event_store.py`** — the append writer. `append()` = validate the envelope → write the JSON blob
  atomically under `events/{lead}/` → insert one `registry` index row. Malformed events raise before
  *anything* is written (they never reach file or row). File paths are stored **relative to the store
  root** so the same string doubles as an S3 key unchanged. `read_lead()` returns a lead's events in
  the fold's total order `(ts, event_id)` — this is the stream the `fold/` package folds.
- **`registry.py`** — the **WAL-mode SQLite** index (`events`, `snapshots`, `meta` tables). **Vendored**
  from `prophit_skunkworks/ltee_archive/` — keep the provenance header. **Critical inversion (§5):**
  the source used wide typed metric columns; here the `events` table *is the envelope* (ts/lead/type/
  schema + a JSON `payload` blob), so a new event type needs no migration. **Do not re-introduce typed
  metric columns.** `readonly=True` opens `mode=ro` (WAL-readable, no PRAGMA/DDL/commit) for the §11
  dashboard — a viewer can never mutate, lock, or stale-read the live store.
- **`fund_registry.py`** — the **write-path enforcement point of the HECO identity rule** (spec §2).
  Funds key on the **SEC series id** (`S######`); `_validate_identity()` raises `IdentityError` on a
  bare ticker *before any write*, so nothing downstream can anchor to a ticker. Tickers are
  **display-only** (`by_ticker()` is a lookup only, never keys anything). Every `upsert()` also emits a
  `registry.updated` event on `_system` with a `fields_changed` diff, so the record carries the
  registry's own evolution. `category_draft` is steering-only context and is never branched on.
- **`layout.py`** — the §7 path tree (`StoreLayout`), shared by the local root and the S3 mirror.
  **Structural backtest/live separation:** a live store may not sit under `backtest/` and a backtest
  store must — enforced in the constructor, not by convention. Note `prospectus_path`/`soi_path` are
  keyed on the filing **accession**, not a pull-date, so each version is frozen immutably for diffing.
  `ts_compact()` appends microseconds when present so two same-second snapshots get distinct filenames.
- **`reindex.py`** — rebuild the index from the fossil record (`pros store reindex`). It re-scans
  `events/`+`snapshots/`, re-validates, recomputes SHA-256, and `INSERT OR IGNORE`s the rows. It
  **computes nothing new — this is REPAIR, not a run-now surface** (a firewall distinction; see
  CLAUDE.md "No run-now surfaces"). `ingested_at` cannot be recovered from the files, so a rebuilt row
  takes the file mtime.
- **`s3_sync.py`** — fire-and-forget S3 mirror (spec §7), also **vendored** — keep the header. Two
  invariants: `sync()` **never raises** (a network failure must not crash the run; the pending set is
  `uploaded_at IS NULL`, so a failed object simply retries next tick), and the live WAL `registry.sqlite`
  is **never uploaded raw** — only a `.backup` snapshot goes up (raw-copying a WAL db ships torn pages).
  `boto3` is imported lazily so `bucket=None`/offline runs never touch AWS.

## Important to know

- **Append-only is the whole contract.** Nothing under `events/` is ever edited or deleted. A
  correction is a *new* event; a changed verdict is a *new* `verdict` event that supersedes the old one
  via `superseded_by` in its payload — never an in-place edit. `insert_event` is `INSERT OR IGNORE`
  (idempotent re-ingest), and there is intentionally no update/delete method for events.
- **Truth vs. index.** If the `registry.sqlite` is ever lost or corrupt, it is fully rebuildable from
  the `events/`+`snapshots/` trees. Reads go through the registry; writes go through both.
- The `snapshots.py` module that once lived here now lives in `fold/` (`ARCHITECTURE.md` §2) — the
  store owns event/snapshot *storage*, the fold owns the *reactive snapshot policy* that decides when
  to write one.

## See also

- Spec §5 (data model / a lead is the fold) and §7 (store tree, S3, backtest separation) in
  `docs/spec.md`; `ARCHITECTURE.md` §2 (module map), §3 (the spine),
  §9 (built vs deferred). Identity rule detail: `docs/decisions/2026-07-06-identity-integrity.md`.
