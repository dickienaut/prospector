# The bug archive becomes a retrieval system — doctrine/register split, two-axis tags, status-as-column

*Decision record, 2026-07-14. Owner-initiated, ratified across three seats (design set the goal and gave it
structure; QA/build ground-checked it against the artifact; two corrections folded in). Extends
[`2026-07-11-bug-fix-archive.md`](2026-07-11-bug-fix-archive.md) — the archive it created now gets an explicit
**job** and a shape that serves it.*

## The reframe (the goal that drove everything)

The archive's real job, in the owner's words: **a living record that is easy to search and surfaces bugs that
correlate with what we're working on** — the **first stop for every bug hunt**, where a *miss* means we are in
genuinely new territory and can reason from first principles instead of a stale prior. That single goal —
*a miss must be trustworthy* — is what forced each ruling below. The 2026-07-11 archive had the right content
(classes, index, records) but four properties worked against retrieval: doctrine and register were **fused**
in one file (so logging a bug edited the governance doc — class-9 drift aimed at the archive itself), rows
weren't **grep-able by what you'd actually search**, statuses had **drifted** (SNAP-01/R1/R4 read "patch
drafted" though they merged via #55), and the register was **incomplete** (BK/CAP/R/M7 findings lived only in
`notes/`). An incomplete or fused register can't support "a miss = novelty."

## The rulings

1. **Split doctrine from register.** [`bugs/README.md`](../bugs/README.md) is now **doctrine only** — the §1
   meta-bug classes, the boundary rules, the §4 record template, the §5 tag vocabulary, the §6 how-to. It
   changes only when the *system* changes. [`bugs/INDEX.md`](../bugs/INDEX.md) is the **register** — one row
   per bug, appended every slice. Logging a bug now touches the volatile file, never the doctrine. The §2/§3
   numbers were **relocated byte-preserved into `INDEX.md`, not renumbered** (stable IDs, like the class
   numbers) so any fossil's "§2"/"§3" reference still resolves.

2. **Distilled, not resolved — status is a column, not a gate.** The register holds *every distilled bug*
   whatever its status; `⭕ open`, `💤 deferred`, `🟡 partial` rows **stay**. A known-unfixed bug in the
   subsystem you're touching is the **highest-value hit there is**, and a register that hid open bugs could
   never make a miss mean novelty. *(This was a build-seat correction to an earlier "closed-only" instinct —
   grounded in the artifact: 13 of the register's rows are non-closed, and multi-finding reviews close
   asynchronously.)*

3. **Distill-not-relocate — the `notes/` review is never moved.** A finding **graduates** from a `notes/`
   review into the register by being **distilled** (root-caused, classed, tagged) into a row — and, if it
   earns one, a `bugs/qa/` record — **not by being relocated.** The multi-finding review stays whole in
   `notes/` (its findings close at different times; moving it would tear a live document) and the record links
   *back* to it; the review is never edited to point forward. *(Second build-seat correction, also grounded:
   the M6 deep-review note holds 15 findings that landed across four different PRs.)*

4. **The finding-vs-bug boundary.** A raw "looks off, unverified" observation in a `notes/` review is **not a
   register row** — it becomes one only once **root-caused** (a named cause at `file:line`, a class, a
   reproduction). That threshold is precisely what makes a register miss meaningful. *(This answers the owner's
   standing question — "do the QA findings I dropped in `notes/` belong in `bugs/`?": the review belongs in
   `notes/`; its root-caused defects belong, distilled, in the register. The review stays; the bug graduates.)*

5. **Two controlled tag axes — subsystem · shape.** Every row carries a **Subsystem** tag (*where it bit*:
   `backup`, `rebalance`, `heartbeat`, …) and a **Shape** tag (*how it failed*: `spurious-fire`, `fail-silent`,
   `green-on-synthetic`, …). You grep one axis ("show me every `backup` bug") or the other ("where else has a
   `spurious-fire` alarm bitten"). The **Shape axis is the §1a taggable classes made searchable**
   (`green-on-synthetic`=1, `invariant-in-prose`=3, `spurious-fire`=7, …), so a grep cross-cuts a class across
   every subsystem. The vocabulary is **controlled** (fixed word-list in README §5) so a synonym can't become a
   silent miss; it extends deliberately, the same discipline as the class numbers.

6. **`bugs/qa/` for the per-bug records.** The distilled records move under `bugs/qa/` (the QA-authored corner);
   the register and doctrine sit at `bugs/` root. The four existing records `git mv`'d there together so their
   cross-links resolve.

7. **The two-author handoff, baked in (README §6).** QA authors the Problem (a row, plus a record if it earns
   one) when a finding is root-caused; build adds the Fix and flips the status **on merge, in the same change**.
   **A fix is not done until its `INDEX.md` row is current** — the same gate as "a fix needs a guarding test."
   This is the mechanism that stops the class-9-aimed-at-the-archive drift that #55's stale statuses displayed.

## Completing the register (the same-day dogfood)

To make "a miss = novelty" true *now*, the register was completed in this change: rows added for every
distilled M6 finding that lived only in `notes/` — **BK-1/BK-2** (✅ #56), **BK-3** (💤, decision #57),
**R2/R3**, **CAP-DRIFT/CAP-USD**, **M7-02** (💤, decision #57), **M7-04/M7-05/M7-06**, **GI-01** (✅ verified
gitignored) — and the drifted **SNAP-01/R1/R4** flipped to **✅ #55**, **M7-05** marked swept-by-M7-01 (#58).
The next build, **M7-02** (backup-health → the weekly email), will be the first bug authored end-to-end under
§6 — the real dogfood.

## The one documented fossil-drift (relocate-never-rename's accepted cost)

Moving the four records into `bugs/qa/` leaves exactly **one** dangling reference:
[`2026-07-11-bug-fix-archive.md`](2026-07-11-bug-fix-archive.md) §3 names
`2026-07-10-email-volatile-fault-suppression.md` as its "first worked example." That decision record is an
**immutable fossil** — it is *not* edited to point at the new path (that would be changing the past, the exact
thing relocate-never-rename forbids). The reference is a **bare filename**, not a relative link, so it still
resolves by search — the file exists, now under `qa/`. This is the same accepted, **documented** cost the
docs-reorg recorded: relocate keeps ~99% of references resolvable by name; the residue is logged here rather
than hidden. One bare-filename reference in one fossil is the whole drift.

## Relationship to the doc-discipline rules

Same lineage as the parent: born-dated records
([`2026-07-11-doc-naming-convention.md`](2026-07-11-doc-naming-convention.md)), amend-in-place for
`README.md`/`INDEX.md` ([`2026-07-11-canonical-docs-amended-not-regenerated.md`](2026-07-11-canonical-docs-amended-not-regenerated.md)),
and index-don't-move for the `notes/` reviews
([`2026-07-11-docs-reorganization.md`](2026-07-11-docs-reorganization.md)). Fittingly, the archive that tracks
how rules are born from bugs is itself reshaped by applying those rules — and the discipline that keeps it
honest (§6's status gate) was written down because the archive's *own* record drifted (class 9) between finding
and fix.
