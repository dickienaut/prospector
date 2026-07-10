# §9e — the dispersion + constituent-price vertical (the 2nd live spawner, in shadow)

*Decision record, 2026-07-09. Implements the design thread's **rev2 build note**
(`docs/2026-07-09-9e-dispersion-vertical-build-note-rev2.md`) against spec rev14 (§4b/§9/§8a). Wires the
already-built `sensors/dispersion.py` into the runner as its **second live spawner**, in **shadow** —
starting the 90-day burn-in. The slice is wiring + one data vertical + one identity bridge + closing one
latent CONTRACT collision; the sensor, the generous payload, the shadow fold mechanism, and the dashboard
shadow panel were already built (verified, not rebuilt).*

## What landed

- **`_run_dispersion` at the §4b slot** (`runner/runner.py`) — the runner's second live spawner. For each
  of the 11 SPDR baskets **resolvable this tick** (`_universe_series_ids` from the mf map — never the empty
  registry, the trap that would leave it permanently inert, the xcorr lesson): pull the basket's holdings
  this tick (freeze-before-parse), truncate to the weight-covering membership (0.90), pull constituent
  prices by ticker, re-key the panel to CUSIP identifiers, reconstruct Schmitt state from the record
  (`_dispersion_last_event_types`, §9f), and drive `dispersion.scan(..., tick_due=True)`. A spawn is
  `shadow=true` → it starts the burn-in clock and is excluded from the ceiling/corroboration/paging.
- **`HoldingsIngest` is now runner-wired** — a new `RunnerDeps.holdings_ingest` field, instantiated in
  `pros run`. The holdings feed (built but previously unconsumed) goes live here for the first time.
- **Cadence: daily.** `tick_due=True` mirrors xcorr's per-run tick (a `dispersion.tick` each run while
  active) — daily when the runner runs daily, the ~65 burn-in evaluations the build note wants.
  `dispersion.tick_cadence_days` stays advisory until M7 owns the real schedule.

## The two adjudicated findings (rev2), in mechanism

### A. The shadow-push CONTRACT collision — closed in the runner

A cold code-read found that shadow-exclusion-from-paging was enforced at the ceiling/corroboration/digest
(`active_nonshadow`) but **not at the push trigger**: `_compute_push` returned `bool(changed_leads) or
bool(faults)`, and a shadow spawn (`status: None→active`, `shadow: True`) is a real `state_changed` delta —
so a shadow spawn **would page**, violating §4b. Inert today (NullNotifier) but real. Dispersion is the
**first** shadow spawner (xcorr is non-shadow), so §9e is the first slice to make the collision live, and it
is resolved **here**, at the mechanism (not deferred to §10 — the sender is a dumb templater; the *decision*
that a shadow change is not page-worthy belongs to the runner):

- `_materialize_snapshots` now returns `(changed_leads, page_worthy)`: `changed_leads` records **every**
  change (the fossil/runlog stays whole), `page_worthy` is the subset whose lead is **non-shadow after the
  change**. `_compute_push(page_worthy, faults)`.
- **Push iff a changed lead is non-shadow after the change, or any fault.** Verified against the fold: a
  shadow spawn/tick/revert stays `shadow=True` (the fold leaves `shadow` untouched on `.reverted`) → not
  page-worthy; a future promotion (`shadow: true→false`) ends non-shadow → pages for free; every xcorr
  non-shadow path is unchanged. Regression-tested (a shadow-only tick → `pushed=False`; an xcorr+shadow
  tick → `pushed=True` because of xcorr, the xcorr `pushed=True` assertion preserved, never flipped).

### B. The ticker bridge — extend the SPDR parser (HECO, one level down)

Dispersion needs constituent **prices** (Tiingo is queried by ticker), but the panel keys on the stable
**CUSIP** and the SPDR parser dropped the file's Ticker column. Fix:

- `parse_spdr_holdings` now keeps the file's own Ticker column (`ticker` added to `MEMBER_COLUMNS`,
  additive, guarded like `identifier`/`sector`). Ticker is a **display-only lookup attribute**; the panel
  keys on the CUSIP (the constituent-level echo of *never anchor on a ticker*, §2 HECO). The ticker↔CUSIP
  map thus comes from the SPDR **primary file itself** — no third-party symbol feed (which would breach the
  primary-source wall).
- `_build_constituent_panel` pulls each constituent by ticker, then **re-keys the tidy `ticker` column to
  the CUSIP *before* `build_panel`**, so both the columns and `attrs['sources']` come out identifier-keyed
  (a post-hoc `.rename()` would leave `attrs['sources']` ticker-keyed → a silent source-lookup miss). The
  frozen price fossil stays keyed by the real Tiingo symbol (freeze happens inside `pull`, before the re-key).

## Two things the build note did not anticipate (found while building)

- **[BUG, caught by the P1-guard test] The constituent pull bypassed the P1 fail-closed guard.** The sector
  panel refuses an unverified adjusted-close source (`guard_live_source`); `_run_dispersion`'s constituent
  pull did not — so an unverified Stooq would have frozen constituent bodies and corrupted every constituent
  return (exactly the P1 hazard, one level down). Fixed: `_run_dispersion` runs `guard_live_source` before
  the basket loop and skips the whole pass (loud) if it trips. The existing
  `test_p1_guard_fails_closed_on_unverified_stooq_live_source` caught it.
- **Soft-fault granularity split (a principled reading of rev2 §5).** A basket whose **holdings feed
  fetch/parse fails** is a per-basket **fault** (a broken feed for an expected basket must surface, §9g); a
  basket with **no priceable constituents** (or a partial price gap) is a **skip** (a coverage gap, honest,
  never a guess — and per-constituent price failures are dropped, not an 8-names-404 fault storm). The
  acceptance suite proves the boundary via a holdings-fetch failure (unambiguous fault) while a healthy
  basket still spawns.

## Config / defaults

`dispersion.paging: false` (shadow until a human `config.changed` flip; never auto-promoted) ·
`weight_coverage: 0.90` · `shadow_days: 90` · z_in 2.5 / z_out 1.0 · `_dispersion_pull_start` sizes the
constituent-price window to dispersion's **own** `baseline_days(252)+window_days(63)` × the 1.5 calendar
buffer — never `cfg['windows']` (xcorr's 567-day chain). No config value changed; no free-tier workaround
existed to delete (Tiingo Power is uncapped — the build note's "delete the workaround" was a no-op).

## PRIMARY-SOURCE GATE (required before the live run — NOT covered by the suite)

`_tiingo_symbol` normalizes SPDR dot-form class tickers to Tiingo dash-form (`BRK.B`→`BRK-B`) at the
constituent-pull seam (never the shared URL builder). The synthetic fixtures have **no class shares**, so a
green suite does **not** verify this mapping. **Before the live `pros run`:** pull the real XLF/XLC/XLY SSGA
files and confirm the mapping handles `BRK.B`, `GOOG`/`GOOGL`, `FOX`/`FOXA`. Record any transform extension
here — never fit silently. This is the one genuine primary-source unknown in the slice.

## Deferred / named (not built here)

skip-if-frozen-today dedup (no live gap on Power) · broader per-issuer/NPORT-P coverage (rate-widening,
state rev5) · dispersion PIT backtest 3b (data-gated) · §10 sender (next slice — owns digest *rendering* of
shadow, and closes the paid-sub lapse-risk dead-man) · `tick_cadence_days` enforcement + `hourly_cap` flip
(M7) · surfacing large per-basket coverage gaps (a future observability refinement).

## Verification

Full suite **508 passed / 1 xfailed** (was 500 + 8 new: 7 runner-dispersion acceptance/violation tests +
the holdings ticker-extraction unit). The acceptance test fires on **real holdings-derived** membership (the
XLK fixture through the real parse→membership path) + a genuinely-departing constituent panel (z≈3.1, over
the real z_in=2.5) → a real shadow `lead.spawned` that folds active-shadow, is excluded from
`active_nonshadow`/ceiling, sets `pushed=False`, starts the burn-in clock, and carries the generous payload.
**"Done" for this slice = fires on real seed data + burn-in started + suite green — NOT "validated"** (the
burn-in is a calibration window, not falsification). The live `pros run` on real SPDR data + the
symbol-mapping gate are a **desktop + cold-Science-QA** step (rev2 §7), pending.
