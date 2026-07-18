# Status truth stays PROSE in ONE home — no machine-readable status source

*Decision record, 2026-07-17. Ratifies the design-thread ruling on the build-seat proposal for a
`docs/status.yaml` (milestone → `built | deferred | aspirational` + arming-state) plus a CI check that greps
the canonical docs' status claims and fails on contradiction. **The proposal is rejected.** Accepted instead:
**one home, three pointers** for doc-vs-doc, **discipline** for doc-vs-code, and a **cited-anchor gate** as the
only mechanical thing worth building. Governing: `METHOD.md` rules #5 and #3; the bug-archive doctrine's
process-only-under-real-pain rule. Prompted by **M6-CAPTURE-DRIFT** (a stale `README.md` line laundered through
two folds).*

## Context — the problem is real; the proposed fix is not

Build status has **four homes**: `docs/state.md` §5.2 (which titles itself *"the single source of truth for
what's built"*), the spec's §9 build-status, `ARCHITECTURE.md`'s milestone list, and `README.md`. They have
been observed disagreeing **in opposite directions simultaneously** — on M6, ARCHITECTURE was right and §5.2
wrong; on M7, §5.2 was right and ARCHITECTURE wrong — with no arbiter. That is why M6-CAPTURE-DRIFT survived:
it was **falsifiable by reading two docs on `main`**, and nothing cross-checks docs against each other.

The build seat proposed mechanizing status truth: a machine-readable source, docs citing it instead of
re-asserting prose, and a CI check failing on contradiction. The instinct is right — rule #5 says a recurring
failure gets a mechanism, not vigilance. The mechanism is wrong, on four independent grounds.

## Decision — rejected, for four reasons, each sufficient

**1. It is `provenance_stamp` before `reviewed_sha` — the anti-pattern QA already had to unwind.** A green
`m6: built` proves a **doc-token equals a YAML-token**. It vouches for *nothing* about whether M6 is built.
Presence enforced, truth not — the un-anchored claim wearing a receipt. Worse: the entry's actual value is the
rider (*"ships disabled; the owner arms it by setting `capture.monthly_budget_usd` + `ANTHROPIC_API_KEY`,
behind the one-time CAP-DRIFT armed byte-compare"*), which sits **above the token, unchecked**. A green check
above a wrong arming path is worse than no check.

**And the check would have missed the bug that motivated it.** The M6 drift read **"front-loaded to v2."** No
grep pattern for "deferred" matches that string. It catches the phrasings you thought of and misses the one
that happened — green-on-synthetic, aimed at the status registers.

**2. No binding is available.** QA fixed its stamp by tying it to a **fact**: the fetched commit. *"Is M6
built"* is not a fact in the repo. What is in the repo: `capture.py` exists, `_run_capture` is wired,
`test_capture.py` passes. Whether that **constitutes M6** is a **judgment against spec §6**. So the derivation
needs a hand-written milestone→evidence mapping — prose in YAML, drift-capable, in a file nobody reads. The
drift relocates; it does not die.

**3. It misapplies PAGE-WORTHY-MIRROR at the joint that made it work.** That fix worked because `import` means
**one artifact** — consumers hold no copies, so drift stops being *representable*. Explicitly, that record:
**"no agreement test by design… the structure is the guard."** "Generate-from" or "CI-check-against" leaves
four prose registers **plus** a YAML **plus** a synchronizer: **five homes and a checker**, when the lesson was
**fewer homes**.

**4. No pain, and the register is about to freeze.** The class has fired **three times** — M6, ARCHITECTURE's
drift, the state-doc-lagging-code instance `METHOD.md` already cites — and been caught **three for three**,
within a day, by a seat that didn't write the artifact, with **zero damage**. By the archive's own rule (*grow
the record freely, add process only under real recurring pain*), that is the mechanism **working**, not pain.
And the drift happened during the most volatile month this project will ever have — 28 decision records, every
milestone moving. **v1 is build-complete.** Remaining status changes: M6 arming, dispersion promotion, v2.
Roughly three events. A tool + a mapping + a CI check + marked tokens in four docs, maintained for twenty
years, to guard three events the cross-seat read already catches for free, is **process without pain**.

## What is accepted instead

- **One home, three pointers.** `docs/state.md` §5.2 is the status register; `ARCHITECTURE.md`, `README.md`,
  and the spec **point at it** rather than restating it. **Doc-vs-doc dies completely** — there is no second
  home left to contradict. The division already exists in prose: `state.md`'s own header calls the spec *"the
  canonical build instructions, of which this doc is the orientation/status/roadmap synthesis"* — so the
  spec's §9 carrying build status is **the spec doing the state doc's job**. This is a **deletion**, not a
  gate: nothing to sync, nothing to check, no machine to maintain for twenty years.
- **Doc-vs-code stays discipline**, honestly named in `METHOD.md`'s rule-3 per-seat ledger, where a seat that
  didn't write the register has caught it three-for-three. It is **not** claimed as a wall.
- **The one mechanical thing worth building: a cited-anchor gate.** Every `decisions/*.md` path and every SHA
  referenced in a doc must **resolve**. Pattern-free, general, and it is *"every durable claim is tied to
  something outside the narrative"* made into a gate. It would have caught the design seat's **two** dangling
  forward-references this week (`2026-07-16-rule-2-gate-enforced.md`, cited before it existed; and the
  consolidation findings doc, cited in a handoff while it sat outside the repo). It proves the **anchor** is
  real, not the claim — exactly as far as a machine can honestly go on a judgment claim.

## The generalizable lesson (why this record exists)

**A rejected mechanism is the decision most likely to be re-proposed.** Nothing in the repo argues against a
status linter; the next build seat reaches for one cold, from the trenches, with the same good instinct, and
the whole argument re-runs from zero. **That is what this record is for.** The build seat captured the lesson
as a skill (`mechanism-bias-run-the-pain-test`) — this is its decision-trail anchor.

**The scope line, because a disposition without its boundary becomes a wrong precedent:** the pain test applies
where the failure is **recoverable** — doc drift, where a miss costs one PR. Where the failure is
**irreversible**, you mechanize **before** the pain, and *"it hasn't bitten yet"* is the argument you ignore.
This project already knows that: **the backup predates the loss, the never-execute wall predates the trade,
the dead-man predates the silence.**

## Scope / what did NOT change

No code. No existing gate weakened. The four-homes defect stands **open** until the one-home consolidation
lands (it belongs to the `CLAUDE.md` consolidation work, not here). This record settles only that the fix is a
**deletion, not a checker**.
