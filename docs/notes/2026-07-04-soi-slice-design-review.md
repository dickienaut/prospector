# Design-thread review — SOI sector-concentration slice

**For:** Claude Code (build thread).
**Re:** `claude/soi-sector-concentration-cd48yp` (commits 5adf125 + b1e4d7f, 359 tests green).
**From:** design thread, 2026-07-04.

## Verdict

**Merge-worthy, with one required change before the reader is trusted past the current fixtures.**

The mechanism is the spec: SOI as the resolver of `sectors_unresolved`, industry headers rolled
through the frozen GICS table, reconciled to the COMMON STOCKS total, routed through the shared
`route_corroboration` so holdings and SOI feed one overlap/accrete/lag path with `detected_at`
preserved as T2. No ticker classifier, no third-party feed. The +593 now attaches on real
primary-source sectors (Jul-2025 TEKX clears XLK×XLU) instead of the synthetic fixture — the genuine
completion of the existence proof, still honestly **n=1** (one issuer, one clearing snapshot), not a
rate.

## Required before trust-past-fixtures: verify the rollup table + add a structural test

**The reconcile check protects parsing, but not the rollup.** Reconciling the industry percentages to
the COMMON STOCKS total is what caught the dropped mixed-case `SPECIALIZED REITs` (96.4% vs 99.2%) — it
earns its keep, exactly as intended. But that sum is **invariant to which sector bucket each industry
rolls into.** A *mis-mapped* industry — e.g. `PHARMACEUTICALS` assigned to Information Technology
instead of Health Care — reconciles cleanly and produces a wrong sector set **silently.** The only
thing catching a rollup error today is the goldens' asserted sets, which exercise the ~15–20 industries
present in TEKX and DECO; the other ~54 rows of the 74-industry table are on the builder's say-so — a
table assembled from memory, unverified against the primary source. That is the same convergent-prior
surface this project has hit repeatedly (the CSV-not-xlsx and blank-sector priors): a value trusted
because both instances share it, not because it was checked against ground truth.

**Do two things:**

1. **Verify all 74 industry→sector assignments against primary-source GICS structure** — the 74
   industries as they sit under the 11 sectors / 25 industry groups. Do **not** take the design
   thread's recall of any specific mapping as the check; that recall is exactly the unverified prior.
   Check the table against GICS itself.
2. **Add a structural test:** every value in the rollup table is one of the 11 canonical GICS sector
   strings — `{Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials,
   Health Care, Industrials, Information Technology, Materials, Real Estate, Utilities}` — and every
   industry key maps to exactly one. This catches a typo'd or non-canonical sector string (which would
   silently fail an overlap match) and pins the table's shape.

**Severity is graceful, so this is not a hard blocker.** A rollup error produces a spurious accrete or
dormant — i.e. **over-firing**, the failure mode the whole system is built to tolerate and hand to the
human, never a silent miss of something real. So it is cheap, not urgent — but it *is* the one
currently unguarded surface, so close it in this PR or the immediate next commit rather than let it
drift into the runner.

## The four-sector correction (Jul-2025 Financials 10.1%)

The design-thread spec asserted `{Information Technology, Utilities, Industrials}` for Jul-2025. **That
was wrong** — `CAPITAL MARKETS 4.7% + FINANCIAL SERVICES 5.4% = Financials 10.1%`, over the 0.10 floor.
The spec said assert the *derived* set with no pre-filled expectation, so the golden correctly records
the filing's **four-sector** truth over the spec's three-sector guess — the discipline catching the
spec author's error is the point of it, working. Two things follow, neither affecting the +593 or the
XLK×XLU match:

- **Multi-lead input.** Financials clearing means real TEKX would also accrete onto any live lead whose
  baskets include Financials (an XLK×XLF pair), not just XLK×XLU. The four-sector set is the correct
  input for multi-lead corroboration; the golden asserting the full set is right.
- **A second knife-edge.** Utilities 10.7% and Financials 10.1% both sit just over the 0.10 floor at
  Jul-2025. Two sectors on the line is one more reason the threshold stays **frozen** and the as-of
  derivation stays honest — do not tune `sector_min_weight` around either.

(The four-sector result is at least *consistent* with a current-GICS table — the payment networks read
as Financials, where the 2023 GICS revision placed them — but per the point above, don't treat that
consistency as the verification. The 74-row table review is the verification.)

## Affirmed correct — do not touch

- **DECO positive control.** Targeting a *different* fund and getting *its* numbers is the right way to
  prove fund-block isolation — a positive control, not an absence assertion.
- **ALLW fault.** Faulting rather than inventing sectors for a bonds-and-futures fund is
  fault-on-unreliable-extraction holding one level out. Correct.
- **Fetch deferral.** The reader is tested against hand-frozen recorded-real fixtures; live
  EDGAR-SOI-fetch is deferred to M5, named and tied to `EdgarClient`. The `www.sec.gov` egress block
  confirms fetch couldn't have been exercised in-session regardless, so the deferral was forced as well
  as right. Drop-and-freeze for tests, fetch-on-cadence for the runner — never conflated, fixtures
  never refreshed by fetch.

## Decision

Fold the rollup-table verification + structural test into this PR before merge, or merge now and make
it the immediate next commit. Either is defensible. The change is **required** before the reader is
trusted on any filing whose industries aren't already in the goldens — which is every filing the runner
will eventually fetch.
