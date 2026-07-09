# `prospector/ingest/` — freeze-before-parse substrate (spec §3)

This is the pipeline's mouth: every network client that fetches an external artifact lives here, and
every one obeys the same discipline — **freeze the raw response body to disk BEFORE anything parses
it**. Parsing is then a pure function of the frozen bytes, so a rerun is fully offline after one pull,
a parse failure still leaves the body on disk for a postmortem, and **a missing row is a missing row**
(no forward-fill, no fabrication). `ingest/` produces frozen substrate + tidy frames only; the
_meaning_ (departures, overlaps, changes) is decided one step downstream in `sensors/`. Built and
wired into the M5 runner, with two named-and-deferred sub-slices called out per module below.

## Modules

- **`edgar.py`** — the EDGAR client, the identity substrate's **only network surface** (declared
  User-Agent — SEC 403s undeclared ones — rate-limited under 10/s, exponential backoff on 429/403/5xx,
  every body frozen via an injected `persist` seam). `resolve_ticker`/`resolve_series` run the §2
  resolution flow (ticker or the _detected_ series id — I1 sidesteps the reused-ticker trap);
  `classify_soi_target`/`resolve_soi_target` locate _which_ accession + _which exhibit within it_
  carries a fund's GICS-grouped SOI (§9b), returning coordinates only (the runner fetches the bytes).
  Two **named deferrals** live in `confirm_prospectus`: **B1** (submissions is per-CIK, so the picked
  prospectus is the trust's newest, not proven to cover the resolved series) and **B2** (older filings
  in `filings.files[]` pages are unpaginated → `older_filings_unread`, never a silent `no_prospectus`).
- **`holdings.py`** — SPDR daily holdings ingest → 90%-weight `MembershipSnapshot` (the §4d keystone
  that later unblocks dispersion/rebalance/launch-corroboration). **Verified against the real file:**
  SSGA serves **xlsx, not CSV** (`parse_spdr_holdings` reads both; a synthetic CSV fixture had hidden
  this), and for an active/thematic fund the `Sector` column is blank `"-"` → file-sector concentration
  is empty → the honest disposition is `sectors_unresolved` (resolved later by `soi.py`, never guessed).
  A weight-sum band guards the percent-vs-fraction unit trap (H1). **`parse_nport_holdings` is the
  DEFERRED §3b NPORT-P stub — it raises `NotImplementedError`** (a thin signature so the dispersion PIT
  slice can drive it later with no sensor change). Note: the ingest _reader_ is built, but the runner
  does not yet drive holdings on cadence — that's the deferred dispersion/rebalance vertical (only XLK
  has a fixture today).
- **`prices.py`** — daily EOD **adjusted** closes for the correlation grid. **Tiingo is primary**
  (`adjClose`, CRSP split+dividend-adjusted, verified against the NVDA-2024 10:1 split); **stooq is
  fail-closed** behind the P1 `guard_live_source` (its `close` is only _assumed_ adjusted — an
  unadjusted close silently corrupts every return across a split, the base of the whole sensor stack);
  **yahoo was demoted** (it bot-challenges non-browser clients on a TLS fingerprint). The Tiingo token
  rides the `Authorization` header inside a `_Secret` redaction holder — never the URL, never the
  fossil. Adjusted closes are **retroactively mutable**, which is _why_ `ingest/prices/` is dated
  substrate, not the append-only record. `build_panel` outer-joins tidy frames (leading NaN kept, never
  filled).
- **`prospectus.py`** — prospectus HTML fetch/freeze (blob-per-accession) + the §4d mandate-diff.
  `html_to_text` (bs4, pinned) turns messy filing markup into navigable text; `extract_mandate` locates
  **only the principal-investment-strategy section** (a full-text diff is a false-positive machine — the
  diff-trap); `diff_mandate` reports whether that section's text moved. **Three owners, one line this
  module must not blur:** bs4 owns _structure_, this module owns _meaning_ (which section / did it
  change), the human owns _significance_. Unreliable extraction → `reliable: False` → the caller emits a
  `fault`, never a false `mandate.changed`. Built and wired (`sensors/mandate.py` on cadence).
- **`soi.py`** — SOI ingest + GICS-industry-grouped sector derivation — the **§4c resolver of
  `sectors_unresolved`**. Parses the industry headers of a fund's EDGAR Schedule of Investments
  (`SOFTWARE — 38.7%`) and rolls industry → GICS sector through the frozen `gics_industry_sector` table
  (config, CONTRACT). **Multi-fund block isolation is mandatory** (one NPORT-EX carries many funds; the
  same headers recur), and a reconcile-to-`COMMON STOCKS`-total check faults rather than emit a wrong
  sector set. This module is the **reader + freeze side**; the **live EDGAR fetch (which accession/doc
  to pull) is now wired in the M5 runner** (`_run_soi_corroboration` → `classify_soi_target` →
  `filing_text` → this module's `freeze`).

## Important to know

- **Freeze precedes parse, always** (`write_atomic`): a corrupt body still lands on disk, and
  `load_frozen`/`load_frozen`-style re-reads are byte-identical, so a later, better parser re-derives
  old filings with no stored staleness.
- **Two intake paths that must never conflate** (CLAUDE.md): tests **drop-and-freeze** hand-built
  fixtures; the runner **fetches on cadence**. Fixtures are never refreshed by fetch code. Every fixture
  is recorded-real (with a source-URL + retrieval-date sidecar/header) or declared-synthetic in-band.
- **Identity keys on the SEC series id, tickers are display-only** (the HECO rule, §2). Every client
  _fetches_ by ticker but _freezes and keys_ by `series_id`; a source quirk (SPDR's lowercased filename,
  stooq's `.us` suffix) stays inside the URL builder and never leaks past it. Constituents in a basket
  are individual equities (CUSIP/ISIN), never run through the fund registry.

## See also

- Spec §3 (freeze the substrate), §2 (identity), §4c/§4d (launch corroboration, mandate-diff, SOI
  resolver), §9b/§9d (SOI target resolution + deferred corroboration retry) in
  `docs/prospector-v1-spec-rev14-2026-07-08.md`; `ARCHITECTURE.md` §2 (module map) and §9 (built vs
  deferred).
- Decisions: `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`,
  `2026-07-04-soi-derived-sector-concentration.md`, `2026-07-03-launch-corroboration-existence-proof.md`,
  `2026-07-03-mandate-diff-targeted-section.md`, `2026-07-07-tiingo-price-source.md`,
  `2026-07-06-prices-ingest-and-p1.md`, `2026-07-06-soi-fetch.md`, `2026-07-06-soi-corroboration-retry-9d.md`.
