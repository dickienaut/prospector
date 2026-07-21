# Mandate — the J.P. Morgan Q&A strategy heading (a question, not a config line)

*2026-07-21, build seat. The third and last of the same-day mandate stack (PR1 over-attribution guard →
PR2 block isolation → **PR3 this**). The deploy doc parked this as "a one-line config addition… land after
block isolation." Block isolation landed (PR2), so this is that follow-up — but the "one-line config"
premise was **wrong**, and the measurement is what caught it.*

## What the deploy doc expected, and why it was wrong

The residue after the supplement noise-cut was the J.P. Morgan **Q&A summary** format: the strategy sits
under a heading phrased as a question — `What are the Fund's main investment strategies?` — which
`strategy_headings` did not list. The deploy doc (and the 2026-07-19 pair-blindness note) treated the fix as
adding that string to the config, deferred only because pre-isolation it would have fired false
corroborations on multi-fund filings.

Adding the config line **did nothing** — the corpus measurement showed **0 documents newly reliable**. Two
reasons, neither fixable by config:

1. **It is a question.** The strict heading matcher (`_is_heading`, the MANDATE-PROSE-HEADING guard from
   #118) strips `:.` but not `?`, so the trailing `?` read as a non-connective prose tail and disqualified
   the line. The guard built to reject prose was — correctly by its own logic — rejecting a legitimate
   **question-form** heading.
2. **A smart apostrophe.** The filing renders `Fund&rsquo;s` → a curly `’` (U+2019); a config pattern
   carries a plain `'`, so `startswith` failed before the `?` even mattered.

(The pair-blindness note's "6 newly reliable" was measured *before* #118's strict matcher landed, when a
bare `startswith` ignored the `?`. The strict matcher silently re-closed the door — a real regression the
config line alone could not reopen.)

## The fix

- **`_is_heading`** now treats a trailing `?` as terminal heading punctuation (`rstrip(":.?")`) and
  normalizes smart apostrophes (`’`/`‘` → `'`). Terminal-form only — a prose sentence still runs on into a
  content word after the pattern, so the guard is **not** loosened (verified: the prose-rejection tests pass,
  and a question that continues into a content word — "…strategies designed to do?" — is still rejected).
- **`strategy_headings`** gains `what are the fund's main investment strateg` (plain apostrophe — the matcher
  normalizes). It is priority-2 (after `principal investment strateg`, before `investment objective`), so a
  filing that carries the standard heading is unaffected.

`strategy_headings` is a DEFAULT (config), but the matcher change is a code fix and this records both.

## Measured, not assumed (the whole point of the deferral)

Run over all 148 frozen blobs, **with the SGML headers backfilled** so the guard + isolation are modeled the
way production behaves (not a misleading whole-doc view):

- **Recall: 6 documents newly reliable** — the J.P. Morgan filings (S000101505/06/27 × two accessions),
  each now extracting its real Q&A strategy ("Under normal circumstances, the Fund invests at least 80%…").
- **Safety: 0 pairs change their effective (guard + isolation + diff) outcome; 0 pairs newly fire
  `mandate.changed`.** The heading recovers *extraction*; it creates **no** new corroborations, because the
  over-attribution guard (PR1) and block isolation (PR2) already resolve which fund owns a filing. This is
  exactly the "safe only after isolation" the deploy doc required, now demonstrated rather than asserted.
- **0 supplement/SAI classification flips** — the matcher change does not reclassify any 497 sticker / SAI
  (the trailing-`?` / apostrophe forms don't occur in a supplement's self-declaration).

Honest scope: on the *current* store the 6 recovered filings are over-attributed JPM series that the guard
already skips, so the **sensor-level** effect today is nil. The value is (a) the matcher fix — a recall gap
for the whole class of Q&A-format prospectuses, not just JPM — and (b) correctness/future-proofing: a
correctly-attributed JPM-format filing now diffs its real strategy instead of faulting. And it is proven to
add zero false firings.

## Verification

- Unit: `_is_heading` matches the Q&A question heading in both apostrophe forms and with/without `?`, and
  still rejects a question that runs on into content; `extract_mandate(JPM_QA)` recovers the real strategy
  and does not mistake the prose "investment objective" line; a cosmetic re-file of the JPM fixture is not a
  change. The module test CFG now carries the heading (matches production).
- Corpus-check: 6 newly reliable, 0 classification flips, 0 newly-firing pairs (headers backfilled).
- Full suite green.
