# SOI-derived sector concentration — the EDGAR filing carries GICS industry groups; no ticker classifier needed

**Status:** design-thread spec, 2026-07-04. Supersedes the "named next slice" of
`docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`. Written to be built cold by
Claude Code; **reconcile the function names below against the live code** (this spec was written from
the decision notes + CLAUDE.md, not the source tree). Folds into the next spec rev after build.

## The correction (what opening the real filing changed)

The xlsx-and-blank-sectors note concluded the unblock for real-fund sectors was **"an external
ticker→GICS-sector classifier"** — map each daily-holding CUSIP/ticker to a GICS sector from a source
other than the daily file. **That is unnecessary, and it was a convergent-prior error.** The primary
source already publishes the sector grouping: the fund's periodic EDGAR filing renders a **GICS-
industry-grouped Schedule of Investments** — each holding listed under an industry header carrying that
industry's percent of net assets (e.g. `ELECTRICAL EQUIPMENT — 17.6%`, `SOFTWARE — 38.7%`,
`ELECTRIC UTILITIES — 6.4%`). Sector concentration therefore comes **directly** from parsing those
industry headers and rolling **industry → sector** through a fixed table (GICS is 11 sectors / 25
industry groups / 74 industries / 163 sub-industries; the industry→sector rollup is 74→11 and does not
drift). No per-ticker mapping, no security master, no third-party feed. The note reached for a
classifier because it reasoned from "the daily xlsx has no sectors, so I must add sectors to each
ticker" — but the filing already groups by sector. Third convergent blind spot broken by primary-
source contact (the first two: CSV-not-xlsx, and the inflationary register).

## The empirical result on real data (the motivating finding)

Three primary-source snapshots for **TEKX** (State Street Galaxy Transformative Tech Accelerators ETF,
CIK 1516212), rolled up to GICS sectors. Utilities is the swing leg, hovering at the floor:

| As-of | IT | Industrials | Utilities | both-sides vs XLK×XLU (floor 0.10) |
|---|---|---|---|---|
| 2025-07-31 (report SOI) | ~52% | ~13.9% | **10.7%** (Electric 5.3 + IPP 2.4 + Multi-Util 3.0) | **fires** — IT and Utilities both clear |
| 2026-01-31 (this filing) | ~51.9% | ~22.1% | **6.4%** (Electric only) | dormant — Utilities below floor |
| ~current daily book | ~52% | — | **~8%** | dormant — Utilities below floor |

So on real data, TEKX corroborates XLK×XLU in **exactly one snapshot (Jul 2025)** and is dormant before
and after. The signed cross-stream lag (**+593 days**, computed to `detected_at` = 2024-09-09 from the
structural spawn 2023-01-25) **attaches at that Jul-2025 resolution** — a real-data derivation, not the
synthetic fixture's. The v1 live lag is now an **existence proof on real primary-source data**, n=1
snapshot; still not a rate (one issuer, one clearing window), but no longer synthetic-only.

**Anti-fitting (CONTRACT — the sharpest case yet).** The answer turns entirely on whether Utilities
reads 10.7% or 6.4%. Nudging `corroboration.sector_min_weight` down to make the Jan-2026/current book
also fire would be fitting-to-the-known-case in its purest form. The threshold is **frozen** (§4a/§8a);
the derivation reports the marginal Utilities honestly and lets the as-of truth stand — including the
dormant snapshots. The golden test records outcomes; it never chases the pretty one.

## Mechanism (what to build — parse the SOI directly)

- **Source (primary-source, no third party):** the fund's periodic EDGAR filings that render a GICS-
  industry-grouped SOI. The semi-annual/annual **N-CSR/N-CSRS** reliably carries it for every
  registered fund; this trust also files roughly **quarterly** SOIs (Jan-31 / Apr-30 / Jul-31 / Oct-31
  boundaries observed). Fetch and freeze per accession under the existing `ingest/` blob store, same
  discipline as `ingest/prospectus/` (freeze raw, extract on read). **Parse the HTML**, not a PDF
  rendering — the PDF is two-column and continuation-paged and will fight you.
- **Parse:** extract industry-header lines matching the pattern `INDUSTRY NAME — N.N%` within the
  target fund's section (bounded by the fund title and its `TOTAL INVESTMENTS`). Roll each industry to
  its GICS sector via the frozen table (below), summing to `{sector: weight}` with the filing's as-of
  date. Emit a **`fault`** (manual review) when extraction is unreliable — header pattern not found,
  section boundaries ambiguous, rolled weights don't reconcile to the `COMMON STOCKS — N%` total within
  tolerance — **never a wrong sector set**. Same "extraction-unreliable → fault, never a false claim"
  discipline as the mandate-diff sensor (§4d); same parser/meaning/significance boundary (bs4 owns
  structure, our code owns which-industry-and-rollup, the human owns significance).
- **Feed the existing contract:** produce the same `{sector: weight}` shape `sector_concentration`
  already returns, then hand it to the built `overlaps` / `corroborate` / `cross_stream_lag` path
  unchanged. `corroboration.sector_min_weight` is **unchanged and frozen**.

## Fit with what's built (this resolves `sectors_unresolved`, it doesn't replace it)

- The `sectors_unresolved → dormant` disposition Claude Code just built stays **correct for the pre-
  first-SOI window** — a fund's first industry-grouped SOI lands weeks-to-months after launch, so
  between launch detection and that first filing there is genuinely no sector source, and dormant-with-
  a-flag is the honest state. The SOI path is the **resolver** of that state: when the first post-launch
  SOI lands, the deferred pass re-runs, derives sectors, and **reaches back with `detected_at`
  preserved as T2** — the same deferral the corroboration hook already implements. The lag measures to
  `detected_at`, so deriving sectors from a later SOI does not corrupt it.
- The **daily xlsx stays the membership/weight source for dispersion and rebalance** (its real jobs) —
  it is simply **not** the sector source for corroboration. Do not try to make it one.

## Boundaries (CONTRACT)

- **GICS is right for the overlap, wrong for the thesis (HECO, one level down).** GICS shreds TEKX's
  actual compute×power thesis across sectors: power lands in **Utilities** (NRG, Vistra, PSEG),
  **Industrials** (Vertiv, Hubbell, nVent — Electrical Equipment), and **Energy** (Exxon); the bitcoin
  miners that are ~39% "Software" (Core Scientific, Riot, Cipher, Cleanspark, Bitfarms) land in **IT**.
  For the *mechanical overlap with sector SPDRs*, GICS-to-GICS is correct and consistent — XLK and XLU
  are themselves GICS-sector funds. But never read the fund's thesis off its GICS top line (that is the
  HECO error), and note the IT leg fires partly because GICS files miners as software (a taxonomy
  coincidence, weak thesis meaning); the Utilities leg is the genuinely meaningful one (those names are
  actually in XLU).
- **Frozen threshold.** `sector_min_weight` does not move to rescue a dormant snapshot. Ever.
- **The industry→sector rollup table is frozen reference data, not a tunable.** Source it from GICS
  (MSCI / S&P Dow Jones), version it, and re-freeze only on a GICS structure revision (the Mar-2023
  reclassification is the precedent) with a `config.changed` fossil. It is deterministic; it is not a
  sensor knob.
- **No third-party sector feed.** The classifier the prior note named is not just unnecessary — a
  bought sector feed would breach the primary-source wall the repo has held throughout. If a
  constituent's sector is ever genuinely needed at ticker level (it is not, for this slice), it is
  *derivable from the SOI corpus itself* (each SOI lists the security under its industry) — never from
  an external vendor.

## Pre-build verification — resolved, with one small open item

- **Resolved:** the report SOI carries the GICS-industry grouping (this Jan-2026 filing for TEKX
  demonstrates it, and the Jul-2025 quarterly independently). The structured **N-PORT XML** does *not*
  carry GICS — its per-holding fields are asset-class / issuer-type codes — so the grouped SOI in the
  report is the sector-bearing artifact, exactly as assumed. (My understanding of the N-PORT schema;
  the SOI availability is confirmed by the file in hand.)
- **One small open item, do first:** pin which EDGAR **form-types** reliably render the grouped SOI
  against the fund's filing index (N-CSR/N-CSRS certainly; confirm whether the NPORT-labeled filing
  that carried this SOI is a dependable recurring source or a one-off rendering). This bounds the
  fetch cadence; it does not change the mechanism.

## What's built / named next

- **Built (prior slice):** xlsx support in `ingest/holdings.py` (`_rows_from_body`, `openpyxl` pinned,
  URL → `.xlsx`); the `sectors_unresolved` disposition; the real TEKX daily golden fixture + provenance
  sidecar; the fixture-provenance discipline in CLAUDE.md.
- **To build (this slice):** SOI fetch + freeze-per-accession; the HTML industry-header parser with
  `fault`-on-unreliable; the frozen GICS industry→sector rollup table (config); wire the derived
  `{sector: weight}` into the existing `overlaps`/`corroborate` path as the **resolver** of
  `sectors_unresolved`, preserving the deferred reach-back to `detected_at`. Golden test: real TEKX Jul-
  2025 SOI → clears both-sides → +593 attaches; real TEKX Jan-2026 SOI → Utilities 6.4% → dormant (the
  as-of truth, threshold frozen). Add both real SOIs as recorded-real fixtures with provenance headers.
- **Retired / not built:** the external ticker→GICS classifier (the prior note's named unblock — no
  longer needed); any third-party sector feed. Broader per-issuer daily-file intake remains a separate
  concern for dispersion/rebalance coverage, not for corroboration sectors.

## Method note

Third convergent-prior correction of this arc, all broken the same way — by primary-source contact, not
by cross-thread review. The build thread's classifier recommendation, the CSV assumption, and the
inflationary register were each a default both instances shared; none was caught internally. The
standing habit stands: when a load-bearing fact about an external artifact is in question, open the
artifact.
