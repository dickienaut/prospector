# M5 SOI-fetch robustness — additions to the `SOI_FORMS` / fund-anchor work

*For placement in the "Deferred — EDGAR-SOI-fetch (fetch-on-cadence), scoped to M5" section of
`docs/decisions/2026-07-04-soi-derived-sector-concentration.md`, next to `SOI_FORMS` / `latest_soi`.
Both surfaced from the real Jul-2025 / Jan-2026 fixtures already in-tree — the same
only-the-real-filing-shows-it pattern as the mixed-case REIT, the xlsx, and the blank `Sector` column.
Neither is a slice defect (TEKX parses correctly today); both are runner robustness for when the fetch
targets other funds or later filings. They fold into spec rev13 / state-of-project rev4 when that fold
lands.*

1. **Anchor on a unique stem, never a full title — funds rebrand.** TEKX is titled "SPDR Galaxy
   Transformative Tech Accelerators ETF" in the Jul-2025 SOI and "**State Street** Galaxy Transformative
   Tech Accelerators ETF" in Jan-2026 — SSGA renamed the whole SPDR-Galaxy line between the two filings.
   So the exact-normalized-title anchor branch **misses on one of any two filings** whenever the name has
   drifted, falling through to the unique-substring branch — which makes the *stem* choice load-bearing.
   The M5 anchor config must key each fund on a stable unique stem — for TEKX, `Galaxy Transformative
   Tech Accelerators` (unique across the trust) — **never** a full or dated title (silent fall-through
   now, or an ambiguous/again-renamed fault later) and **never** bare `Galaxy` (matches TEKX, DECO, HECO
   → the ambiguous-anchor fault from hardening finding #1). The rebrand is the live proof, already in the
   fixtures, of why the stem — not the title — is the anchor.

2. **Header variants beyond the line-wrap (hardening #2 covered only the wrap).** In the same fixtures:
   DECO and HECO render `CONSOLIDATED SCHEDULE OF INVESTMENTS` (consolidated subsidiaries), and every
   fund carries `…SCHEDULE OF INVESTMENTS (continued)` continuation-page headers. `_fund_blocks` must
   therefore also (a) **accept the `CONSOLIDATED` prefix** — those sibling blocks are what bound the
   target fund's block, the end-bound defense the wrap fix was restoring; a missed sibling loosens the
   preceding fund's end-bound — and (b) **exclude `(continued)` continuation headers**, or a mid-SOI
   continuation line read as a fresh block-start will fragment a fund's block. TEKX is saved either way
   (plain header, fenced by its own `COMMON STOCKS` block), so not a slice blocker — but `CONSOLIDATED`
   and `(continued)` are exactly the blocks the runner hits the moment it targets a consolidated or
   multi-page fund, and they are already in the test data, so pin them with fixtures now rather than
   discover them live.
