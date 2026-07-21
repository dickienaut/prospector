# CLAUDE.md consolidation — the reconciled read (for ratification)

*2026-07-21. Reconciles the three independent reads — Design (07-16, 277-line doc), Build (07-20 @ `c8d2d42`,
299 lines, extended by its two orphan-sort notes), QA (07-21 @ main `a8010d61`, live repo) — into one
document the owner ratifies and Build executes as a traced diff. **This document is the spec for the rewrite;
the diff is checked against it, and deviations during execution come back as findings, not judgment calls.***

*Consolidator's corrections — two findings in the input set were superseded and are carried here in corrected
form: **(1)** Build-findings §2 reported `gics_industry_sector` resolving nowhere in the spec; Build's own
later orphan-sort **retracted** this (it resolves at `spec.md:37`, stated more precisely than CLAUDE.md — the
original probe grepped the config key, not the contract's words). Classification: **B — duplicate, delete.**
**(2)** The orphan-sort's "disable squash" recommendation is **already landed** (QA verified
`allow_squash_merge: false` at `a8010d61`); it appears below as a settled fact, not a to-do.*

---

## 1. The reconciled diagnosis (unanimous, now measured)

**Delete-and-point, not fold-then-delete.** Build probed 36 contract-bearing clauses: 32 resolve in the spec,
3 are constitutional (stay), **1** is a true partial (NPORT-P), **0** are genuine orphans. QA independently
re-ran the partial-hunt against full spec sections and confirmed the floor: **NPORT-P is the only Category D.**
The spec already carries the contracts; CLAUDE.md holds echoes. The consolidation is therefore *smaller and
safer than any seat expected*: one spec amendment, deletions-with-pointers, structural cleanup, honest
tiering, and a bounded set of additions.

**Length was the wrong target throughout.** The defects are second homes (C-1, C-2), missing rules (§5), and
overclaimed enforcement (§4). The additions below will partly offset the deletions — that is correct, not a
failure of the exercise.

## 2. Preconditions — land BEFORE or WITH the consolidation, as their own PRs

- **P-1 · The firewall package-wide sweep (the exercise's one mechanism change).** QA planted a
  `portfolio.yaml` read in `sensors/soi.py` (un-allowlisted): **both firewall tests passed — CI green on the
  forbidden read.** The wall is an allowlist over 6 of 54 modules. The fix-template already ships in-tree:
  `tests/test_capture.py::test_never_read_wall…` sweeps `rglob("*.py")` over the whole package and **fails
  correctly** on the same plant. Copy that shape for `portfolio.yaml` **and add the detector-bucket term**
  (currently zero enforcement of any kind). *Sequencing is the point: the sweep lands before the constitution
  writes "enforced," so the doc's strongest claim is true when written, not aspirational.*
- **P-2 · The spec §3b delta (the one Category-D fold).** Amend `spec.md:67` to carry the hazard — *"never
  filled with survivor-biased data"* — then the CLAUDE.md line deletes. One sentence, spec rev bump, traced.
- **P-3 · Verify "Update with rebase" survived.** QA verified `allow_rebase_merge: false` (part of the
  append-only win). The July git-strategy ruling kept rebase-merging **deliberately enabled** because GitHub's
  Update-with-rebase button (the back-merge-noise fix) requires it. **Check a behind-branch PR for the button.**
  If it's gone, that's a regression the squash win silently bought — decide knowingly (re-enable
  rebase-merging at the repo level while the ruleset's `allowed_merge_methods` still restricts what lands on
  main, per the original two-layer ruling) rather than discover it at the next stacked PR. *Flagged, not
  ruled — a UI check no seat can run.*
- **B-2 rider · `.github/CODEOWNERS`** cites the superseded `2026-07-12` merge record — repoint to
  `2026-07-16-agent-identity-split-and-merge-gate.md` in whichever PR touches it first.

## 3. The CLAUDE.md edit list

### 3a. Deletions (each with its anchor — the diff must show the pointer, not a bare removal)

- **C-1 · The opening spec-rev narrative — the highest-value single edit, now measured twice.** The pointer
  drifted rev14→15 (Design), was still stale at rev 16 four days later (Build B-1), and remains uncorrected
  today (QA Q-1). Replace with a **version-free pointer**: *"The canonical spec is `docs/spec.md`; read its
  header for the current rev; earlier revs in `docs/history/`."* The rev narrative deletes whole — its five
  embedded CONTRACT claims all resolve (mandate-prior `:51/:233/:350` · forward-hash ×6 · `sectors_unresolved`
  ×6 · `prospectus_accession` ×4 · **gics rollup `:37`**, per the corrected finding). The narrative's
  historical *attributions* were never verified and are moot on deletion.
- **C-2 · CONTRACT-vs-DEFAULT compresses to imperative + record path.** The ~80 lines of decision-record
  summaries reduce per-entry to the operative constraint (one–two lines) plus its `decisions/` path. **The
  compression rule that governs every entry: drop the narrative around the imperative, never the imperative.
  If a "never X" loses its "never," the consolidation has failed regardless of how it reads.**
- **The 32 Category-B rows** delete with pointers. QA's full-section re-read stands as the second read
  licensing them (series-ids, proto-cluster wall, macro both-directions all verified **verbatim** in the
  spec — Design's "reads like hedging; it isn't" clause is faithfully carried, both scars).

### 3b. Structure (moves, not edits — the diff shows relocation)

- **C-3** · One `## The record` heading over the three doc-rule sections.
- **C-5** · `## Identity` → `## Fund identity` (the machine-account identity now also lives in the doc).
- **C-6 + Build §6** · The five-line header map (*operative here · why → METHOD.md · contract → spec · scars
  → docs/bugs · this file wins on disagreement*) **plus a ToC of section names only.** The rejected
  alternative is recorded so the next person doesn't rebuild it: **no "index of every NEVER"** — it either
  restates the imperatives (a second home) or degrades into a pointer list with maintenance cost and no
  reader value.

### 3c. Honest tiering (the firewall ledger — final, QA-verified form)

State the clauses with their true tiers, per METHOD.md rule #3's per-seat-ledger pattern. **Post-P-1** the
table the constitution carries is:

| clause | enforcement (verified) | tier |
|---|---|---|
| never read `portfolio.yaml` | package-wide sweep (P-1) | **mechanism** *(pre-P-1: a 6/54 allowlist, proven not to bite)* |
| never read the detector's bucket | P-1 sweep term (in-repo) + separate repo (no import path) | **mechanism (in-repo) + architecture** |
| never place / size a trade | capability absence — no broker credentials, no reachable portfolio | **mechanism-adjacent** |
| never **recommend** a trade | **nothing — and correctly so** (you cannot test the absence of a recommendation) | **prose — the clause closest to the real risk: this system talks an operator into a trade long before it places one** |

Also tiered where the doc currently implies uniformity (QA §4): offline-tests/network-guard, append-only,
ticker-rejection, tag-only deploy = **mechanism**; no-run-now, no-auto-tune = **prose by design** (the point
of no-auto-tune is that the human is the only mover); `config.changed` ordering = **assumed, unguarded** (see
§6).

### 3d. Additions (Category E — missing operative rules, grouped so the doc doesn't re-bloat)

*Twelve candidates from the three reads compress into five clusters. Every addition obeys 3a's own register
discipline — imperative + record/anchor path, no restated reasoning (that is METHOD.md's job).*

1. **The seats (M-1 + M-6).** QA exists; findings arrive as `qa/*` PRs; **Option-2 composition** (QA proposes
   RED test + reference patch; Code applies with an independent read; `xfail(strict)` handoff). Who does
   what; what each seat must not do. The operative subset only.
2. **Verification (M-3 + M-4 + B-M1 + B-M3 + B-M4).** Every fix ships the violation test that would have
   caught it · **prove the gate bites** (a gate that has never rejected is observationally identical to no
   gate) · verify against the unit the system *acts* on, not the unit you changed · a fixture must reproduce
   the pre-fix failure · the deploy is not the proof, the tick is — record the null, name the retest.
   *(B-M2 rides as one capability sentence: the frozen substrate makes whole-corpus replay nearly free, so
   parser changes are expected to be corpus-checked.)*
3. **The register (M-2).** A fix isn't done until its `docs/bugs/INDEX.md` row is current.
4. **The record (M-5 — now mechanism).** Merge commits, never squash; verified `allow_squash_merge: false`.
   One sentence, stated as the wall it now is.
5. **Sensor conduct (B-M5) + Development (B-M6).** Mark what you cannot attribute — never suppress, never
   emit as clean · production deploys from a tag by mechanism (`deploy.sh` refuses non-tags, takes the
   single-writer lock).

## 4. The protected-list check (the diff's acceptance test)

Post-consolidation, **every clause on Design §4's scar-tissue list must be shown present in exactly one
canonical home** — the spec (with CLAUDE.md pointing) or CLAUDE.md (constitutional). **The one deliberate
exception, stated in the doc:** the Firewall is duplicated in both, whole, on purpose — it is the
constitution's reason for existing. Any protected clause absent from both homes fails the diff, full stop.

## 5. The suite baseline the status claims key off

**685 passed · 1 skipped · 2 xfailed** at `a8010d61`. QA's "1 failed" is an environment artifact (its tarball
baseline never installed the package, so the lock test's subprocess couldn't import `prospector`; green in
CI, which does). Recorded so nobody re-investigates a scary number that means "the harness skipped a step."

## 6. Open items (named, not blocking)

- **IAM policy** — owner-only, uncheckable by any seat. Established *not currently load-bearing*
  (`s3.bucket: null`, boto3 lazily imported) — the S3 half of the firewall rests on capability-absence today.
- **`config.changed` strict ordering** — "before any sensor" has no ordering test. Cheap candidate; until it
  exists the doc must not state it as mechanism.
- **Completeness bounds** — each seat named its own: Design cannot enumerate; Build's 36 probes are a probe-set
  property; QA's D-hunt read four sections past the screen. The floor (one D) is a floor, not a proof.

## 7. Execution order & the diff protocol

1. **P-1** (sweep PR) → **P-2** (spec §3b, rev bump) → **P-3/B-2** checks/riders.
2. **The consolidation rev**, cut against **fresh main at execution time** — re-verify the volatile items at
   cut (the spec pointer, the repo merge-method flags; three reads at three repo states is the lesson).
3. **Diff protocol:** every deletion names its spec anchor · every addition names its record · every
   protected clause passes §4 · the changelog entry cites this document. Owner reviews the diff *against this
   list*, not against taste.
4. **QA post-check:** one cold pass over the merged result — the protected-list sweep and a re-plant of the
   §1 violation (which must now fail).

## 8. Why the three-read structure earned its cost (the meta-record)

The convergences were cheap; the divergences were the value, exactly as predicted: the firewall climbed three
orders of evidence (inferred tier → allowlist count → **demonstrated not to bite**); the squash state flipped
under the reads and only a live check caught it; the gics finding was retracted by its own author's deeper
probe, and the retraction — not the finding — is what ratifies. QA flagged its own D-hunt as
*not-independent* (a second read licensing deletions, not a second opinion). One prediction failed usefully:
no seat found a genuine orphan, which means the folds have been happening all along — the audit's finding is
about CLAUDE.md's echoes, not the spec's gaps.
