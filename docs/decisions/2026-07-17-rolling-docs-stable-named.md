# The live build spec and state-of-project doc are stable-named, amended in place

**Date:** 2026-07-17
**Status:** ratified (design thread)
**Supersedes (in part):** `docs/decisions/2026-07-11-doc-naming-convention.md` — specifically its
*"Rev only where it versions"* clause, insofar as it filed the **live** build spec and state-of-project doc as a
dated, `-revN` versioned series. That record stays as an immutable fossil (append-only); this one supersedes the
clause, it does not edit it.

## Decision

The two rolling canonical docs move to **stable names, amended in place**:

- `docs/prospector-v1-spec-rev15-2026-07-16.md` → **`docs/spec.md`**
- `docs/project-prospector-state-of-project-rev8-2026-07-16.md` → **`docs/state.md`**

The **rev lives in the header** (`rev 15`, `rev 8`), a single content claim, not in the filename. From rev 16
on, a rev bump is a **surgical in-place amendment** (per amend-never-regenerate) — no new dated file, no
`git mv` to `history/`. The pre-2026-07-17 dated revs already in `history/` stay exactly as they are; the full
series is `git log --follow docs/spec.md`.

## Why

1. **It is the naming convention applied to itself — a correction, not a new preference.** The convention already
   says *stable-named = amended-in-place single instance; dated = point-in-time or versioned.* The build spec is
   governed by **amend-never-regenerate** — *surgical diff, everything else preserved verbatim* — which **is** the
   amended-in-place contract. So the spec (and the state doc's Parts I–IV) were **misclassified** as a dated
   series. The fix makes two existing rules stop contradicting each other. (The contradiction was live: the
   convention called each rev a *new file*, where "surgical diff" is a fiction and "preserved verbatim" is
   unauditable.)

2. **The decisive argument: rev-in-filename destroyed the PR diff — where the mandated check lives.**
   CLAUDE.md requires, before writing a canonical doc, *"diff against the prior version and confirm every changed
   clause traces to a decision record."* Under the dated convention, a rev bump showed git a **new file** plus a
   **move** (PR #86: rev14→rev15 was +2000 lines new + rev14→`history/`). **No diff.** The reviewer saw nothing;
   the check had to be run by hand (`diff history/…rev14 …rev15`) — exactly the "remember to run" that makes a fold
   a major undertaking. Sharper for the state doc (PR #87): *"Parts I–IV carried verbatim"* is its central
   discipline and was **unverifiable in review** — asserted, checked by hand. Under a stable name the PR diff
   **shows** Parts I–IV untouched and Part V's re-synthesis as the real diff. The claim stops being a claim.

3. **One fact, many homes.** The rev-in-filename made every reference a **version pin** — CLAUDE.md, ARCHITECTURE,
   INDEX, decision records each a home for *which rev is current*. It drifted repeatedly and undetected
   (CLAUDE.md said rev12 while the spec was rev14; ARCHITECTURE said status rev5; INDEX said "rev 15 pending"
   after #86 merged) — the same falsifiable-but-undetected pattern as the four status registers. A rev pin becomes
   a **content claim** ("per spec rev 15 §8a"), checkable against the header, one home.

4. **The dated benefit was always for the fossils.** Dating disambiguates *coexisting instances*; there is only
   ever one live spec. Keeping `history/` dated preserves the rule's whole purpose. Nothing it protects is lost.

## Cost (honest)

You lose browsable old revs *without git*. Real but bounded: the `history/` fossils **stay dated and browsable**,
so this only bites revs *after* the transition (the freeze-era ~3/year), which `git log --follow docs/spec.md`
enumerates with date + PR. An independent reader comparing, e.g., rev7→rev8 without a paste now depends on git —
the fold's composition already routes that diff through the build seat.

## Freeze note

Unlike a checker maintained for years to guard a few events, this is a **deletion**: one reference-checked rename
(×2), then zero maintenance forever. It converts the fold's most miss-prone check — the surgical diff and the
verbatim-preservation audit — from a manual grep into the review UI's default view. Cheap now, cheaper later.

## Mechanism (how it was executed, within the existing rules)

The naming convention's own **escape valve** — *"a specific legacy misnamed doc may be normalized as a deliberate,
reference-checked one-off (grep its references, fix the fixable, document any fossil drift), never a bulk
rename"* — is invoked here, twice:

- **`git mv` ×2, R100** (100% similarity — zero content change to either doc; the rename *is* the whole spec/state
  diff in this PR).
- **Whole-repo reference grep** (not just `docs/`): live pointers updated in `CLAUDE.md`, `ARCHITECTURE.md`,
  `README.md`, `docs/INDEX.md`, and **10 package `README`s**.
- **Fossil citations are left untouched.** Append-only `decisions/` records that cite a dated spec/state path are
  never rewritten to chase a rename (that would be the violation). Any that cite an *older* rev path were already
  dangling before this change (every prior rev bump did the same) — a **pre-existing backlog** the cited-anchor
  gate will surface properly; it is not created by, nor grown into, this PR.
- **`INDEX.md` carries the redirect + transition marker** so `history/` does not read as a misleading fossil and a
  live-yesterday citation still lands: *rev15 → `docs/spec.md`, rev8 → `docs/state.md`; from rev 16, amended in
  place.*

## Provenance

This is a decision (it precedes no code), so its anchor is this PR itself: the `git mv` R100 renames and the
reference-checked pointer sweep are the evidence, verifiable in the diff. Design surfaced the rev-in-filename
mechanism; the *"naming convention applied to itself"* framing (misclassification, not new rule) is the build
seat's; QA's D2 (INDEX lagging the newest canon) is a related symptom of the same one-fact-many-homes defect.
