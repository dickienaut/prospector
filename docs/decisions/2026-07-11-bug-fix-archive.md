# A dedicated bug & fix archive — rules are born from bugs

*Decision record, 2026-07-11. Owner-initiated: start a first-class `docs/bugs/` archive that tracks defects
**and** the rules they spawn, because "**rules are born from bugs, so we must track them and the decisions that
sprout from them**," and because a class of **meta-bugs — like "didn't go to the primary source" — keeps
biting.***

## The decision

`docs/bugs/` becomes its own territory (not a corner of `notes/`), because the lineage **bug → rule** is
load-bearing and deserves a front door. It has three parts:

1. **Meta-bug classes** — the recurring patterns, each traced to the rule/CONTRACT it birthed. This is the
   heart: repeat offenders are where rules come from. Nine were catalogued from the QA record (see below).
2. **A complete bug index** — every logged defect (the H/S/B/I/P full review, N1–N10 going-live pass, the §9e
   dispersion finding, the §10 E1/E2 suppression finding), compact, each linked to its detail doc, its
   regression test, and the rule/decision it spawned.
3. **Per-bug records** — `YYYY-MM-DD-<slug>.md`, **born dated** (per `2026-07-11-doc-naming-convention.md`), for
   bugs found going forward; a template + a first worked example (`2026-07-10-email-volatile-fault-suppression.md`).

## Why a separate archive (not just `notes/`)

The raw QA findings already exist in `notes/` — but scattered across seven docs, organized by *review pass*,
not by *pattern*. The value the owner wants is the **cross-cutting lineage**: which recurring class a bug
belongs to, and which rule it minted. That view doesn't exist until it's synthesized. And naming it explicitly
makes the meta-bugs *visible as a checklist* — the point is to catch the next instance of a known class **before**
it ships, not just to log it after.

## The nine meta-bug classes (and the rules they birthed)

Extracted from the QA record: **(1) green-on-synthetic/broken-on-real** → fixture-provenance discipline;
**(2) convergent-prior error** → primary-source verification + the three-seat workflow; **(3) invariant in
prose, not mechanism** → make-it-un-violatable + attempt-the-violation tests; **(4) test passes for the wrong
reason** → runner-faithful seeds; **(5) never anchor on a ticker** (the HECO lesson, recurring deeper) → the
series-ID identity layer + the §9e primary-source gate; **(6) go to the primary source** → the primary-source
gate + the no-third-party-feed / no-LLM-text walls; **(7) nuisance-alarm / GPWS** → the §8a alarm-posture
CONTRACT + the stable-`key=` convention; **(8) fail-loud vs fail-silent** (the severity axis — silent wrong
numbers are the dangerous ones); **(9) doc drift / memory-prosthetic leak** → §5-single-source-of-truth +
delete-and-restate-on-close. Each already has a decision record or `CLAUDE.md` clause behind it; the archive
makes the bug→rule edge explicit so the *reason* the rule exists isn't lost.

## Boundary & discipline (so it doesn't fragment or drift)

- **`bugs/` = defect lifecycle** (broke → root cause → fix → regression test → rule born). **`decisions/` =
  design/contract choices** — a bug that forces a CONTRACT change still gets its decision record; the bug entry
  *links* it. **`notes/` = the raw findings** (primary detail) — the archive **indexes** them, and (honoring
  relocate-never-rename / never-change-the-past) **never moves or rewrites** them.
- The index (`bugs/README.md`) is stable-named, **amended in place** (a living map, like `INDEX.md`); the
  per-bug records are dated fossils.
- **Log a bug when it's root-caused, not after it's fixed** — the trail is the point.

## Relationship to the doc-discipline rules

This is the QA-lifecycle analogue of the decision trail, and it leans on the rules ratified the same day:
born-dated records (`2026-07-11-doc-naming-convention.md`), amend-in-place for the index
(`2026-07-11-canonical-docs-amended-not-regenerated.md`), and index-don't-move for the historical `notes/`
findings (`2026-07-11-docs-reorganization.md`). Fittingly: the archive that tracks how rules are born from bugs
is itself built on rules born from bugs.
