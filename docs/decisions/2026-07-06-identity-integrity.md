# Identity-integrity fixes I1/B1/B2 — the HECO reused-ticker guarantee, hardened

*Decision record, 2026-07-06. Lands the three identity-integrity findings from the Claude-Science QA
review (`docs/prospector_full_review_claude_science.md` §§I1/B1/B2) named as runner-path prerequisites
in `docs/prospector-m5-runner-spec-2026-07-05.md` (§Prerequisites). Must land **before the runner runs
live cadence** — I1 sits in the launch-recording path the M5 skeleton already wired. Follows step 2
(SOI-fetch); precedes step 3 (§9d retry loop + §9c + §9e).*

## The through-line

The whole identity layer exists to defeat the HECO false-positive: a ticker reused across two different
SEC series over time (`docs/` HECO case). Everything downstream keys on the **series id (S######)**,
never the ticker; the write path rejects a bare ticker (`fund_registry._validate_identity`). The review
found three places where that guarantee was quietly circumvented **without raising** — the dangerous
kind, because the write-path check is syntactic (is it an S######?), not semantic (is it the *right*
one?).

## I1 — thread the DETECTED series id, never re-derive by ticker

**Bug:** the launch sensor detects the exact `(symbol, seriesId)` pair from the frozen mf-map diff, then
`sensors/launch.scan` bound the series to a throwaway `_series_id` and passed only the symbol;
`register_launch → resolve_ticker(symbol)` re-derived the series independently via `matches[0]`. On a
reuse transition — when the map lists the ticker under both the old and new series — `matches[0]` is a
coin-flip by document order, so the fund could register under the **wrong** series, defeating the very
guarantee the layer exists for.

**Fix:**
- `sensors/launch.scan` now threads the detected `series_id` into `register_launch`.
- `register_launch(ticker, name_raw, detected_at, series_id=None)` — `series_id` is an **optional
  trailing** param (backward-compatible; the launch path always supplies it, a caller without a
  detected series falls back to the ticker re-derive). When supplied, resolution keys on the series via
  the new `edgar.resolve_series(series_id, ticker, client)` — the typed-return sibling of the manual
  path's `_resolve_series` — which looks the series up in the mf-map (correct cik + aggregated class
  ids) and only **verifies** it, never re-answers "which series is this ticker?".
- The detected series is threaded into the **retry queue** too: a new `detected_series_id` column on
  `resolution_queue` (a module-owned working table — registry.py's DDL stays frozen), stored by
  `record_failure`, and `run_retries` resolves on it (else falls back to the ticker). So a launch that
  fails at register time (EDGAR indexing lag) resolves on the **series** when it retries, not a
  re-derive.
- **Ambiguous-symbol → fault (review's I1-adjacent note):** `resolve_ticker` now returns
  `ambiguous_symbol` when a symbol maps to more than one `(cik, series)`, instead of a silent
  `matches[0]`. The launch path sidesteps this entirely (it resolves on the detected series); this
  guards the ticker-only callers (manual/CLI), mirroring the SOI anchor-ambiguity discipline.

**Proven:** `test_i1_reused_ticker_is_ambiguous_to_resolve_ticker` (the trap faults, never guesses),
`test_i1_resolve_series_keys_on_the_detected_series` (the same ticker resolves to whichever series was
detected), `test_i1_scan_registers_the_detected_series_under_ticker_reuse` (end-to-end: the fund
registers under the DETECTED series, and the old series is NOT registered),
`test_i1_retry_resolves_on_the_stored_detected_series` (the retry fires on the stored series when EDGAR
indexes it late — proves-it-fires, not merely-called).

## B1 — series-scope the prospectus confirm (identity half fixed; the accession residual deferred)

**Bug:** the EDGAR submissions doc is per-CIK with **no** series/class dimension, so "a prospectus-family
filing exists" was verified at the registrant level and the stored `prospectus_accession` is just the
trust's newest 485BPOS/497/N-1A. On a multi-series trust (CIK 1516212 hosts TEKX/DECO/HECO+), resolving
one series attaches the trust's newest prospectus regardless of which series it covers.

**Decision (owner-ratified 2026-07-06): resolve-by-series now, defer the accession flag.**
- The **identity half is fixed** by I1's `resolve_series`: cik + class ids now come from the detected
  series, not `matches[0]`.
- The **residual** — the `prospectus_accession` is registrant-level, not proven to cover the series — is
  **deferred**. Its true fix needs the filing's SERIES/CLASS header, which requires filing-text ingest
  (not built — the same gate as the mandate-diff, §4d). The alternative, a `prospectus_scope` field on
  `FundEntry`, was declined: `FundEntry` is documented as "spec §2's field list, nothing more," so
  adding a field is a §2 CONTRACT amendment (design-thread only) — the owner chose deferral over that.
- `confirm_prospectus` (shared by the ticker, series, and manual paths) carries the limitation in its
  docstring so the gap is honest in the code. Its only downstream victim (the mandate-diff) is not live
  until step 3+, so this does not block live launch-recording cadence.

## B2 — filings.files[] pagination (minimal honest guard; full pagination deferred)

**Bug:** `filings.recent` holds only the newest ~1000 filings; older ones live in `filings.files[]`
pages no code followed. A long-lived registrant whose last prospectus predates the recent window
resolved to a silent `no_prospectus` and would land in the manual queue **wrongly**.

**Decision (owner-ratified 2026-07-06): minimal honest guard.** `confirm_prospectus` now returns a
distinct `older_filings_unread` reason (not `no_prospectus`) when no prospectus is in `recent` **and**
`filings.files[]` is non-empty — the answer is inconclusive, so flag it rather than silently mis-queue.
Following the pages (fetching `filings.files[]`) is the named deferral; the launch stream targets
brand-new funds that cannot overflow the window, so this only bites the manual-resolve path on an
ancient registrant. Proven: `test_b2_older_filings_unread_is_flagged_not_silent_no_prospectus` (with
files[] → flagged; without → the honest `no_prospectus`).

## Shape notes

- `confirm_prospectus(subs, cik) -> (accession, reason, detail)` and `_aggregate_class_ids` are the two
  new shared helpers in `edgar.py`; `resolve_ticker`, `resolve_series`, and the manual `_resolve_series`
  all route through `confirm_prospectus`, so B1/B2 behavior is identical across every §2 path (no drift).
- No CONTRACT change: the `funds` and `resolution_queue` tables are module-owned working indices (the
  registry.py events DDL stays frozen/vendored); `FundEntry` is untouched.

## Still deferred (named, not silent)

- True series-scoped prospectus confirmation (B1 residual) — unblock: filing-header (SERIES/CLASS) parse,
  the mandate-diff gate; or a design-thread `FundEntry.prospectus_scope` field.
- `filings.files[]` pagination (B2 full) — unblock: an `EdgarClient` method to fetch and search the older
  pages when `recent` yields nothing.

## Tests

407 pass (was 400; +7). All offline behind fixture fetches; the autouse socket guard fails any real
connection. The pre-existing HECO/failure/manual-resolve/CLI tests pass unchanged — the optional-trailing
`series_id` preserves the ticker-re-derive fallback those exercise.
