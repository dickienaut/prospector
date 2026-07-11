# Prospector regression tests — N1, N2, N3

Three regression tests for the confirmed BUGs from the 2026-07-07 follow-up review
(`prospector_followup_review_2026-07-07.md`). Each is **RED against the code as shipped**
(reproduces the bug) and **GREEN against the documented fix** — and each asserts *behaviour*,
not a specific implementation, so it does not lock the fix into one shape.

All three were validated against the live snapshot (repo tarball fetched 2026-07-07,
175 files). Environment: Python 3.12, the repo's own deps + streamlit for the dashboard AppTest.

| Test file | Finding | Targets | RED shows | GREEN needs |
|---|---|---|---|---|
| `test_runner_idempotency.py` | **N2** | `runner.run_tick` / `resolution.register_launch` | a same-UTC-day re-tick re-emits `launch.unverified` (1→2) and re-enqueues `resolution.failed` (1→2→3) | the tick idempotent on the same store within a day |
| `test_prices_panel_dedup.py` | **N3** | `ingest.prices.parse_tiingo` / `build_panel` | a duplicate-date row yields a non-unique DatetimeIndex; the outer join broadcasts a co-listed ticker's value onto both rows — a fabricated cross-observation | `build_panel` to dedup dates or fault (fix-agnostic) |
| `test_dashboard_readonly.py` | **N1** | `dashboard/app.py` + storage layer | the read-only §11 dashboard opens the store **read-write** — flips a serving-prepared store's `journal_mode` back to WAL, and crashes on a read-only mount | the viewer to open the store read-only |

---

## How to run

```bash
# from the repo root, with the dashboard extra installed (streamlit)
python -m pytest tests/test_runner_idempotency.py \
                 tests/test_prices_panel_dedup.py \
                 tests/test_dashboard_readonly.py -v
```

Against the code as shipped: **6 RED**. After the fixes in `reference_fixes.diff`: **6 GREEN**,
and the full existing suite stays green (475 passed, 1 skipped — see "Regression gate" below).

The tests follow the house convention exactly: `tests/` is a package (`__init__.py` present) and
no test imports a sibling test module, so `test_runner_idempotency.py` is **self-contained**
(its own `_deps`/`_edgar`/`_fetch_mf_only`/`_seed_prior_mf` harness, mirroring
`test_runner_mandate.py` / `_xcorr.py` / `_soi_corroboration.py`).

---

## What each test asserts, and why it is shaped that way

### N2 — `test_runner_idempotency.py`

The runner's own docstring claims *"two cold runs over the same store produce identical events"*
(statelessness CONTRACT, §9). The existing `test_two_cold_runs_produce_identical_events` proves a
**weaker** thing — two *separate fresh stores*, each run *once* — so it never exercises a re-tick
against a store that already holds the day's events. A same-UTC-day re-run is a real operational
path (a cron catch-up after a missed/late tick; an operator re-running `pros run` after the
soft-fault path returned a RunLog and invited a retry).

- `test_same_store_retick_same_day_does_not_double_write` — runs the **same store** twice on the
  same UTC day and asserts the append-only record is unchanged by the second run. RED: the second
  run re-detects the identical `(symbol, seriesId)` (because `_load_prior_mf_snapshot` selects the
  prior from dates *strictly* `< today`) and `register_launch` re-emits `launch.unverified` with a
  fresh `uuid4` event id — nothing dedupes.
- `test_three_reticks_do_not_accumulate_resolution_failures` — guards the compounding case, so a
  partial fix that dedupes `launch.unverified` but leaves the resolution path re-enqueuing still
  fails.

### N3 — `test_prices_panel_dedup.py`

`build_panel` already faults loudly on an empty frame and on a duplicate **ticker**, but silently
accepts a duplicate **date**: `_tidy` drops NaN and sorts but never de-duplicates on date. Built
through the **real** `parse_tiingo` (not a hand-made frame) so the test tracks the actual ingest
path.

- `test_parse_tiingo_frame_has_unique_dates` — the tidy frame `build_panel` trusts must not carry a
  duplicate date.
- `test_build_panel_rejects_or_dedups_duplicate_dates` — the behavioural guarantee, **fix-agnostic**:
  after `build_panel` the index is unique, *whether* the fix dedups in `_tidy` (`keep="last"`) or
  faults loudly like the duplicate-ticker guard. RED output literally shows a clean ticker's single
  value broadcast onto both duplicate rows — the fabricated cross-observation §3 forbids.

### N1 — `test_dashboard_readonly.py`

The §11 dashboard is supposed to be read-only, but at the storage layer it opens the store
**read-write**: `Registry.__init__` runs `PRAGMA journal_mode=WAL` + `executescript(_DDL)` + commit,
and `recent_runs`/`ResolutionMachine` each run DDL + commit.

- `test_viewing_does_not_flip_the_stores_journal_mode` — the durable, observable signal that survives
  a fully-seeded store. Once an operator has prepared the store for read-only serving (checkpointed
  out of WAL into rollback-journal `delete` mode), merely viewing runs `PRAGMA journal_mode=WAL` and
  silently flips it **back** to WAL. A read-only (`mode=ro`) viewer cannot. No chmod, so it is
  meaningful regardless of uid.
- `test_dashboard_renders_against_a_readonly_store` — the firewall enforced the natural way: the
  operator mounts the store read-only (chmod). RED: the viewer crashes with
  *"attempt to write a readonly database"* at `app.py` (the `PRAGMA journal_mode=WAL`). Self-skips if
  the platform/uid lets the write through (so it never yields a false pass; uid here is 501, non-root).

---

## Two findings the test-writing surfaced (beyond the original N1 write-up)

Writing tests that must actually go green forced running the code in the exact configurations the
review only described — and two things turned up that the follow-up report did **not** capture. Both
are the "assumption without evidence" class worth flagging.

**1. Fixing the viewer to `mode=ro` is necessary but NOT sufficient for a read-only *mount*.**
A WAL-mode store cannot be opened read-only on read-only media *at all* — even by a correct `mode=ro`
connection — because SQLite must write the `-shm` wal-index to read the WAL. The permission matrix is
unambiguous: in live WAL mode, *no* file-permission setting separates a fixed viewer from the broken
one (either both succeed on a writable dir, or both fail on a read-only dir). Serving the store
read-only therefore **also** requires checkpointing it out of WAL first (`wal_checkpoint(TRUNCATE)` +
`journal_mode=DELETE`, or a copy). `immutable=1` sidesteps the `-shm` write but is **unsafe against
the live runner** — it tells SQLite the file never changes, so concurrent runner writes become
invisible or corrupt the read — so it is not the right general answer. The read-only-mount test
encodes this precondition explicitly. *Implication for the fix: pair the `mode=ro` viewer change with
a documented "prepare store for read-only serving" step, or have the runner checkpoint-truncate after
each tick.*

**2. The existing `test_dashboard_app.py` smoke test passes only *because of* the N1 bug.**
Its seed writes raw events but never creates the `resolution_queue` working table; the broken
read-write dashboard creates it on the fly. A correctly read-only viewer can't — so the moment N1 is
fixed, that smoke test flips red with `no such table: resolution_queue` unless its seed is made
runner-faithful (construct a `ResolutionMachine` while the fixture store is still writable, the way a
real tick does). The one-line seed change is in `reference_fixes.diff`. *This is exactly the "a test
that passes for the wrong reason" hazard — worth a glance at whether other dashboard-adjacent tests
lean on the same accident.*

---

## `reference_fixes.diff` — reference patch (proof of satisfiability, not a prescription)

Minimal fixes applied only to **prove the tests can go green** and to make the two findings above
concrete. The implementation seat should treat these as one satisfying point in the design space, not
the required patch.

- **N3** — `_tidy` gains `drop_duplicates(subset=["date"], keep="last")` (append-only re-pull: latest
  row supersedes).
- **N1** — `Registry(..., readonly=True)` opens `file:{path}?mode=ro` (no WAL PRAGMA / DDL / commit);
  `runlog._ensure_table` and `ResolutionMachine.__init__` skip their DDL when `registry.readonly`;
  `app.py` opens `Registry(..., readonly=True)`. **Note:** `mode=ro` — *not* `mode=ro&immutable=1`
  (immutable is unsafe against the live runner and can't see fresh tables; see finding 1).
- **N2** — `register_launch` scans existing `launch.unverified` events for a matching
  `(ticker, detected_at)` and returns `"recorded"` (a no-op) if already present; `launch.scan` treats
  `"recorded"` as neither resolved nor queued. *This linear scan is O(n) in the launch history per
  candidate — fine at current cadence, but a production fix may want an index or a bounded lookback.*

## Regression gate

- Full existing suite **against the fixed tree**: **475 passed, 1 skipped, 0 failed** (includes the
  6 new tests and the one required `test_dashboard_app.py` seed update).
- Full existing suite **against the unfixed tree** (excluding the 3 new files): **469 passed** —
  confirms nothing in the reference patch regressed the baseline.
