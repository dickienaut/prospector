# Launch sensor: capture first, corroborate next (the forced ordering)

**Status:** design-thread guidance, ratified 2026-07-03. Records why the launch sensor (spec §4c,
milestone 4) ships as **detection + two-phase recording first**, with the **corroboration hook +
holdings-derived concentration** as the *defined* next slice — and pins that next slice with a named
unblock so a headline v1 deliverable (the live cross-stream lag) cannot quietly become a permanent
"v-later." No CONTRACT changed; this is a sequencing + scope decision within milestone 4.

## The finding that forced the split

The corroboration hook — routing a resolved `launch` onto every live `xcorr`/`disp` lead whose
baskets overlap the launch, which is what yields the **live** cross-stream lag T(structural) →
T(launch) — keys on a launch's **concentration industries**. The live pipeline does not populate
them: `resolve_ticker` fills `concentration_industries: []` ("the prospectus parse is v-later"), and
`Resolution.name` is only the **trust** name (e.g. "SSGA Active Trust"), not the fund's theme. The
backtest's +593-day lag used the **curated** `historical_launches.yaml` (industries hand-filled),
**not** the live path. So the hook cannot honestly fire live yet — and a hook whose only green test
is a scenario that never occurs live is exactly the self-flattering metric this project refuses.

## Why capture-first is forced, not chosen

This is the **capture-now-interpret-later** pattern again — the shape that resolved the discourse
stream and the stress gate. The launch stream has a **cadence backbone** (the `launch.unverified` →
`launch` recording, `detected_at` preserved) and an **interpretation layer** (the corroboration hook
that consumes it). The ordering is **forced by an asymmetry**:

- **A launch timestamp cannot be backfilled.** If you were not watching when a fund launched, that
  datum is gone forever. The capture half must run **continuously from day one**.
- **Corroboration can be added later and applied retroactively** — thaw backward over the captured
  launch history once the interpretation layer exists.

So shipping detection + recording now is not "half a broken thing." It is the half that *must* run
continuously and *cannot be recovered* later; every launch it records live is one the deferred hook
will corroborate against when it lands. (Option 2 — build the consumer before its input exists — is
backwards; Option 3 — do both at once — is only worth it if the concentration signal is free, and it
is not.)

## The honesty rule for the next slice

**The concentration signal and the hook are ONE slice, built and jointly tested against live
behavior. The hook is never built without the live input it consumes.** What is deferred is not "the
hook alone" but "(concentration signal + hook), tested together, reflecting reality." This is the
guard against Option 2 and against a green-but-fictional hook test.

## The design for the next slice: concentration from holdings, not prose

Derive a launch's concentration **from its first holdings**, not by parsing prospectus prose:

- **Reuses existing machinery.** The holdings → sector logic is built by the rebalance/dispersion
  work in this same milestone (§4d holdings ingest), not a new prose parser.
- **Ground truth, not stated strategy.** Actual holdings, not face-value description — the project's
  standing "ETF look-through is truth" principle. **HECO is the proof** a fund's *stated* identity
  can be categorically wrong; the same reason the identity layer keys on the series id, not the blurb.
- **Simplifies the hook.** Holdings give the fund's actual sectors, so corroboration becomes a direct
  **sector-set overlap** with a live lead's baskets — not `keyword_match()` on industry strings
  against `sector_keywords` (that matcher was built for the hand-filled curated YAML and stays there,
  for the backtest).
- **Cost, and it is noise.** Holdings post days after launch, not at registration — a small
  post-launch delay on the industry tag. The lag being measured is months-to-years, so a few days is
  noise. `detected_at` (the launch datum) is still nailed at detection, untouched by this delay.
- **Honest fallback.** Semi-transparent active ETFs disclose holdings less directly; for those, fall
  back to the prospectus strategy text, or tag concentration **unresolved** and let the hook simply
  **not fire** (honestly) rather than guess.

## The dependency chain (each step reuses the last)

detection + recording *(this slice, done 2026-07-03)* → holdings ingest *(§4d, this milestone)* →
launch-concentration-from-holdings + corroboration hook *(the defined next slice)* → **live
cross-stream lag**.

## The guardrail (against a permanent "v-later")

The **(concentration + hook)** slice is the **defined next slice after the milestone-4 sensors**,
with a **named unblock: holdings-derived concentration working against live filings.** The live
cross-stream lag is the deterministic half of velocity-toward-consensus and a stated v1 deliverable;
it is allowed to come in the next slice, but it is **not** allowed to quietly disappear. When §4d's
holdings ingest lands, this slice is unblocked and scheduled — not reopened for debate.

## What shipped this slice (2026-07-03)

- `prospector/sensors/launch.py` — detection: `new_registrations()` diffs two frozen
  `company_tickers_mf.json` snapshots; `scan()` drives the per-day pass.
- `ResolutionMachine.register_launch()` (`prospector/identity/resolution.py`) — two-phase intake:
  `launch.unverified` (timestamp nailed) → resolve → immediate `launch` on `_system` (carrying the
  original `detected_at` + back-reference) or the retry-then-manual queue. `_complete` extended to
  take the datum explicitly on the immediate (no-queue-row) path.
- Tests: `tests/test_launch_sensor.py` (detection, immediate resolution, queued fallback, lag
  integrity, the cold-scan seed edge); `tests/test_resolution_failure.py` extended to drive its
  detection through the real `register_launch`.

**Not built (deferred to the defined next slice):** the corroboration hook, holdings-derived
concentration, standalone per-fund launch leads and their §8a active-lead-ceiling interaction (a
separate CONTRACT-adjacent question — a handful of new ETFs/day must not blow the ceiling), the
etfdb name skim, the raw 485 daily-index scan, and the live §9 cadence loop (milestone 5+).
