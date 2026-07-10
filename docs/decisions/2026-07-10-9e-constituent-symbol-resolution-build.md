# §9e constituent-symbol resolution — build record (what was implemented, what was verified)

*Implementation record, 2026-07-10. Claude Code (implementation seat) building the design-seat
adjudication (`2026-07-10-9e-constituent-symbol-resolution.md`) of Claude Science's QA finding
(`../dispersion_foreign_ticker_findings.md`) on branch `claude/dispersion-vertical-9e` (PR #24). This
records **what landed and what was verified vs. deferred** — the decision and the evidence live in those
two docs; this does not repeat them. Governing spec: §4b/§9e; the CONTRACT is the identity-key discipline
(HECO, §2/§5) enforced **end-to-end**, not just at the panel.*

---

## 1. What this closes (one line)

`_run_dispersion` pulled each constituent's price **by the SPDR Ticker column**, trusting it to be a valid,
unique, US-listed symbol. The recorded-real TEKX file breaks that inside the 0.90 cut (`ENR`→Siemens/EUR
collides with NYSE:Energizer → silent wrong series; `-` money-market and `2670549D` placeholder → 404-drop
→ overstated coverage). The fix filters the un-priceable lines **at the membership boundary, before the
pull**, keys the pull on CUSIP, and reports **honest** coverage. Decision: Option 1 + Option 2, defer
Option 3.

## 2. What landed (the diff, by intent)

**`prospector/ingest/holdings.py`**
- `MEMBER_COLUMNS` now carries `local_currency` — the SSGA file's own `Local Currency` column, the
  **primary-source** signal for a foreign listing (no third-party symbol feed → no wall breach).
  `parse_spdr_holdings` reads it (via the existing `col.get(...)` pattern); `weight_covering_members`
  carries it through (via `row.get(..., "")`, so frames without the column — CSV/synthetic — still work).
- **`priceable_members(members)`** — drops, as a *reported coverage gap*: (a) non-USD `Local Currency`
  lines (the `ENR` collision class); (b) a `MONEY MARKET` name (defense-in-depth); (c) any ticker that is
  not a plausible US equity symbol (`_US_EQUITY_TICKER_RE = ^[A-Z]{1,5}([.\-][A-Z]{1,4})?$`) — which
  excludes `-`/blank (SSGA's cash sentinel) and placeholder codes carrying a digit (`2670549D`).
- **`priced_coverage(priceable, priced_ids, total_weight)`** — `coverage_actual` computed over the set
  that **actually priced**, against total basket weight.

**`prospector/runner/runner.py`**
- `_build_constituent_panel` now takes an ordered iterable of **`(ticker, identifier)` pairs**, not a
  `{ticker: identifier}` dict (Option 2: a dict collapses two non-unique `-` tickers into one key,
  silently dropping a CUSIP; a list preserves every CUSIP, and `build_panel` already FAULTS on a duplicate
  CUSIP rather than fabricate).
- `_run_dispersion`: `priceable = priceable_members(members)` before the pull; the panel is built from the
  priceable pairs; `coverage_actual = priced_coverage(priceable, set(panel.columns), total_weight)`; the
  `MembershipSnapshot` carries `members=priceable` (the intended price universe — the generous payload
  reads name/weight from it by the panel's CUSIP columns, so a 404-dropped name simply does not appear).

## 3. The tests ARE the deliverable (RED-first, for the *right reason*)

`tests/test_dispersion_foreign_and_cash_tickers.py` — four acceptance tests against the **real TEKX
fixture**, offline. The design thread's non-negotiable: watch them fail on the **un-fixed** branch **for
the stated behavioral reason**, not a trivial ImportError. So the pull-set and coverage tests are
**behavioral** — they drive the real `_run_dispersion` (the fix lives in its filtering step, the only place
the violation is observable) with a stub `price_ingest` that records requested symbols, and a hand-built mf
map (no EDGAR). Confirmed RED against the branch before the fix:

- `test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker` — RED: `'ENR' in ['RIOT','ENR','CIFR',…]`.
- `test_cash_and_placeholder_lines_are_excluded_from_the_price_universe` — RED: `'-'`/`'2670549D'` requested.
- `test_coverage_actual_reflects_the_priced_set` (monkeypatches `dispersion.scan` to capture the
  `MembershipSnapshot`, since coverage isn't emitted) — RED: `coverage_actual == 0.9149` (overstated).
- `test_member_map_does_not_collapse_duplicate_tickers` — the one **structural** test (a dict collapse is
  not behaviorally observable: both `-` lines 404 either way). RED-by-construction; guards the Option-2
  invariant. `build_panel`'s duplicate-CUSIP fault is the further backstop.

**Provenance discipline (Science's, preserved):** the tests assert the membership-boundary behavior (that
`ENR` is never handed to the bare-symbol pull) — **not** the secondary, web-sourced claim that
`ENR`=Energizer. The finding is fix-agnostic and needs no live verification; the malignant case is exactly
why exclusion (not "let it 404") is the honest default — a colliding foreign ticker does not 404.

## 4. What was verified (evidence, on real data)

- Real TEKX 0.90 cut = 25 constituents; **22 kept, 3 excluded** (`ENR`/EUR 6.17%, `-` money-market 4.22%,
  `2670549D` placeholder 1.62%). `coverage_actual` **0.9149 → 0.7953** (honest priced fraction).
- Full suite: **512 passed / 1 xfailed** (508 pre-existing with `moto` + 4 new). No regressions in the
  touched areas (holdings, real-TEKX, runner-dispersion, dispersion-sensor, launch-corroboration).
- Firewall untouched (no portfolio read, no trade path); the read-only wall grep stays clean.

## 5. Implementation decisions worth recording (not in the adjudication)

- **Blank currency is NOT foreign.** The USD filter fires only on an *explicit* non-USD value; a
  blank/absent `Local Currency` (CSV / synthetic fixtures) falls back to the ticker-shape gate. This keeps
  the clean XLK fixture (no currency column, all US tickers) → all 8 kept → existing tests unaffected.
- **No broad cash/currency *name* blocklist.** Deliberately not added — false-positive-prone (a real
  operating company could match). SSGA marks cash with the `-` ticker, which the shape gate already
  excludes; the `MONEY MARKET` check is narrow defense-in-depth (a ~flat NAV would inject a zero-variance
  column) and safe (no operating company is named that).
- **Coverage is computed, NOT surfaced.** `coverage_actual` is not added to the `dispersion.tick` payload —
  **surfacing large per-basket coverage gaps is the deferred §5 observability refinement**. Nothing is lost
  by waiting: `coverage_actual` is a deterministic function of the frozen holdings + price fossils, so it is
  reconstructible; a payload-schema change is a CONTRACT touch and out of scope for this fix.
- **Structural correctness, no config knob.** Priceability is not a tunable threshold (and thresholds are
  never auto-tuned) — it is hardcoded like the weight-sum band, not a `config/prospector.yaml` DEFAULT.

## 6. Deferred / human-owned (flagged, not faked)

- **Widened primary-source gate (desktop; needs real SSGA files CI can't reach).** Before the live run,
  confirm on real XLF/XLC/XLY that dual-class (BRK.B / GOOG·GOOGL / FOX·FOXA) **and** foreign/cash lines are
  handled, and that a clean-looking colliding symbol like `ENR` does not silently return a US series (the
  dual-class dot/dash check would NOT catch it — a different failure mode). Also confirm the live **XLI**
  firing is computed on clean US-equity constituents (expected: the 11 sector SPDRs are US-domiciled by
  index rule, so the collision almost certainly does not fire on the live grid — but verify).
- **Option 3 — foreign CUSIP/SEDOL → US-symbol resolution.** The "complete" fix; needs a primary-source
  mapping and serves the not-yet-live foreign/thematic scope. Exclusion-with-a-reported-gap is the honest
  default until a resolution slice earns it.
- **Surfacing large coverage gaps** (§5) — now more load-bearing (a foreign-heavy basket shows a large
  priced-coverage gap that is itself a signal worth rendering).

## 7. The lesson (carried into the code comments)

The implementation had **half-applied** the build note's CUSIP-key discipline: the panel re-key to CUSIP
was correct, but the pull and the `member_map` were left ticker-anchored. The identity key must be enforced
**end-to-end**, not just at the panel — this is *never-anchor-on-a-ticker* (HECO, §2/§5) recurring one level
down, at the constituent grain, for the third time in the project. Primary-source verification (reading the
real TEKX file) is what broke the shared wrong prior — the rev2 gate anticipated dual-class and stopped
there; only the file surfaced `ENR`.
