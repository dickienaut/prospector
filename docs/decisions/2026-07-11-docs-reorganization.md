# Docs reorganized into a kind-based folder taxonomy

*Decision record, 2026-07-11. Owner-directed reorganization of `docs/`, which had grown to 42 files flat at
the top level. A **content-preserving relocation** — every move is a `git mv` with byte-identical content; no
clause of any bound document was rewritten. This is the escape-valve companion the amend-rule anticipates:
a cleanup recorded with a proof that nothing unintended changed (`2026-07-11-canonical-docs-amended-not-regenerated.md`).*

## What changed

The 42 flat files were grouped by document *kind*. The **live docs stay at the `docs/` root** so the current
contract is unmissable; everything else moved into folders. `decisions/` and `deferred/` were already foldered
and are **untouched**.

```
docs/
  INDEX.md                                                 ← the map (rewritten for the new layout)
  prospector-v1-spec-rev14-2026-07-08.md                   ← CURRENT build spec (stays at root)
  project-prospector-state-of-project-rev7-2026-07-11.md   ← CURRENT status (stays at root)
  decisions/   (unchanged) dated fossils
  history/     (14) superseded build-spec revs {3,5,6,8,9,11,12,13} + state-of-project {rev1..rev6}
  notes/       (17) QA findings, reviews, build-notes, slice-specs, guidance, handoff
  origins/     (7 md + 2 pdf) founding-era + sibling-project archive
  deferred/    (unchanged) parked v2 designs
```

Advancing a canonical rev is now a fixed ritual: drop the new rev at the root, `git mv` the superseded one
into `history/`, update `INDEX.md` + the `CLAUDE.md` / `ARCHITECTURE.md` pointers.

## The governing rule: relocate, never rename; move, never rewrite

Two invariants make this safe under the constitution:

1. **Move, never rewrite.** Every relocation is a `git mv` with content unchanged (`git diff -M` shows `R100`,
   zero insertions/deletions). The amend-never-regenerate rule governs *content*, not *location*, so a
   byte-identical move changes no clause of the build spec, `CLAUDE.md`, the founding doc, or the
   state-of-project doc. The pre-write check is satisfied trivially: there is no changed clause to trace.
2. **Relocate, never rename.** Every filename is preserved exactly (the `YYYY-MM-DD-slug` decision-record names
   especially — those did not move at all). Because ~99% of the repo's ~120 doc references are **prose
   filename mentions**, not clickable links, preserving filenames keeps them all resolvable by search even
   where a folder prefix is now stale.

## The bound-doc amendments (each traces to this record)

The reorg moved two files that bound docs pointed at (rev12 spec and rev5 status into `history/`), which forced
four surgical single-line pointer amendments. Only the pointer clause changed in each; all surrounding text
(notably the `CLAUDE.md` rev-fold narrative) is preserved verbatim:

- `CLAUDE.md:6` — canonical-spec pointer → `docs/prospector-v1-spec-rev14-2026-07-08.md` (root).
- `CLAUDE.md:110` — SOI design-spec twin → `docs/notes/2026-07-04-soi-derived-sector-concentration.md`.
- `ARCHITECTURE.md:4` — status source-of-truth → `docs/project-prospector-state-of-project-rev7-2026-07-11.md`.
- `ARCHITECTURE.md:357` — email findings → `docs/notes/email_nuisance_suppression_findings.md`.

**Pre-existing staleness corrected in passing:** the two spec/status pointers were *already wrong* before the
reorg — `CLAUDE.md:6` named **rev12** and `ARCHITECTURE.md:4` named status **rev5**, while every other authority
(`INDEX`, `README`, `ARCHITECTURE:3`, all package READMEs) already said rev14 / rev7. Bringing them current is
a reconciliation to an already-established fact, not a new contract decision.

Nine non-functional code/config/test **comment/docstring** citations of the three moved `notes/` files were
also repointed (`config/prospector.yaml`, `prospector/{sensors,ingest,runner}/…`, four tests). No import, read,
glob, or assertion depends on a doc path — the test suite is behaviorally untouched.

## rho-G removed

`rho-G-hawkes-criticality-subsystem-design-theory.md` was deleted from both its locations (`docs/` and the
`BuildContextFiles/` provenance copy). It is a **sibling-project** doc (the Thesis Smoke Detector's criticality
subsystem), **unbuilt design-ahead**, and was never listed in the INDEX. The removal was motivated by the QA
review's own read — *"the theory docs are the extreme case… the 36KB rho-G/Hawkes subsystem is 100% unbuilt
design-ahead"* (`notes/prospector_full_review_claude_science.md`); that observation is left in place as the
provenance for this decision. Git history preserves the file if it is ever needed.

## Accepted drift (append-only fossils — cannot fix)

Twenty references originate **inside `decisions/` fossils** (append-only — never edited) and point out to files
that moved. Nineteen are `docs/<name>` or bare-filename **prose** that still resolve by search because filenames
were preserved. **One is a genuine break, and is accepted:**
`decisions/2026-07-10-9e-constituent-symbol-resolution-build.md:5` encodes a *relative* link
`../dispersion_foreign_ticker_findings.md`, whose target is now `../notes/dispersion_foreign_ticker_findings.md`.
The fossil is immutable, so the link stays stale forever; accepted because the target's filename is unique and
findable and git preserves the history. Recorded here so the drift is visible, per the map-matches-territory
discipline — the one place the map cannot be made to match the territory, said out loud.

## Why this was low-risk

The reorg looked intricate but was mechanically safe: **no Python / config / test / CI reads a `docs/` path**
(every code reference is a comment), and only **one clickable markdown link** points into `docs/`
(`README.md:102` → the current spec, which stayed at the root and did not break). The real cost was bounded to
prose staleness inside immutable fossils — enumerated above. Three parallel read-only investigations (a
cross-reference audit, a full-file classification, and a constraint audit) established these facts before any
file moved.
