# §9a sector-prices panel in the runner + the P1 guard; and the spawner-arc sequencing correction

*Decision record, 2026-07-06. Implements spec §9a (prices ingest wired into the runner) + closes review
finding P1 (`ingest/prices.py` Stooq adjusted-close). Also records the load-bearing **sequencing
correction** (Option A) that reordered the M5 spawner arc. Slice 1 of the arc: sector-prices →
xcorr-live → dashboard.*

## The sequencing correction (why this order, against the original plan)

The design thread's first framing was "wire one prices foundation, then dispersion-shadow (§9e) + xcorr
(§4a) on top of it." Exploring the actual slot state **overturned that premise**, and the owner ratified
the correction:

- **`PriceIngest` (§3) was already built** — `pull` (freeze-before-parse), `parse_yahoo` (reads
  `indicators.adjclose`), `parse_stooq`, `build_panel`, `warmup_days`, `required_pull_start`. So there was
  no "build the prices foundation" work — only *wire the existing ingest into the runner*.
- **The two spawners have OPPOSITE gaps.** `xcorr` (`sensors/xcorr.py`) is a pure-math pipeline + the
  Schmitt trigger with **no `scan` orchestrator** (only the backtest drives it), but its inputs are cheap —
  the 11-ETF sector panel from `config.universe`. `dispersion` (`sensors/dispersion.py`) *has* a full built
  `scan` (shadow gate, generous payload, `spawned_at`), but its inputs are a **holdings-derived vertical**:
  a per-basket `MembershipSnapshot` (holdings ingest is SPDR-only, runner wiring is a SLOT, only XLK has a
  fixture) **plus** a constituent price panel keyed by member **CUSIPs** (Yahoo/Stooq pull by *ticker*).
- **Therefore the "shared prices foundation" is a half-truth:** the sector-ETF panel feeds *xcorr*;
  dispersion needs a *different, holdings-derived* constituent panel. Dispersion cannot spawn a real shadow
  lead — so cannot start the §9e 90-day burn-in clock — until that whole vertical exists, **regardless of
  ordering**. The burn-in-clock argument that motivated "dispersion first" collapses: the clock is gated on
  the vertical, not on sequence.

**Corrected order (Option A):** §9a sector-prices panel (this slice) → **xcorr-live** (§4a, the M3-
acceptance-gated primary spawner: cheap inputs, only a `scan` to build) → **read-only dashboard** (§11, the
priority — real firings + a surface). Then the **dispersion + burn-in vertical** (§9e + holdings/
constituent prices), where **holdings-intake coverage** is finally confronted as its own slice, when its
consumer is built — not smuggled in early under "wire the clock." Email (§10) last.

## What was built (this slice)

`runner._build_sector_panel` (wired in the §9a ingest phase of `_run_sensors`, after mf-tickers, before the
sensor sub-order): pull each `config.universe` ticker (the 11 SPDRs + SPY) from the live primary source
(`prices.primary`, DEFAULT yahoo), **freeze-before-parse** via the built `PriceIngest.pull`, and assemble
the wide panel with `build_panel`. Reuses the existing ingest machinery entirely — no new ingest code. The
panel is a built-and-frozen artifact this slice (its consumer, `_run_xcorr`, lands next). `RunnerDeps` gains
a `price_ingest` field (a pre-wired dependency mirroring `edgar_client`; the CLI builds the httpx one, tests
inject a fixture fetch).

Granularity (§9g): the guard trip and each per-ticker fetch/parse failure (and an empty frame) are **soft
faults** — recorded on `_system`, the column skipped, the pass continues; never a run-abort.

## P1 — the Stooq adjusted-close hazard, closed structurally

The finding is real: `parse_stooq` reads the CSV `Close` and merely *asserted in a comment* it is adjusted;
`parse_yahoo` correctly reads `adjclose`. If Stooq's `Close` is *unadjusted*, every return across a
corporate action is wrong — and returns are the base of the whole sensor stack. But: Stooq's endpoint sits
behind a JS proof-of-work gate a polite client can't pass, Yahoo is primary, and sector ETFs effectively
never split — so **live risk today is ~zero**, and the right fix is **structural, not empirical-blocking**:

- **Fail-closed guard** (`prices.guard_live_source`, called by `_build_sector_panel`): refuse Stooq as a
  *live* source until `prices.stooq_adjusted_verified` (DEFAULT false) is set true. Yahoo (and any source
  not named) passes. Makes silently trusting an unadjusted close **impossible**, at zero cost today.
- **Comment honesty**: `parse_stooq`'s docstring is downgraded from "Close is adjusted" to "UNVERIFIED
  (P1) — assumed, never proven; gated by `guard_live_source` until a recorded-real split fixture proves it."
- **Empirical confirmation (flagged, out-of-band):** the actual NVDA-2024-10:1-split check compares Stooq
  `Close` vs Yahoo `adjclose` across the split and, on success, flips the flag + drops a recorded-real
  fixture. This needs **one out-of-band network pull** (the offline socket guard forbids it in tests) — low
  urgency because Stooq is gated. Not a blocker for this slice; do it when network is available, never wire
  fetch into a test.

## Boundary / bounds

- The runner pulls the sector panel every tick (12 tickers). Cadence-agnostic (M7 throttles). A same-day
  re-pull overwrites the dated frozen blob (ingest/ is dated substrate, not the append-only record).
- No auto-fallback to Stooq is built this slice: the runner pulls the primary; the guard governs whether a
  Stooq selection may ever go live. Keeping it thin.
- **Deferred:** the xcorr `scan` orchestrator + `_run_xcorr` (next slice); the whole dispersion holdings/
  constituent-price vertical + §9e burn-in clock (named next-after-dashboard).

## Tests

423 pass (was 416; +7). New: the panel is built + frozen under `prices_path` from an injected Yahoo fetch;
a per-ticker failure is a soft fault (others land, failed pull freezes nothing); the P1 guard fails-closed
when Stooq is forced live unverified (nothing pulled/frozen from it); + four `guard_live_source` unit tests
(yahoo allowed, unverified/absent-flag stooq refused, verified stooq allowed). Offline: every fetch is
injected; the socket guard fails any real connection.
