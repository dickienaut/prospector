# §4a xcorr wired LIVE into the runner — the primary lead-spawner

*Decision record, 2026-07-07. Implements spec §4a as the runner's live, paging, ceiling-counting lead-
spawner (the §4a SLOT in `_run_sensors`). Slice 2 of the spawner arc (sector-prices → **xcorr-live** →
dashboard), following the Option-A sequencing correction (`docs/decisions/2026-07-06-prices-ingest-and-
p1.md`).*

## What was missing, and what was built

`sensors/xcorr.py` was a **pure-math pipeline** (`daily_returns` → `rolling_beta` → `residuals` →
`pairwise_rolling_corr` → `fisher_z` → `departure_z`) + `stress_series` + the shared Schmitt trigger.
The only code that *orchestrated* those into per-day triggers and events lived in the **backtest** runner
(a full-history replay). There was **no per-tick driver** — so wiring xcorr live meant building one.

Built `xcorr.scan(panel, ticker_to_series_id, cfg, now, last_event_types, emit, tick_due=True)` — the
live analog of the backtest replay, mirroring `dispersion.scan`'s shape:
- drive the pipeline **once** over the panel + the stress series;
- per pair, reconstruct the Schmitt state from the record (§9f) and step **one** tick on the pair's
  latest z (the backtest walks history; the runner evaluates "now").

Wired `_run_xcorr` at the §4a slot (first in the §4a→§4d sub-order). A batch failure is a soft fault
(§9g) via the caller's boundary; no panel → `skipped` (xcorr can't run without a warmed grid).

## Load-bearing decisions

**Universe→series_id comes from the mf map, not the registry.** `xcorr_lead_id` keys on SEC series ids
(§2/§5 CONTRACT). The obvious source, `_lead_context` (the fund registry), is **empty in production**:
`upsert` fires only on a *resolved launch*, and the 11 SPDRs are the seed universe — never "launched,"
so never registered. Reading the registry would leave xcorr **permanently inert** (a wired-but-never-
fires spawner — the exact anti-pattern). Instead `_universe_series_ids` resolves the sector tickers from
**this tick's mf-tickers map** (the authoritative `[cik, seriesId, classId, symbol]` feed already fetched
for the launch diff). Network-free, authoritative, and it makes xcorr actually fire. A ticker that is
absent or ambiguous (>1 series id) is skipped — refuse to guess. **SPY is excluded by design**: it is a
UIT with no series id and is only the β-strip market factor, never a pair member (it drops out in
`residuals`).

**LIVE, never shadow.** A spawn carries `shadow=false`, so it pages and counts toward the §8a ceiling via
`active_nonshadow` — **no extra code**; the fold + that filter already do it. This is the opposite trust
level from the deferred dispersion (which will ship shadow/silent/clock-starting): xcorr is the M3-
acceptance-gated sensor (null test before calibration, falsifiers fired), trustworthy from day one.

**Stress gate (§4a CONTRACT).** On a day where the market-wide correlation LEVEL ≥ `crisis_level` (0.85),
the trigger is frozen: a would-be entry (quiet + z≥z_in) is recorded as an `xcorr.departure`
`market_stress=true` on `_system` (in the record + counts, never a spawn, never a phantom lead); an
already-active pair emits nothing. This mirrors the backtest exactly.

**§9f state from the fossil record.** `_xcorr_last_event_types` reads each xcorr lead's last trigger-
relevant event type straight from the registry (ORDER BY ts, event_id) — never a side cache — filtered to
the trigger vocabulary so a later corroboration/verdict can't be misread as an active departure. A pair
that never spawned is `None` → quiet, so it enters cleanly.

**One event vocabulary, two drivers.** The live scan emits the *same* events as the backtest —
`lead.spawned` (`spawner=xcorr`, `display`, `display_pair`, `shadow=false`) + `xcorr.departure` on entry,
`xcorr.tick` while active (silent — refreshes `latest_z`, no push), `xcorr.reverted` on exit — so the
fold, the CLI, and the coming dashboard treat backtest and live firings uniformly. No series ids in the
lead payload (the lead-id already encodes them — the §4d routing CONTRACT).

## Proven by the acceptance-gate discipline (the tests ARE the gate)

- **fires live end-to-end + pushes** (`test_runner_xcorr`): the mf map resolves a sector pair, a planted
  price panel departs, and one `run_tick` spawns a real `lead.spawned` (shadow=false) that folds active,
  counts in `active_nonshadow`, and pages (a live spawn is a state change — unlike a silent launch);
- **null-silent**: a panel with no shared factor spawns nothing;
- **stress gate freezes**: with `crisis_level` tripped, a would-be entry is a stressed departure on
  `_system`, not a spawn;
- **§9f state reconstruction**: an already-active pair does not re-spawn (it ticks); a reverted pair can
  re-enter — proving the state comes from the record, not a recompute;
- **soft-fault boundary**: a panel missing the market column faults the pass, not the run.

The proven M3 planted-departure fixture is reused, but with the shared factor held ON through the end and
the panel truncated to ~30 days past onset (near the z peak, before the trailing baseline adapts) — the
runner evaluates "now," not a full replay, so the latest row must be mid-departure.

## Bounds / still deferred

- **Coverage bound:** xcorr fires only for sector pairs the mf map resolves this tick; the mandate/soi
  routing that reads `_lead_context` (the registry) stays bounded until the universe is registered — a
  separate concern, unchanged here.
- **Cadence:** the runner is cadence-agnostic (M7 throttles); each tick records an `xcorr.tick` while a
  lead is active (silent, no push).
- **Deferred:** §4b dispersion + §9e burn-in clock (needs the holdings/constituent-price vertical);
  §4d rebalance (holdings-diff). The dashboard (§11) is next — it renders these live xcorr firings.

## Tests

430 pass (was 423; +7 — 4 `xcorr.scan` sensor tests + 3 runner-integration tests). Offline: every fetch
injected; the socket guard fails any real connection.
