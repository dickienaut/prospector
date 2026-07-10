# §9e — constituent-symbol resolution: the design call on the foreign/cash/collision finding

*Decision record, 2026-07-10. Design-seat adjudication of Claude Science's QA finding
(`dispersion_foreign_ticker_findings.md`) against branch `claude/dispersion-vertical-9e`. Science laid out
the evidence and three handling options but explicitly left the choice to the design/impl seats; this record
**is that choice**, plus the acceptance gate and the widened primary-source gate. For the build seat (VSCode).
Evidence lives in Science's doc — this does not repeat it. Governing docs: the rev2 build note
(`2026-07-09-9e-dispersion-vertical-build-note-rev2.md`) and the §9e decision record
(`2026-07-09-dispersion-vertical-9e.md`).*

---

## 1. The finding (one line + severity)

`_run_dispersion` pulls each constituent's price series **by the SPDR file's Ticker column**, then re-keys
the panel to CUSIP — but the pull happens *after* trusting the ticker to be a valid, unique, US-listed Tiingo
symbol. Real SSGA files break that three ways inside the 0.90 cut (evidence: the recorded TEKX fixture):

- **`ENR` — the malignant case (HIGH).** `ENR` is Siemens Energy's *foreign* (EUR) local ticker in the file,
  but also a live US NYSE symbol for **Energizer** — a different company. A bare-ticker pull returns
  Energizer's real, populated series, relabeled with Siemens' CUSIP and fed to the matrix: a **silent,
  wrong** substrate (the P1 hazard at the constituent grain, invisible to `guard_live_source`, which vets the
  *source* not per-name resolution). *(Per Science: `ENR`=Siemens in the file is confirmed from the fixture;
  `ENR`=Energizer/NYSE is corroborated by web search, secondary — re-confirm at the gate. The test does not
  depend on live-verifying the pull.)*
- **`-` (cash/money-market) and `2670549D` (placeholder) — benign but coverage-overstating.** They 404 and
  drop as honest gaps, but `coverage_actual` (0.9149 on TEKX) is computed from holdings weights *before* the
  price-pull drops, so it **overstates** what was actually priced.
- **`member_map` is ticker-keyed** (`{ticker: identifier}`) — SSGA writes cash/derivative lines with ticker
  `-`; two `-` lines in one cut collapse to one dict key and silently drop a CUSIP. Wrong structure for a
  non-unique column.

**Scope nuance (decisive for urgency).** §9e's live universe is the 11 US sector SPDRs (S&P 500 sector
slices, US-domiciled by index rule); the finding is against TEKX (a global/thematic fund). The foreign-
collision hazard almost certainly does **not** fire on the live sector grid — so the 2026-07-10 XLI firing is
very likely clean (**verify**: confirm XLI's 0.90 cut carries no non-USD or `-`-ticker lines). The bug bites
the **deferred foreign/thematic scope** — and it is the exact silent-wrong-substrate class the project fixes
at the mechanism *now*. **Not an emergency that invalidates tonight; a hard must-fix before merge.**

This is *never-anchor-on-a-ticker* (HECO, §2) at the constituent grain — the third recurrence one level down.
The implementation **half-applied** the build note's own CUSIP-key discipline: the panel re-key to CUSIP is
correct, but the pull and `member_map` were left ticker-anchored. The key must be enforced **end-to-end**.

## 2. DECISION — the handling

**Option 1 + Option 2; defer Option 3.**

- **[FIX — Option 1] Exclude non-priceable lines at the membership boundary**, *before* `member_map` /
  the price pull. Drop (a) rows whose `Local Currency` ≠ USD (the foreign-listed lines — the `ENR` class), and
  (b) cash / derivative / placeholder rows (ticker `-` or blank, or a money-market / currency name). This is
  the "coverage gap, never a guess" move: the basket is priced on its US-listed core, the excluded weight is a
  *reported* gap, and nothing is silently wrong. Requires carrying `Local Currency` through `MEMBER_COLUMNS`
  (holdings.py) — additive. **Note the USD filter is a proxy** for "priceable by US ticker on Tiingo"; USD-
  denominated edge cases become named gaps, not guesses — acceptable.
- **[FIX — Option 2] Make the structure collision-safe.** Key the constituent structure on **CUSIP from the
  start** (carry ticker as a lookup attribute only), or detect a duplicate/blank ticker and **skip-with-a-fault**
  rather than dict-collapse. Even with Option 1 excluding the known `-` class, a non-unique ticker must never
  silently drop a CUSIP. This finishes the CUSIP-key discipline end-to-end.
- **[FIX — coverage honesty] Compute `coverage_actual` from the priced-and-correct set** (after exclusions and
  after any price-pull drop), not from pre-pull holdings weights, so excluded/dropped weight is a **reported
  gap**. This is not cosmetic: it makes the burn-in calibration trustworthy — you know what universe Q was
  computed on.
- **[DEFER — Option 3, named] Foreign CUSIP/SEDOL → US-symbol resolution.** The "complete" fix, but it needs a
  mapping source; anything third-party breaches the primary-source wall, and it serves the **not-yet-live**
  foreign scope. Exclusion + a reported gap is the honest default until a resolution slice earns it (the clean
  bridge would be a primary SSGA/EDGAR field exposing the US-listing symbol, if one exists).

Rationale: this makes the code correct for both scopes with near-zero impact on the live US sector grid
(all-USD → the filter drops at most a tiny cash line), while turning the foreign sleeve into an honest,
surfaced gap rather than a silent corruption — and it does not over-build resolution for a scope that isn't
live (the "does it close a gap on something LIVE" test).

## 3. Acceptance gate — tests ARE the gate (RED against branch, GREEN after fix)

Science's three, against the **real TEKX fixture** (no network), plus a fourth for coverage honesty:

- **`test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker`** — `ENR` (Siemens, EUR) is **not** in the
  set of symbols handed to the price pull. RED today. Fix-agnostic (satisfied by exclusion *or* resolution).
- **`test_cash_and_placeholder_lines_are_excluded_from_the_price_universe`** — the `-` money-market line and
  the `2670549D` placeholder are not treated as priceable equities. RED today.
- **`test_member_map_does_not_collapse_duplicate_tickers`** — a membership with two `-`-ticker cash lines in
  the cut loses no CUSIP (both survive keyed by CUSIP, or the collision faults). RED today.
- **`test_coverage_actual_reflects_the_priced_set`** — for a basket with excluded/dropped lines,
  `coverage_actual` reports the *honest* (lower) priced coverage, not the pre-pull weight sum. RED today.

Suite stays green (branch is 507/1 skip/1 xfail locally; 508 with `moto`) plus these four.

## 4. Primary-source gate — WIDENED

The rev2 gate named only the dual-class symbol mapping (`BRK.B`/`GOOG`/`FOX`). Widen it: before the live run,
confirm on the real XLF/XLC/XLY files that

- foreign-listed (non-USD) holdings are **excluded** (or, later, correctly resolved),
- cash / money-market / placeholder-ticker lines are **excluded** from the price universe, and
- specifically that a clean-looking-but-colliding symbol like **`ENR` does not silently return a US
  security's series** — the dual-class check alone would **not** catch this, because `ENR` needs no dot/dash
  transform; it is a valid-looking symbol pointing at the wrong company.

Also confirm the 2026-07-10 XLI firing was computed on clean US-equity constituents (no non-USD / `-` lines
in its 0.90 cut) — expected, but verify before treating that firing as sound.

## 5. Deferred / named

- Foreign CUSIP/SEDOL → US-symbol resolution (Option 3) — not-yet-live scope; needs a primary-source mapping.
- **Surfacing large per-basket coverage gaps** (the rev2 observability refinement) — now more load-bearing: a
  foreign-heavy basket will show a large priced-coverage gap, and that gap is itself a signal worth rendering.
