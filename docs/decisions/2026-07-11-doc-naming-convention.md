# Doc naming — provenance in the filename (constitution amendment)

*Decision record, 2026-07-11. A design-thread-ratified amendment to the repo constitution (`CLAUDE.md`, new
section "Doc naming — provenance in the filename"), added by **surgical insertion of one section** — forward-dated,
per the rule it establishes.*

## The rule

Every doc is **born with a leading ISO date** (`YYYY-MM-DD-…`); a `-revN` suffix is added **only** where the
doc is one of a versioned series (spec, state-of-project, a decision revisited as rev 2+), each revision a **new
dated file** with the prior moved to `history/` (never a rename-in-place). Stable-named exceptions —
`CLAUDE.md`, `INDEX.md`, `ARCHITECTURE.md`, package `README`s, `LICENSE` — keep fixed names because they are
**amended in place**, not re-fossilized. **Forward-only:** the rule governs *new* files; existing filenames are
not bulk-renamed. A specific legacy misnamed doc may be normalized only as a deliberate, **reference-checked
one-off**.

## Why

Mostly it formalizes what the repo already does — every decision record is dated, the spec and state doc carry
date + rev. Writing it down makes it enforceable and closes the gaps (the undated / same-named files that caused
real confusion — e.g. an undated `rho-G` turning up as a 24 KB vs 36 KB mystery, two same-named `CLAUDE.md`
copies from different projects — during the `2026-07-11-archive-sort-and-history-recovery` sort). A clean dated
filename makes a doc's version answerable **at a glance**, which matters more now that **the repo is the single
source of truth**: the parallel project-mount is abandoned, so the amend loop is *paste the current repo text
into the design thread → amend → commit here*, and "which version do I paste" has to be answerable from the name.

## The three refinements (getting the scope right is the whole ballgame)

1. **Forward-only — the load-bearing one.** As first stated, "date every doc" collided with a rule just set:
   the reorg's ***relocate, never rename*** (`2026-07-11-docs-reorganization.md`). References point at filenames,
   and byte-identical names are what kept ~99% of them resolvable by search across the reorg. **Bulk-renaming
   existing files to bolt dates on would break exactly those references and *multiply* the one un-fixable cost
   the reorg documented — fossil drift** (a decision record is immutable; it cannot be edited to point at a
   renamed file). So the rule is **"files are *born* dated," not "rename what exists."** The escape valve is the
   same disciplined shape as amend-never-regenerate's consolidation-rev: a *specific* badly-named legacy doc may
   be normalized as a reference-checked one-off (grep references, fix the fixable, document any drift) — **never
   a bulk rename**. And it is mostly unneeded: grouping-by-kind (the reorg) plus forward-dating already dissolves
   the provenance pain, and git recovers a legacy file's provenance anyway.
2. **Date on everything; rev only on a versioned series.** A date is stable — a file's date never changes — so it
   belongs on every born-here doc. A **rev number only means something on a versioned series** (the spec, the
   state doc, a revisited decision like `...-guidance-rev2`), and there each rev is a new dated file (rev-bump =
   new file, prior → `history/`, never rename-in-place — already the practice). A `-rev1` on a one-shot fossil is
   noise; it will always be rev 1.
3. **The exception set is principled — worth stating, not "some files are special."** The stable-named docs
   (`CLAUDE.md`, `INDEX.md`, `ARCHITECTURE.md`, package `README`s, `LICENSE`) keep fixed names **because they are
   amended in place** per amend-never-regenerate — one always-current instance whose history lives in git and its
   changelog, not a dated series. So the naming line is the same distinction that already governs *how* each kind
   changes: **stable-named = amended-in-place single instance; dated = point-in-time or versioned.**

## Relationship to the rules it sits beside

It is the naming corollary of two existing rules: **append-only / amend-never-regenerate** (the stable-named
exception set is exactly the amended-in-place set) and the **reorg's relocate-never-rename** (which forward-only
protects). Recording the *reason* for forward-only is the point of this fossil — the rationale (it defends the
reorg's reference-integrity) is exactly the kind of thing that gets lost and re-litigated the first time someone
is tempted to bulk-rename for tidiness.

## Self-application

This amendment was added to `CLAUDE.md` by **surgical insertion of one new section** — existing text untouched —
and this record is a **new, forward-dated file** (not a rename of anything). Born dated, added by surgical
amendment; fittingly.
