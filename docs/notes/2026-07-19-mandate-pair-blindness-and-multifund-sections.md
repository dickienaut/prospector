# The fix that scored clean and would have been wrong — pair-blindness, B1, and multi-fund sections

*2026-07-19, build seat. A finding note, written because the finding is worth more than the fix that
produced it. Context: GitHub Actions was in a partial outage, so this session was local-only work
following #118 (`MANDATE-SOURCE-NEWLINES`).*

## What I set out to do

Close the last 3 mandate advisories from the 2026-07-19 tick. They were fully diagnosed: the
J.P. Morgan **Q&A heading variant** — the one half of the noise-cut note's item 1c that genuinely
survives. Both filings carry, verbatim:

```
[88]  What are the Fund's main investment strategies?
      -> "Under normal circumstances, the Fund invests at least 80% of its Assets…"
[164] Main Investment Strategies          <- runs to EOF, no stop heading (correctly unreliable)
```

`strategy_headings` is a **DEFAULT** (config), so this looked like a config line plus verification.
The Q&A heading is also the *right* target: it bounds cleanly at `Purchase and Sale of Shares`, and
it is the **summary** strategy section — the same target `principal investment strateg` hits in every
other filing.

I added it. Then I ran the corpus check built earlier the same session.

## What the corpus check said

```
1. SUPPLEMENT/SAI CLASSIFICATION FLIPS: 0
2. RELIABILITY: 61/68 -> 67/68        REGRESSIONS: 0
3. NEWLY RELIABLE: 6                  (all six the JPM filings)
4. SECTION TEXT CHANGED: 0
5. REMAINING UNRELIABLE: 1            (and that one is a correct fault)
```

A clean win by every number the harness produced. **It was wrong.**

## What was actually true

The three series sharing that accession — `S000101505` (LGDS), `S000101506` (JPRF), `S000105027`
(JLVP) — all carry `name = "J.P. Morgan Exchange-Traded Fund Trust"` in the registry. The **trust**,
not the fund. That is bug **B1** (*prospectus attached at trust level, not series*), already on the
register as a ratified 🟡 residual.

And the two accessions being compared are prospectuses for **different funds**:

| accession | fund |
|---|---|
| `0001193125-26-302736` | a U.S. large-cap **value** long/short fund |
| `0001193125-26-305575` | JPMorgan **All Country Research Enhanced Equity** ETF |

So the "fix" would have converted **3 safe faults into 3 false `mandate.changed` events**, each
summarising a diff between two unrelated funds' strategies. Precisely the outcome §4d exists to
prevent: *a false change claim is worse than a missed one.* Reverted, unshipped.

## The generalizable defect — the harness was pair-blind

The harness judged documents **one at a time**. The sensor does not: it diffs a **pair** (prior frozen
filing, current filing) and emits from the comparison.

> **A change can improve every document individually and still make the sensor emit garbage.**

Per-document metrics are blind to that *by construction* — no amount of care reading that report would
have caught it. This is the same shape as the lesson that produced the harness twelve hours earlier
(*a fix verified only on the documents it targeted is verified on a biased sample*), one level up:
**verifying the unit you changed is not the same as verifying the unit that acts.**

Fixed: the harness now has a **section 6** that models what the sensor would actually do — it resolves
each series' (prior, current) pair the way `_last_frozen_prospectus` does, runs the real `diff_mandate`
under both baseline and HEAD, and reports **pairs that would newly fire `mandate.changed`**. It also
flags the structural tell directly: **an accession frozen under more than one series**, which means
those series share a document and at most one of them legitimately owns it.

Run against the pre-#118 baseline, section 6 flags the JPM pair on the first line of output.

## The second finding — multi-fund prospectuses have no fund-block isolation

Chasing the shared-accession flag turned up **two distinct shapes**, both live in the store:

1. **One fund, several claimants** (`0001999371-26-015168`): a single-fund prospectus with **one**
   strategy section, pointed at by **2** series. One of them is a B1 mis-attribution.
2. **Genuinely multi-fund** (`0001999371-26-014940`): **two** strategy sections, pointed at by **4**
   series. `extract_mandate` takes the **first** heading that bounds a section — so all four series
   diff the *first fund's* strategy. At most one of the four is correct.

Shape 2 is a gap we have already solved once, elsewhere, and know the shape of: the SOI work made
**fund-block isolation mandatory** for multi-fund `NPORT-EX` exhibits (*"the sector-bearing artifact is
multi-fund — fund-block isolation is mandatory"*). The mandate extractor never got the same treatment,
because until #118 these documents mostly failed extraction outright and faulted safely.

**#118 changes that.** It is already merged to `main` (not yet deployed — prod is pinned at `v1.0.4`).
Against the pre-fix baseline the pair check reports **6 newly-firing `mandate.changed`, 5 of them
carrying the shared-accession flag.** #118 did not *create* this — B1 and the missing isolation
predate it — but it **converts safe faults into firing corroborations**, which is what makes it
visible and what makes it matter.

### Blast radius today: real, contained, and contained *circumstantially*

- All **64** `mandate.changed` events in the store's history routed to `_system`.
- Every active lead is a sector-SPDR pair (`XLU×XLV`, `XLC×XLF`, …); none of these third-party ETFs
  sits in a lead basket, so `watching_leads` returns empty and the event lands on `_system`.
- `mandate.changed` is a **silent** corroboration: it never pages.

So the damage is false records in an append-only store, not a false live-lead corroboration. **But the
containment is circumstantial, not structural** — it holds because of which leads happen to be active
today. A lead forming over a basket containing one of these funds would accrete a false corroboration,
and nothing in the code prevents it.

## Options (owner's call — this is §4d/CONTRACT-adjacent, and B1 is a ratified residual)

1. **A narrow safe-path guard (recommended).** If the current or prior accession is frozen under more
   than one series, **do not diff** — raise the existing extraction-unreliable **review-advisory**
   instead. Small, uses machinery that already exists, and is exactly the doctrine already in force:
   *flag, don't guess.* Costs recall on genuinely-shared filings until isolation exists.
2. **Fund-block isolation for the mandate extractor**, mirroring the SOI solution: isolate the target
   fund's block before locating the section. The correct end state, and materially more work — it needs
   a reliable way to tie a series to its block within a combined filing (which is B1's core problem).
3. **Accept and defer.** Deploy #118 as-is, knowing false silent corroborations will land on `_system`.
   Cheapest, and the record is append-only, so the false entries are permanent.

I did **not** implement any of these — 1 and 2 touch how §4d decides to fault, and B1 is a ratified
residual whose scope belongs to the design thread.

## What shipped from this session

- The corpus-check harness, **with** section 6 (pair-level) — `tools/corpus-check/`.
- Register rows: `CORPUS-CHECK-PAIRBLIND` (fixed), `MANDATE-MULTIFUND-SECTION` (open).
- **Not** the JPM Q&A pattern. It is correct in isolation and should land *after* option 1 or 2 —
  filed as the follow-up it now is, rather than the one-line config win it looked like.

## The through-line

Three findings in one day, each one level above the last:

1. Verify against the documents you changed → **missed** a regression in the ones you didn't.
2. Verify against every document → **missed** a defect visible only in the pair.
3. Verify against every pair → still cannot see whether a *series* owns the document it is being
   diffed against. That one is B1, and it is still open.

Each layer was invisible from inside the one below it.
