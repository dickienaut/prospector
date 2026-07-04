# SOI-derived sector concentration — the EDGAR filing carries the GICS grouping (the ticker→GICS classifier is retired)

**Ratified:** design thread, 2026-07-04. Design spec: `docs/2026-07-04-soi-derived-sector-concentration.md`.
Supersedes the "named next slice" of `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`.
Folds into the next spec rev.

## The decision

The prior slice concluded the unblock for real-fund sectors was "an external ticker→GICS-sector
classifier." **That was a convergent-prior error.** The primary source already publishes the sector
grouping: a fund's periodic EDGAR filing renders a **GICS-industry-grouped Schedule of Investments** —
each holding under an industry header carrying that industry's percent of net assets (`SOFTWARE — 38.7%`,
`ELECTRIC UTILITIES — 6.4%`). Sector concentration comes **directly** from parsing those headers and
rolling **industry → GICS sector** through a frozen table. No per-ticker map, no security master, no
third-party feed. The SOI path is the **resolver** of the `sectors_unresolved → dormant` disposition the
daily-xlsx path emits (blank `Sector` column for active funds): when the first industry-grouped SOI lands,
a deferred pass derives `{sector: weight}`, thresholds it with the frozen `corroboration.sector_min_weight`,
and routes the launch through the **same** overlap/accrete/lag path as the holdings source — reaching back
with `detected_at` preserved as T2, so the cross-stream lag measures to detection, not to the SOI's as-of.

## What was built (this slice)

- `prospector/ingest/soi.py` — `SoiIngest` (freeze-per-accession, read side), `extract_soi_sectors`
  (fund-block isolation → `INDUSTRY — N.N%` parse → industry→sector rollup → reconcile), `dominant_sectors`.
- `prospector/sensors/soi.py` — `scan(...)`, the deferred accretion pass: fault-on-unreliable, else
  route via `launch_corroboration.route_corroboration` (extracted so the holdings and SOI sources share
  one overlap/emit/lag path — the emitted `launch`/`match` event is identical, so `cross_stream_lag` is
  unchanged).
- `config/prospector.yaml` — the `soi:` reader block and the frozen `gics_industry_sector:` rollup table.
- Recorded-real fixtures: `tests/fixtures/soi/tekx_soi_2025-07-31.htm` and `…2026-01-31.htm` (+ sidecars).

## CONTRACT

- **Frozen threshold.** `corroboration.sector_min_weight` (0.10) does not move to rescue a dormant
  snapshot. Ever. This is the sharpest anti-fitting case yet: TEKX's corroboration turns entirely on
  whether Utilities reads 10.7% (Jul-2025, clears) or 6.4% (Jan-2026, dormant). The derivation reports
  the marginal Utilities honestly and lets the as-of truth stand — including the dormant snapshots.
- **The industry→sector rollup table is frozen reference data, not a tunable.** Sourced from the GICS
  structure (MSCI / S&P Dow Jones), post the March-2023 reclassification. Values are the **exact 11
  canonical sector names in `sector_map`** (load-bearing: `overlaps` compares these strings). Re-freeze
  only on a GICS structure revision, with a `config.changed` fossil — never a sensor knob. An industry
  absent from the table → a `fault` (unknown industry), never a silent mis-roll.
- **No third-party sector feed.** A bought feed would breach the primary-source wall. If a constituent's
  sector were ever genuinely needed at ticker level (it is not, for this slice) it is derivable from the
  SOI corpus itself, never from an external vendor.
- **GICS is right for the overlap, wrong for the thesis (HECO, one level down).** For the *mechanical
  overlap with sector SPDRs*, GICS-to-GICS is correct and consistent (XLK/XLU are themselves GICS-sector
  funds). But never read the fund's compute×power thesis off its GICS top line — GICS shreds it across
  Utilities / Industrials / Energy / IT, and files bitcoin miners as "Software" (a taxonomy coincidence,
  weak thesis meaning; the Utilities leg is the genuinely meaningful one). The overlap is a mechanical
  screen; the human owns significance.
- **Parser/meaning/human boundary (same line the mandate-diff draws).** bs4 owns HTML **structure**; this
  module owns **which fund / which industry / the rollup**; the **human** owns **significance**. The
  extraction must never grow a "this change is meaningful" opinion.

## Primary-source findings (build-time contact with the real filings)

Both real TEKX SOIs were provided by the owner (egress to `www.sec.gov` is policy-blocked in the build
environment) as Safari `.webarchive` captures; the `WebMainResource.WebResourceData` — the exact bytes
sec.gov served — was frozen as the `.htm` fixtures. Reading them corrected/confirmed:

- **Form:** the sector-bearing artifact is the **`NPORT-EX`** exhibit (a multi-fund SSGA Active Trust
  report), not an N-CSR body. This sets the M5 `SOI_FORMS` finding. (N-PORT *XML* carries no GICS — the
  rendered SOI in the report is the sector-bearing artifact, as assumed.)
- **Multi-fund isolation is MANDATORY.** The same industry headers recur across the six funds (TEKX, DECO,
  HECO, ALLW, PRIV, PRSD); the parser isolates the target fund's block (its titled `SCHEDULE OF
  INVESTMENTS` → `COMMON STOCKS — N%` → `TOTAL COMMON STOCKS`) before parsing.
- **Mixed-case industry names.** GICS "Specialized REITs" renders `SPECIALIZED REITs — 2.8%` (lowercase
  `s`). A first-draft all-uppercase regex silently dropped it — and the **reconcile check caught it** (the
  parsed industries summed to 96.4% vs the `COMMON STOCKS — 99.2%` header). This is the safety net working
  as designed: reconcile-to-total turns a missed header into a `fault`, never a silent under-count.
- **Filed truth over prose (Jul-2025 clears four sectors, not three).** At the 0.10 floor the Jul-2025 SOI
  clears `{Financials 10.1, Industrials 13.9, Information Technology 52.0, Utilities 10.7}` — Financials
  (Capital Markets 4.7 + Financial Services 5.4) also clears, which the spec prose's three-sector list
  omitted. The XLK×XLU match and the **+593** are unaffected (overlap is a subset test: {IT, Utilities} ⊆
  the derived set). The golden asserts the real four-sector set. Jan-2026 clears `{Information Technology,
  Industrials}`; Utilities is 6.4% (Electric only) → below the floor → dormant.
- **The Utilities rollup is the granularity proof.** Jul-2025 Utilities 10.7% = Electric Utilities 5.3 +
  Independent Power & Renewable Electricity Producers 2.4 + Multi-Utilities 3.0 — three GICS industries
  that clear the floor **only together**; the industry→sector rollup is exactly what makes the leg present.
- **Both fixtures reconcile exactly** (99.2% / 99.6%). A derivatives-only fund (ALLW) has no `COMMON
  STOCKS` block → the parser faults ("COMMON STOCKS block header not found") rather than inventing sectors.

## Deferred — EDGAR-SOI-fetch (fetch-on-cadence), scoped to M5, tied to `EdgarClient`

The **reader** (parse + roll + route + golden tests, on hand-frozen fixtures) is built now. The **live
fetch** — discovering *which* NPORT-EX/N-CSR accession and *which document within it* carries a fund's
current SOI — is deferred to the M5 runner, tied to the existing `EdgarClient`:

- `SOI_FORMS` (starting `NPORT-EX`, `N-CSR`, `N-CSRS`) + a `latest_soi(submissions)` mirroring
  `latest_prospectus`, and accession `index.json` resolution for the non-primary SOI document.
- `SoiIngest.freeze` is already the write primitive the M5 fetch will go through; `sensors/soi.scan`
  already takes a `fetch_body` seam (the runner wires it to `EdgarClient`; tests pass a fixture thunk).
- **Invariant (do not conflate): drop-and-freeze for tests, fetch-on-cadence for the runner.** The frozen
  `.htm` fixtures are dropped once by hand and are **never** refreshed by fetch code — the offline tests
  must stay deterministic. The runner's fetch feeds the *live* pipeline only.

`parse_nport_holdings` stays the labeled §3b stub — do not fill it (N-PORT XML carries no GICS).

## Method note

Third convergent-prior correction of this arc (after CSV-not-xlsx and the blank `Sector` column), all
broken the same way — by primary-source contact, not cross-thread review. The classifier recommendation
was a default both instances shared; opening the filing dissolved it. The standing habit holds: when a
load-bearing fact about an external artifact is in question, open the artifact.
