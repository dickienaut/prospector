# The rev15 / rev8 fold — build note (2026-07-16)

*Build note for Claude Code. Folds the build spec **rev14 (2026-07-08) → rev15** and the state-of-project doc
**rev7 (2026-07-11) → rev8**. This is the build seat's first fold — the design seat ran the prior ones — so
this note is the **procedure**, not just the scope. **Two docs, two rules, two PRs.** They look like one job
and they are not.*

---

## 0. The one thing that matters

**Fold what was RATIFIED, not what was BUILT.** The worklist is `docs/decisions/`. It is not the code.

Everything else in this note is downstream of that sentence. If rev15 is written by reading the
implementation, the spec becomes a **description of the code** instead of a **contract that constrains it** —
and a spec that describes the code can never catch drift, because drift *is* the code disagreeing with the
contract. The inversion is silent and permanent; nothing downstream would ever reveal it.

It is also **author-reviewing-author, one layer up.** You implemented most of what landed since rev14. "The
spec now says what I built" is the founding failure wearing a spec's clothes.

So: **every clause you change traces to a decision record. Anything that doesn't trace is a FINDING, not a
spec update.** See §5 — that's the fold's real product.

## 1. Two docs, two rules

Per `CLAUDE.md`'s canonical-docs rule:

- **The spec — pure amend.** Surgical diff: alter *only* the clauses a recorded decision changed; every other
  byte preserved verbatim. Wholesale rewrite forbidden. A clause is superseded **in place with the change
  recorded**, never silently dropped.
- **The state doc — the partial exception.** Parts I–IV follow the amend rule (carried forward, not
  rewritten); **Part V is re-synthesized** — a snapshot of *now*, not a contract. Rev 7 did exactly this.
- **The escape valve exists; do not reach for it.** A consolidation rewrite is permitted *only* with a
  clause-by-clause diff proving no unintended contract changed. That valve is for patchwork traps, not for a
  week of targeted amendments. Wanting it here is a signal to stop and ask.
- **Two PRs.** Different rules, different failure modes, different review surfaces. Fused, one review covers
  two disciplines and neither gets read properly. **Spec first** — rev8 names rev15.

## 2. Method — the spec

1. **Enumerate.** `ls docs/decisions/`, filtered to records dated after **2026-07-08**. That set is the
   worklist. **Enumeration, not recall** — completeness is the fold's entire value, and completeness cannot be
   reached by remembering.
2. **Classify every record.** Most will **not** touch the spec: the reorg, doc-naming, CI/branch-protection,
   branch-off-fresh-main, the worktree/deploy topology, the identity split, the canonical-docs rule itself —
   those are **process** decisions that amend `CLAUDE.md`, not the build spec. Only records that changed
   **CONTRACT text** fold into rev15. **Write the classification down** — it is the evidence for step 4 and it
   goes in the PR body.
3. **Amend, one § at a time.** Smallest edit to the affected section that makes the spec state the *current*
   contract, plus **a changelog line naming the delta and its decision-record path.** The changelog is not
   decoration — the rule requires it, and a changelog that under-reports its own changes is the same class of
   defect as an un-anchored claim.
4. **Run the check — this one is yours by rule.** `CLAUDE.md`: *"Before writing a canonical doc: diff against
   the prior version and confirm every changed clause traces to a decision record."* Diff rev15 against rev14;
   for each changed hunk, name the record. Anything unaccounted for → §5.
5. **File it.** New dated file `docs/prospector-v1-spec-rev15-2026-07-16.md`; **rev14 moves to
   `docs/history/`** — a rev-bump is a new dated file with the prior *relocated*, never a rename in place.
   Then fix the pointers: `CLAUDE.md`'s opening line names the canonical spec, and `ARCHITECTURE.md` and the
   state doc reference it. Grep `rev14` / `rev-14` and fix what resolves.

## 3. Method — the state doc

1. **Parts I–IV: carry them verbatim.** *Copy the bytes.* Do not retype, and do not clean up while you're in
   there. A retyped Part I is a wholesale rewrite that happens to look similar — and the drift is invisible
   *precisely because there is no diff to check*, which is the rule's own stated reason for existing. If a
   decision record genuinely changed something in I–IV (**§2.9 "What is deferred"** is the usual one), that's
   an amendment with a changelog line, same as the spec.
2. **Part V: re-synthesize.** Rev 7's shape is the template: **5.1** where the arc stands · **5.2** status by
   register — BUILT / QUEUED / DEFERRED (named, with reason) / ASPIRATIONAL (v2, walled off), *the single
   source of truth for what's built*, which is the discipline that stops the doc over- or under-claiming ·
   **5.3** next steps, prioritized · and the **load-bearing honesty line** closing 5.2.
3. **The framing rev8 must land** (judgment — the design seat will sharpen it, but draft toward it):
   **build-complete is a finish line *and* a starting line.** What finished is the **instrument**. The
   false-discovery rate is unmeasured, dispersion is n=1, flow-vs-structure is open — and none of those
   resolve by building. Part V should read *the instrument is done; the measurement hasn't started*, not as a
   victory lap.
4. **File it.** New dated file; **rev7 → `docs/history/`**.

## 4. Named failure modes

- **Regeneration disguised as amendment.** A week of deltas makes *"let me just rewrite this section
  cleanly"* feel efficient. It is the forbidden thing, and it's forbidden *because* the drift it creates is
  undetectable.
- **Folding built-not-ratified.** §0. The inversion.
- **Retyping Parts I–IV.** §3.1.
- **A changelog that under-reports its own delta.** `METHOD.md` hit this yesterday — a substantive addition
  landed without a changelog line, caught on review. Same class as an un-anchored claim.
- **Recall instead of enumeration.** A worklist from memory of the arc is missing records, and you won't know
  which ones.

## 5. The drift audit — the fold's real product

Every clause that doesn't trace is exactly one of two things:

- **An unrecorded decision** → **write the record.** Decision records are append-only and *freely authored*
  (explicitly NOT bound by amend-never-regenerate), so this is cheap. Then the clause traces.
- **Actual drift** → **a register row.** The code does something nobody ratified.

**This is the one moment you get a systematic drift audit for free.** Every other week, drift is found by
accident; here, the check the rule mandates *is* an audit — it walks the whole contract surface against the
whole decision trail. Don't spend that on transcription. **If the fold produces zero findings, be
suspicious**: either the arc was unusually clean, or the check wasn't adversarial.

## 6. Acceptance & review

- Full suite green — docs-only PRs still ride the gate.
- **The §2.2 classification table goes in the PR body:** record → folds / doesn't-fold → which §. That's what
  makes the review *checkable* rather than a re-read.
- **Design reviews against the records directly.** As of the 2026-07-16 sync the design seat can read
  `docs/decisions/` verbatim, so its review checks each clause against the record itself, not against your
  account of it. **Paste the enumeration with the PR** — if a record in the list isn't in the fold, that's the
  catch.
- **Cross-check — a second witness, NOT a worklist.** The design seat's recollection of this arc's *likely*
  CONTRACT deltas: §10 (the sender; the stable `(subsystem, key)` fault signature; the §8a advisory-posture) ·
  §9e (dispersion live + constituent symbol resolution) · §8b (the export) · §4d (rebalance runner-wiring) ·
  §6 (capture + budget guard + the byte-exact `query_drift` ruling) · §7/§9 (the single-writer lock; store
  durability/backup) · the merged-config hash · §10's fault-taxonomy home (PAGE-WORTHY-MIRROR).
  **This list is unverified and must not become the worklist.** Enumerate first, *then* compare. A mismatch in
  either direction is a signal: if the enumeration lacks something here, either the design seat is wrong or a
  record is missing — and both are worth knowing.
- **QA optional.** Its skill is branch-QA (baseline, RED/GREEN, findings PR) and a docs fold has no RED test,
  so a standard dispatch would be shaped wrong. If you want the cold read, the ask is different — *verify the
  enumeration's completeness and each clause's trace* — and that procedure doesn't exist yet.

---

*Sequencing note: the `CLAUDE.md` Development-clause amendment (rule 2: posture → mechanism) and its decision
record are **independent of this fold** and unblock `METHOD.md`. They do not wait on rev15. If they aren't
already in flight, do them first — they're small, and something is currently blocked behind them.*
