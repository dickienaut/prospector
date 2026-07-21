# Mandate series-scoped confirmation — the SGML SERIES/CLASS header, and the B1 over-attribution guard

*2026-07-21, build seat. Design-thread-authorized (the owner chose "go straight to block isolation"; this
is PR1 of that work — the ingest primitive + the safety guard it enables). CONTRACT-adjacent (§4d) and it
advances a ratified residual (**B1**), so it is recorded here. The sequel — per-fund block isolation (PR2) —
builds on this primitive and gets its own record.*

## The problem

Two bugs compound on the mandate diff:

- **B1 (prospectus attached at trust level, not series)** — the SEC submissions doc is per-CIK with no
  series dimension, so `latest_prospectus` returns the **trust's** newest prospectus for **every** series of
  the CIK. A filing gets frozen under — and diffed for — series it does not cover.
- **`MANDATE-MULTIFUND-SECTION`** — a multi-fund filing carries one strategy section per fund; `extract_mandate`
  takes the first, so every claimant series diffs the first fund's strategy.

The live evidence (2026-07-19): a Goldman 485APOS with two funds' sections emitted **byte-identical**
`mandate.changed` for GCPB and GINC; and — verified while building this — J.P. Morgan 497
`0001193125-26-305575` is frozen under three unrelated series (LGDS/JPRF/JLVP) while its filing header shows
it covers **only** a fourth, new series (S000108870, All Country Research Enhanced Equity ETF). #122 *marked*
these as unattributable; it did not stop them. The containment ("all 64 historical `mandate.changed` routed
to `_system`; no active lead touches these funds") was **circumstantial, not structural**.

## The primary-source answer

The EDGAR full-submission SGML header carries `<SERIES-AND-CLASSES-CONTRACTS-DATA>` — per filing, the exact
set of series it covers, each with its `SERIES-NAME` and class `TICKER`. This is B1's deferred series-scoped
confirmation, named as the unblock in three places (`edgar.py` `confirm_prospectus` docstring;
`docs/decisions/2026-07-06-identity-integrity.md:95`; `docs/notes/2026-07-20-v1.0.5-deploy.md`). Verified
present and populated even on **preliminary** filings (485APOS/497 with placeholder tickers). It is fetched
by a **Range GET** of the submission `.txt` (the header is at the top; the body is multi-MB).

## What PR1 ships (the ingest primitive + the over-attribution guard)

1. **`EdgarClient.filing_header(cik, accession)`** — Range-GETs the SGML header (accepting `206 Partial
   Content`), escalating `0-49999 → 0-262143 → unranged` until the `</SEC-HEADER>` sentinel is present, and
   freezes it via the §3 `persist` seam. A still-truncated header after the cap is detected downstream and
   **faults, never guesses coverage off partial bytes**.
2. **`parse_series_classes(header_bytes)`** (pure, in `ingest/prospectus.py` — so the corpus-check's
   single-module `exec` reaches it) → `{series, complete, has_series_block}`, keeping **three signals
   distinct** (the fail-silent trap): authoritative coverage · complete-but-no-series-block (older/non-fund
   form, benign) · truncated (coverage unknown → fault).
3. **`ProspectusIngest.series_classes(cik, accession)`** — freeze-once (accession-keyed, series-independent),
   re-read thereafter. A header that cannot be **fetched** degrades to `complete: False` ("coverage unknown")
   → the caller faults, never silently reads "not covered" from a failed fetch.
4. **The over-attribution guard** in `mandate.scan`, consulted **before freezing the body** (so a wrong-fund
   filing is neither frozen under this series — no new B1 pollution — nor diffed):
   - covered → proceed; **not covered → `not_covered`**: emit nothing, no fault (the expected B1 state);
   - **truncated / unfetchable header → review-advisory** (refuse to guess, §4d);
   - complete-but-no-series-block → fall back to the `series_sharing` tripwire (shared → review; lone → proceed).
5. **Coverage-aware `_last_frozen_prospectus`** — the §9c prior walk also skips a frozen full prospectus whose
   header does not cover this series (the same way it skips a supplement), reaching the true prior **for this
   fund**.

## Doctrine held

- **§4d, unchanged:** a false `mandate.changed` is worse than a missed one — every un-verifiable case
  (truncated / unfetchable header, ambiguous no-series-block) **faults to the existing review-advisory**.
- **Reads live, no new registry field.** The header is consulted at diff time, not stored on `FundEntry` —
  consistent with the B1 ruling that declined a `prospectus_scope` §2 amendment. The registry
  `prospectus_accession` stays registrant-level (the honest residual); the mandate sensor now **verifies**
  coverage rather than trusting the over-attributed field.
- **`series_classes` (filing) vs `series_sharing` (our store)** are distinct and both kept: the header says
  which series a filing *covers*; `series_sharing` says which series we *froze it under*. The gap between them
  IS the over-attribution.

## B1 status

Advanced from 🟡 *"accession residual flagged"*: series-scoped confirmation is now **real for the mandate
diff** — the over-attribution no longer produces false diffs (Shape A is fixed). The registry field remains
registrant-level (deferred, as ratified); the identity/registry consumers are untouched by this PR.

## The sequel (PR2, not in this PR)

Block isolation uses the **same header's per-series fund name** as the `fund_anchor` to isolate each fund's
block within a genuinely multi-fund filing (Shape B) — restoring recall and **unblocking the parked J.P.
Morgan Q&A-heading fix**. #122's store-side `series_sharing` marking is then replaced with header-derived
`covered_series` provenance.

## Verification

- Unit (offline): `parse_series_classes` on the recorded-real JPM (covers S000108870 only) and Goldman
  (GCPB + GINC) headers plus the three-signal edges; `filing_header` (206, range escalation, unranged
  backstop, persist); the guard through `mandate.scan` (`not_covered` → no event/no freeze; truncated →
  advisory; covered-multi-fund → still diffs; no-series-header shared → review).
- Runner (`test_runner_mandate.py`): JPM-shape → `not_covered`, nothing emitted, body never fetched;
  coverage-aware prior reaches back across a wrong-fund frozen filing.
- Corpus-check (`tools/corpus-check/`): section 6 now models the guard from frozen headers and reports the
  **guard skips** (Shape-A firings removed). Run `backfill_headers.py` once to freeze headers for the whole
  store, then the guard is modeled over all 148 blobs (missing headers are reported, never read as a clean
  pass — the CORPUS-CHECK-PAIRBLIND lesson).
