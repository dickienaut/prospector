# Bug README refinements — the bounded set (2026-07-11)

*Decision record, 2026-07-11 — recorded as the written trace for the bug-README §1 re-shelve (PR #36). The
design-thread spec that governed the change, preserved **verbatim** below (primary source, not re-voiced into
build-seat prose); the build-seat **Outcome** is appended. Refinements 1, 3, 4 shipped in that PR; refinement 2
rides the CI work.*

*Spec for Code, from the design-thread review of `docs/bugs/README.md`. **This is the bounded set of four
refinements the review actually proposed** — re-shelve §1, add the CI lineage-check, reframe convergent-prior,
fix the wikilinks. The larger restructure a separate thread elaborated (a four-level split, stable slug IDs, a
survivorship line, a new bug class) is **explicitly out of scope** (§5): those are un-vetted additions to a
load-bearing register, each its own design pass if wanted — they do not ride in on "restructure §1."
Everything here preserves the archive's content **verbatim**; it re-shelves and re-frames, it does not rewrite
(amend-never-regenerate + the doc's own "re-shelving, not a rewrite" read).*

---

## 1. Re-shelve §1 into two subsections — preserving the numbers as stable IDs

§1's flat numbered list conflates three kinds of entry, which breaks its own "tag the class" instruction (you
can tag a bug "class 5"; you can't tag one "class 6 — go to primary source," because that's the *fix*, not a
defect). Split §1 into two clearly-labelled subsections:

- **Taggable failure-classes** — the actual defect patterns a new bug tags to: **1** (green-on-synthetic),
  **3** (invariant-in-prose-not-mechanism), **4** (test-passes-for-wrong-reason), **5** (ticker-as-identity),
  **7** (nuisance-alarm), **9** (doc-drift).
- **The frame — not taggable classes** (read to understand *why / how severe / how we counter*, never
  tagged): **2** (convergent-prior — *the root*; see §3), **8** (fail-loud-vs-silent — *the severity axis*),
  **6** (go-to-primary-source — *the countermeasure*).

**[CRITICAL] Do NOT renumber.** Keep the class numbers 1–9 exactly as they are. The §2 index tables' "Class"
column references them by number, and renumbering would break those references — the same reference-integrity
`relocate-never-rename` exists to protect. The numbers are stable IDs; the re-shelve only groups them. So the
taggable set reads "1, 3, 4, 5, 7, 9" (non-contiguous, and correct) and the frame is "2, 6, 8." This is the
taxonomy's version of moving files into folders without renaming them.

**[CRITICAL] Content byte-identical.** Each entry's description, instances, and "rule born" stay verbatim;
only which subsection it sits in changes. Re-shelving, not rewriting.

**§2 needs no change — and reads richer for it.** Because the numbers are preserved, a Class value like
`1,2,8` still resolves: green-on-synthetic (taggable 1), rooted in convergent-prior (frame 2), fails silently
(frame 8). The column now naturally reads as *taggable-class + frame annotations (root / severity)* — a bonus,
not a migration.

Then update the "How this works" bullet: a new bug tags to one of the **taggable** failure-classes (1, 3, 4,
5, 7, 9) or "one-off"; the **frame** (2, 6, 8) is the lens you read to understand it, not a tag.

## 2. The CI lineage-check — the mechanization (rides the CI workflow)

*The load-bearing item. It makes the archive verify its own claims (the archive eating its own class-3 dog
food) so it can't become a victim of its own class-9 drift. It adds a step to the CI workflow specced in
`notes/2026-07-11-ci-branch-protection-setup.md`; implement alongside that, not separately.*

A CI step that parses `docs/bugs/README.md`'s §2 tables and, for every row naming a guarding test
(`tests/<file>::<test>`), asserts that **test node exists in the collected suite**:

- **✅ and 🟡 rows** — the named node must **exist** (the same job's `pytest` run already verifies it *passes*,
  so existence + a green suite = the claim holds).
- **💤 rows** — the named node must **exist** (the suite's own `xfail(strict)` already guards it hasn't started
  passing early).
- **⭕ rows** — no test claimed; skip.

Implementation: a small `scripts/check_bug_lineage.py` that (a) extracts the `tests/…::…` refs + status glyph
from the tables, (b) gets the real node list via `uv run pytest --collect-only -q`, (c) fails if any ✅/🟡/💤
row's named node is absent — message e.g. *"README claims `tests/…::foo` for H1 (✅) but that node isn't in the
suite; the archive has drifted from the tests — fix the README or restore the test."* Run it as a step in the
CI `test` job (after `uv sync`, alongside `pytest`).

**[Scope guard]** Verify **only** the named-test-node-existence claim — the one falsifiable, machine-checkable
thing. Do **not** attempt root-causes, "rule born," or prose; those aren't checkable and trying is scope creep.
One claim, checked: *the guarding test the archive names exists.*

## 3. Reframe convergent-prior (2) as the root

Currently subordinate to class 1 ("the reason class 1 stays invisible"). Reframe it — **content verbatim,
framing elevated** — as **the root**: code and fixture share one wrong premise *because the same model wrote
both*, so no internal review catches it, only the primary source does. It's the vulnerability unique to an
AI-authored codebase and the whole justification for the four-seat architecture (author ≠ reviewer) and the
primary-source wall. In the re-shelved §1 it **leads the frame subsection** as "the root — why the whole silent
set stays invisible," with green-on-synthetic and the rest read as its downstream symptoms. A §1 framing change
only; no §2 reorder.

## 4. Fix the wikilinks

`[[validate-slices-against-real-moving-substrate]]` and `[[prove-spawners-fire-on-real-seed-data]]` are Obsidian
syntax — inert text on GitHub (the single source of truth now). Convert to standard `[text](relative/path.md)`.
**And resolve the targets:** they read like intended rule-doc names — if the doc exists, point at it; if it
doesn't yet, make it an explicit `` `TODO: rule doc not yet written` `` rather than a link to nowhere. A
dangling standard link is no better than a dangling wikilink.

## 5. Explicitly NOT in this spec (the scope guard)

From a separate thread elaborating the review — **not** part of it, must not ride in on "restructure §1." Each
is a real question, but each is its own design pass, decided *before* it touches the register, not a diff
reviewed after it's landed:

- **A four-level split of §1** — the review proposed a *two-way* split (taggable classes | frame), §1 above.
  Nothing more.
- **Stable slug IDs** for classes/bugs — the numbers already serve as stable IDs (§1); a slug scheme is a
  separate decision carrying its own reference-migration cost.
- **A survivorship line** — undefined here; not reviewed.
- **A new bug class** — a structural addition to the taxonomy, not a "safe fix"; needs a design pass (which
  class, why it's distinct, what it subsumes) before it's added.

If any is wanted, raise it as its own item and it gets designed. It does not enter here.

## 6. Sequence

- **One PR** for the doc edits — refinements **1, 3, 4** (re-shelve, reframe, wikilinks). Branch off fresh
  `origin/main`; diff against `origin/main` before the PR (naming-clause discipline); confirm the diff is a
  re-shelving/re-framing with content preserved — **no class idea reworded, no number changed.**
- **Refinement 2** (the lineage-check) rides with the CI setup work — it's plumbing and needs the CI workflow
  to exist.

---

## Outcome (build seat, 2026-07-11)

Implemented on branch `bug-readme-refinements` → **PR #36**.

- **Refinements 1, 3, 4 landed** in one doc commit. The §1 re-shelve was performed by a **self-verifying
  script** that moves exact byte-ranges and asserts every original §1 body line survives — the only body lines
  that changed were the **two wikilink lines**; **all nine class bodies are byte-identical**, and **§2–§4 are
  byte-untouched**. That is the spec's "re-shelve, not rewrite" made mechanical (the archive's own
  mechanism-not-prose rule, applied to editing the archive).
- **Numbers 1–9 preserved (no renumber),** as §1 mandates — so existing `§1.N` references in sibling decision
  records (e.g. `2026-07-11-branch-off-fresh-main.md`'s "§1.9 doc-drift / §1.4 passes-for-wrong-reason") still
  resolve. This is exactly the reference-integrity the no-renumber clause protects.
- **Wikilinks resolved to real repo docs — no `TODO` needed:** class 1 →
  [`CLAUDE.md` §Fixture provenance](../../CLAUDE.md#fixture-provenance) (the home already cited beside it),
  class 3 → [`2026-07-06-soi-corroboration-retry-9d.md`](2026-07-06-soi-corroboration-retry-9d.md) (defines the
  fires-not-called test). Both wikilinks turned out to point at the private memory layer, not repo docs — so
  they were re-pointed at the real homes rather than marked dangling.
- **Amendment ratified after this spec** (design thread, same day, folded into the same PR): the §1 intro's one
  word `"a class here"` → `"a **taggable** class here"` — the minimal edit that makes the re-shelve internally
  consistent (frame classes 2/6/8 are not taggable). Handled as a *specified* one-word change, not a
  "while-you're-in-there," to hold the seat boundary under exactly the "it's trivial" pressure that erodes it.
  Rendered **bold**, not `*italic*`, to survive the already-italicised intro paragraph.
- **Refinement 2 (CI lineage-check) deferred** — there is no `.github/workflows/` yet; per §6 it rides the CI
  branch-protection plumbing (`notes/2026-07-11-ci-branch-protection-setup.md`) when that lands.
- **The §5 out-of-scope items** (four-level split, slug IDs, survivorship line, new class) were **not** touched.
