# Canonical documents are amended, never regenerated (constitution amendment)

*Decision record, 2026-07-11. A design-thread-ratified amendment to the repo constitution (`CLAUDE.md`, new
section "Canonical documents — amended, never regenerated"), added by **surgical insertion of one section** —
never a regeneration, per the rule it establishes.*

## The rule

Canonical contract/reference documents — the **build spec, `CLAUDE.md`, the package READMEs, and the founding
document** — are **amended, never regenerated**: changed by a **surgical diff altering only the clauses a
recorded decision changed**, plus a changelog note of the delta and its decision-record; all other text
preserved verbatim. A **wholesale rewrite is forbidden** — regenerating a contract doc silently drifts text no
one decided to change. A clause is **superseded in place with the change recorded** (changelog + decision trail
+ git), never silently dropped: the doc states the *current* contract, and *every* change is traceable.

## Why

It is the doc-process form of the discipline the whole project already runs on — **append-only, never let the
present silently rewrite the past** (the fossil record, the superseding verdict, freeze-the-substrate ingest).
The failure it prevents is concrete and was nearly hit in the rev-7 state-of-project exercise: the "produce a
fresh doc" instinct, correct for a *snapshot*, applied to a *contract* document regenerates clauses no
decision touched — the contract drifts, and the drift is **invisible because there is no diff to check**. The
rule makes the diff — and the decision behind each changed clause — mandatory and visible.

## The two refinements (what keeps it from being brittle)

1. **State-of-project doc — the partial exception (two document kinds, two rules).** Its stable conceptual
   body (**Parts I–IV**) is contract-like → amended / carried forward. Its current-status rollup (**Part V**)
   is a snapshot of *now*, not a contract → re-synthesized each rev. This is why rev 7 carried Parts I–IV
   verbatim and rewrote Part V, while the spec took amendments. The rule names which part is which.
2. **The consolidation-rev escape valve.** Amend-only accretes awkward seams over many revs. A cleanup rewrite
   IS allowed — but only as an explicit **consolidation rev** with a **clause-by-clause diff proving no
   contract changed except the ones intended**, recorded in that rev's decision record. The forbidden thing
   was never *rewrite*; it is *rewrite unchecked*. Make the check mandatory and drift can't hide.

## Scope

**Bound:** the enumerated canonical set (build spec, `CLAUDE.md`, package READMEs, founding doc) + the
state-of-project doc's Parts I–IV. **NOT bound (freely authored):** working / build notes, QA findings,
session logs, and the **decision records themselves** — which are append-only (a changed decision is a new
record superseding, never an edit), the immutable trail this rule points to.

## The check (build seat)

Before writing a canonical doc: **diff against the prior version and confirm every changed clause traces to a
decision record.** A consolidation rev additionally carries the clause-by-clause diff proof in its own
decision record.

## Self-application

This amendment was added to `CLAUDE.md` by **surgical insertion of one new section** — the existing text
untouched — with this record as its decision trail. Amended, not regenerated; fittingly.
