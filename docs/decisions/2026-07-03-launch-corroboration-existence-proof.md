# Launch corroboration: the live lag is an existence proof, not yet a rate

**Status:** design-thread guidance, ratified 2026-07-03 (the pre-green review); built as the launch
corroboration hook (`prospector/sensors/launch_corroboration.py`), the milestone-4 capstone. This is
the slice where "detect emerging structural shifts early" first becomes a *number*, so it carries the
honest-test boundary and its live-lag test was reviewed by the design thread **before green**. Records
the mechanism, the boundary, and — the load-bearing part — the coverage limitation at full strength.
Folds into the next spec rev.

## What it does

When a resolved launch's **holdings-derived sectors** overlap a live lead's baskets, the `launch`
accretes onto that lead (a silent corroboration — it NEVER spawns a lead, rev7: no ceiling slot), and
the **cross-stream lag** T(structural departure) → T(launch) becomes measurable there. No overlap →
recorded dormant on `_system`. `holdings_unavailable` → dormant. Reuses the §4d forward-hash routing
and `launch_lag` (reads only `detected_at`).

## The honest-test boundary (the review gate) — how it was closed

The backtest's +593 came from a **curated** launch table (concentration hand-filled) matched with
`keyword_match` on industry strings — a green that never occurs live. That path stays in the backtest
and never crosses into the live hook, which derives concentration from **first holdings** (ground
truth) and does a **direct sector-set overlap**. Two conditions, both met:

- **Both endpoints real.** T1 is a real structural `lead.spawned`; T2 is a real `launch` whose sectors
  are *derived* from real holdings, not supplied.
- **The split assertion (design-thread sign-off condition).** The test proves the sectors are
  *correct*, not merely *derived*, in an assertion **separate** from the lag — `sector_concentration`
  on a real messy SPDR-format fixture yields the expected `{Information Technology, Utilities,
  Industrials}` (Assertion A), and the hook computes **+593 days** from the two timestamps
  (Assertion B). Because the lag value is independent of the sectors and the sectors are checked on
  their own, a mapping bug and a hook bug cannot cancel into a flattering +593. The fixture carries no
  `concentration_industries`.

## The lag is signed — negative is data

`cross_stream_lag` records T2 − T1 honestly. Negative (a launch detected *before* the delayed
structural spawn — **packaging beat structure**, the un-recalibrated-gate −58 category) is a real
outcome, **never clamped to positive or discarded**. `None` when there is no structural spawn or no
corroborating launch (undefined, not fabricated). Record the true value; let the human read it.

## Timing — corroboration is DEFERRED, never fired at launch time

A fund's first holdings post **days after** it lists, but `detected_at` is nailed at detection. Wiring
corroboration into launch resolution would find the empty sector set and **silently never fire** (the
`concentration_industries: []` trap, one layer down — the launch-side twin of the mandate sensor's
frozen-prior invariant). So `corroborate` is a **deferred, re-attempted pass**: the launch is recorded
dormant at detection (built); when its first holdings land the pass runs and **reaches back**,
preserving the original `detected_at` as T2. It is *called with* holdings; it never assumes they
exist. The §9 runner (M5+) owns the retry-until-holdings-land scheduling.

## THE FINDING, at full strength — the live lag is bounded by holdings coverage, not the hook

This is the thing to hold onto, discovered by building: **the binding constraint on the live
cross-stream lag is holdings coverage, not the corroboration logic.** `ingest/holdings.py` parses
**SPDR CSVs only**, so:

> **For any launch outside the SPDR family, the cross-stream lag is *structurally unmeasurable*, not
> merely absent.** When the lag fires, it fires on the coverage-biased subset the tool can see
> through. TEKX being SPDR/SSGA is the exception, not the rule.

So the honest framing of the v1 live lag — never let "+593 reachable" quietly overwrite it — is: **the
mechanism is proven and produces a real, derived lag on covered issuers; coverage is currently one
issuer family; the measured lag is therefore an EXISTENCE PROOF, not yet a rate.** Same discipline as
"recall confirmed on n=1" and "precision structurally unmeasurable": the mechanism works, the sample is
thin, say both.

The `holdings_unavailable → dormant` outcome is therefore **the majority case today, and first-class** —
a real disposition surfaced for deliberate survey (like a non-corroborating launch), never an edge to
paper over and never a guess. It is the launch-side twin of `fault`-on-unreliable-extraction: flag the
blind spot, never fake through it. **The dormant pile is the map of what the tool can't yet see.**

## The named next slice (the payoff of building narrow)

Building narrow hands the next slice its definition for free: **holdings-intake coverage is the named
unblock for a *representative* live lag** — per-issuer holdings parsers, or the NPORT-P look-through
path (the §3b surface already deferred). The sequence: prove the hook now against SPDR (this slice);
widen intake as its own defined work; the lag then goes from existence-proof to measurable-rate as
coverage grows. **Intake was deliberately NOT widened inside this slice.**

## What shipped
`prospector/sensors/launch_corroboration.py` — `sector_concentration` (Piece 1: holdings→sectors),
`series_id_sectors`, `lead_sectors` (forward-hash), `overlaps` (both-sides), `corroborate` (the
deferred pass), `cross_stream_lag` (signed). Config: `sector_map` (SPDR→GICS) + `corroboration.
sector_min_weight`. Tests: `tests/test_launch_corroboration.py` (12, offline) with a realistic messy
SPDR-format `TEKX_2024-09-10.csv` fixture; the split assertion, the signed lag, both-sides,
off-thesis-dormant, and the holdings-unavailable majority case. **Not built:** non-SPDR/NPORT holdings
intake (the coverage frontier — the named next slice); the live §9 runner (this ships as a deferred
driver + pure functions, tested offline). The backtest `keyword_match` + curated YAML never enter the
live path.
