# Mandate fund-block isolation — the target fund's own strategy section in a multi-fund prospectus

*2026-07-21, build seat. The sequel to the same-day PR1 record
(`2026-07-21-mandate-series-scoped-confirmation-over-attribution-guard.md`). Design-thread-authorized
(the owner chose "go straight to block isolation"). CONTRACT-adjacent (§4d); closes bug
`MANDATE-MULTIFUND-SECTION` and completes the B1 series→block tie for the mandate diff.*

## The problem this closes

PR1 fixed **Shape A** — a filing frozen under a series it does not cover (the over-attribution guard skips
it). PR2 fixes **Shape B** — a *genuinely* multi-fund prospectus. `extract_mandate` took the **first**
strategy section, so when a filing carries several funds, every covered series diffed the **first** fund's
strategy. On 2026-07-19 two Goldman series (GCPB, GINC) sharing one 485APOS emitted **byte-identical**
`mandate.changed`. #122 *marked* that as unattributable; it did not fix it.

## The fix — isolate the fund's block by name, then scan inside it

When the SGML SERIES/CLASS header (PR1) says a filing covers **>1** series, the sensor hands
`extract_mandate` the target fund's SERIES-NAME (`fund_anchor`) + all covered names (`fund_names`). The
extractor isolates the target's block **before** running the ordinary strategy finder:

- **The fund NAME is the block delimiter — the strategy heading is not.** "PRINCIPAL INVESTMENT STRATEGIES"
  recurs 2–3× per fund (summary, statutory, SAI) — which is exactly why "take the first" was wrong. Each
  fund's block opens with a `{SERIES-NAME}…Summary` heading; that is the boundary.
- **Selection mirrors the SOI reader** (`ingest/soi.py` `extract_soi_sectors`): candidate block-starts are
  heading-shaped lines carrying a "Summary" token + a covered name; the anchor picks its block by
  **unique substring** (the header name is a substring of the affixed heading title); a candidate wins only
  if its block **bounds a valid strategy section** (this filters the table-of-contents copies structurally —
  a TOC entry's region is just a page number). Then the existing continue-scan runs **inside** `[block_start,
  next_block_start)`.
- **Every un-isolable case FAULTS** (`reliable: False` → the existing review-advisory): the anchor matches no
  block (name drift on a renamed fund), or matches ambiguously (the anchor name is a substring of another
  covered fund's name — the SOI anti-guess rule). §4d: a false `mandate.changed` is worse than a missed one.
- **`diff_mandate` isolates each side with ITS OWN filing's name** for the stable `series_id`, so a fund
  name never crosses from one filing into the other — name drift across filings is un-weaponizable.
- **Backward-compatible:** a single-fund filing (`fund_names` ≤ 1) or no anchor → the whole document,
  **byte-identical to before** (the single-fund majority path — a regression gate in the tests and the
  corpus-check).

## Verified on the real filing (not synthetic)

On the real Goldman `0001193125-26-300911` body, `extract_mandate(anchor="…Core Plus Bond ETF")` returns the
Core Plus section and `anchor="…Income ETF")` returns the Income section — they **differ** — where the
whole-doc extractor returns Core Plus for both. The fixture `goldman_multifund_body_300911.html` is that
filing's real rendered text (both fund-summary blocks + the TOC), re-wrapped one line per `<p>` for a compact
committed fixture (the raw HTML is machine-generated with per-word tags, too large and too fragile to trim
by bytes); provenance in its `.source.txt`. The full-corpus proof runs through the corpus-check section 6
(after `backfill_headers.py`).

## The #122 marking is superseded

#122 stamped `shared_accession`/`sharing_series` because the diff returned the first fund's section for every
series ("we cannot attribute this to one fund"). That premise is now false — the guard dropped the wrong-fund
filings and isolation gives each series its own section. So the store-side `series_sharing` marking is
**removed** from the emit path; a multi-fund filing instead carries **neutral header-derived provenance**,
`covered_series` (which series the filing covers, straight from the header — strictly more accurate than
"which series we happened to freeze it under"). `series_sharing` itself survives as the no-series-header
fallback tripwire in the guard.

## Status

- **`MANDATE-MULTIFUND-SECTION` → ✅** — both shapes fixed (A: over-attribution guard, PR1; B: block
  isolation, PR2).
- **B1** — the series→block tie is now BUILT for the mandate diff. The registry `prospectus_accession` field
  remains registrant-level (the honest residual, unchanged).

## Deliberately deferred (PR3)

The **J.P. Morgan Q&A heading** (`what are the fund's main investment strateg`) — now safe *after*
isolation, but a global `strategy_headings` config change best gated by a full corpus-check run (headers
backfilled) so its effect is measured, not assumed (the deploy-doc's "after block isolation" rule).

## Verification

- Unit (offline): isolation on the real Goldman body (distinct per-fund sections; whole-doc == first fund);
  anchor-not-found → fault; ambiguous anchor (a name that is a prefix of another) → fault; single-fund /
  no-anchor → whole-doc unchanged (regression); `diff_mandate` per-side (Core Plus moved, Income did not —
  no cross-fund fire); the sensor stamps `covered_series`, not the old keys.
- Full suite green. Corpus-check section 6 now models isolation per side (after the one-time header backfill).
