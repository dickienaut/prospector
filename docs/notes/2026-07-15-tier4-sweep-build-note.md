# Tier-4 sweep — closing the low-severity tail (2026-07-15)

*Build note for Claude Code. One batched PR closing the register's low-severity open set, so v1 is
**free-standing** — every row ✅ or explicitly-parked-by-decision, nothing left half-decided — before v2 work
begins. Thirteen small items. The efficiency premise: per-item process overhead would exceed the fixes, so
they batch; the honesty premise: **a forced fix is not a close** — if an item proves not-a-defect on cold
read, disposition it (GI-01 precedent: ✅ verified-not-a-defect, class `judgment`) rather than patching for
green.*

## Ground rules (apply to every item)

1. **Primary source first.** Each item's full finding lives in the source review doc named on its register
   row (mostly `notes/prospector_full_review_claude_science.md`). Read the finding before touching the code —
   the register row is the pointer, not the spec. The six smells especially: this note deliberately does not
   restate their mechanics; re-derive from the review.
2. **Minimal fix + violation test, per item.** Tier-4 means smallest change that closes the row. No drive-by
   refactors, no "while I'm in here" — the sweep's scope discipline is per-item, and the temptation to clean
   adjacent code is exactly how a one-day sweep becomes a week.
3. **Commit-per-item, ID in the message** (`H2: freeze real xlsx with .xlsx ext`, `S3: fullmatch …`). The
   merge-commit history then maps 1:1 to register rows — the trail is the point.
4. **Preserve the fail-loud direction.** Several fixes widen acceptance (H3, H4). Widening must never convert
   a loud fault into a silent misparse — each acceptance-widening item carries a **negative test** proving a
   genuinely-unknown input still faults. This is the one real design line in the sweep (see H3).
5. **Register flips ride in the same PR.** A fix isn't done until its row is current (the maintenance gate).

## The items

**H2 — real xlsx frozen as `.csv`** (ingest·holdings). Fix at the freeze site: `ext="xlsx"` for xlsx payloads.
**Forward-only** — existing misnamed fossils are immutable and stay as-is (relocate-never-rename applies to
the store too); confirm the reader still handles the legacy `.csv`-named xlsx files. Tests: a real-xlsx
payload freezes with the right extension; a legacy misnamed fossil still reads.

**H3 — `"Weight (%)"` header variant faults** (ingest·holdings). Widen the header match (prefix/contains per
the row) to accept the *known-real* variants — and no further. **The negative test is mandatory:** a
genuinely alien header must still fault to manual review. Trading the loud `no holdings header` fault for a
silent misparse of an unrecognized layout would be a severity inversion — worse than the bug. Accept what's
been seen; keep faulting on what hasn't.

**H4 — plain `REAL ESTATE INVESTMENT TRUSTS` header** (ingest·soi). Row re-scoped synthetic-only; the fix is
a one-line `gics_industry_alias` entry. Confirm the scope from the finding: if real filings can carry the
plain header, add the alias (test: plain header rolls up, no fault); if truly synthetic-only, adding it is
still cheap robustness — lean add, but a verified-synthetic-only disposition is acceptable.

**S3 — `^…$` regex admits trailing `\n`** (store). Switch to `\Z` / `re.fullmatch`. This *tightens*
validation, which is the right direction — but check blast radius first: scan the store for any existing
name/value that passed under `$` and would now fail (unlikely; verify, don't assume). Test: trailing-newline
input rejected.

**S5 — pandas NaN sector becomes `"nan"`** (ingest·soi). `pd.isna` guard before any str-cast. A NaN sector
routes to the **existing unparseable/fault path** (honest, manual review) — never a `"nan"` bucket, never a
silent drop. Follow the 9e precedent: exclusion is loud and counted. Test: a NaN-sector row produces the
fault/exclusion, and no `"nan"` key exists anywhere downstream.

**report.py — empty `acute_crises` → `IndexError`** (backtest). The row's hint is `or [{}]`; re-derive the
cleaner minimal fix from the call site (guarding the access / skipping the section on empty is likely
righter than a placeholder dict). Test: report generation over a backtest with zero crises succeeds and
renders sanely.

**The six smells — lag-lexical-sort · eigengap · token-substring · sql-assert · edgar-`matches[0]` ·
ledger-datesort** (various). Deliberately not specced here — the review doc holds each one's mechanics.
For each: read the finding, then **fix or disposition**. Expected shapes from the names (verify against the
source, do not trust this line): lexical-vs-chronological sort bugs get a typed sort key + a test with an
order that lexical sorting would scramble; `matches[0]`-style first-pick gets the I1 treatment (disambiguate
or fault, never silently pick); `assert` used for runtime control flow becomes a real raise (`-O` strips
asserts); substring token matching gets an anchored match + a false-positive test. Any smell that reads as
sound on the real substrate → GI-01-style disposition with one line of why.

**BK-MSG-01 — backup's broad `except` mislabels non-drive faults** (backup). Narrow the label, not the
catch: keep the catch-all (best-effort-but-loud stands), but only attach the *"retry once the drive is
healthy"* hint to drive-shaped errors (OSError family); anything else gets a generic mid-copy failure
message carrying the actual exception class + text. Test: a non-OSError mid-copy fault surfaces its real
error, not the drive hint.

## Riders (register/record work in the same PR)

- **BK-READ-01 flip** — design-thread ruling: **accept and document** (correctness over cost at current
  scale — the re-read runs post-tick when nothing waits, seconds on a single-digit-GB store). Flip to
  🟡 ratified-residual with a mini decision record naming the revisit trigger: backup wall-time exceeding
  ~a minute, or store growth making the re-read minutes-long. **Override condition:** if QA's #64
  reproduction shows amplification materially worse than seconds today, it comes back to the design thread
  instead — measurement beats the ruling.
- **Row flips for every item above**, each linking its commit and test (or its disposition line).

## Explicitly not in scope

- **Doc debt (DRIFT-1/2, C.2)** — rides the rev15 spec-fold session, not this sweep (one "record matches
  territory" pass, done together).
- **The 💤 set (N9, E2, BK-3)** and the **🟡 residuals (B1/B2, R3)** — parked by decision, tripwired by
  xfail or named deferral. They are *closed as decisions*; un-parking them to green the board is exactly the
  completionism this sweep is not.

## Sequencing & acceptance

Branch off fresh `origin/main` now — the sweep touches ingest/store/backtest/backup-messages and is
independent of the two in-flight PRs (the stacked CAP/DASH set and the M7-04/06 lock); the ruleset's
up-to-date-before-merge handles any ordering if they land first. One PR, commit-per-item; full suite green
through the CI gate; **one QA dispatch over the branch** (the batch is the efficiency); owner reviews and
merges. After this + the rev15/doc pass, the register's live tail is: in-flight items, the capture-arming
gate, and the deliberately-parked set — v1 free-standing.
