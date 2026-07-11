# Branch off a freshly-fetched `origin/main`, never off a sibling feature branch

*Decision record, 2026-07-11. A small but load-bearing development-discipline amendment to `CLAUDE.md`
(§Development), added by surgical insertion of one bullet. **Born from a bug** — a real near-miss this
session — which is fittingly the pattern the bug archive exists to capture.*

## The rule

Start every change from the current remote head: `git fetch origin && git switch -c <name> origin/main`.
**Never** branch off a stale local `main` or off a sibling feature branch. **Diff against `origin/main`
before opening the PR** — that diff is the last guard.

## Why — the near-miss

While the owner was merging doc PRs quickly, a new note was committed on top of a **sibling feature branch**
(`archive-sort-and-rho-g-restore`) whose base predated the merge of a *different* branch (the doc-naming
amendment, PR #32). Because that branch had never contained #32's changes, a PR opened from it would have shown
#32's merged `CLAUDE.md` section and its decision record as **deletions** — i.e. it would have **silently
reverted an already-merged constitution amendment.** The `git push` also accidentally re-created a
merged-and-deleted branch.

The bug was caught by the mandated **diff-against-current-version** habit (`git diff origin/main --stat` before
the PR): the deletions were obvious, the branch was rebased onto the real `origin/main`, and the stray branch
was deleted. No harm reached `main` — but only because the diff was read.

## Root cause & fix

- **Root cause:** a branch's *base* is invisible after the fact; a stale base turns "add my change" into "add
  my change **and** revert everything merged since the base." Fast-merging multiplies the exposure.
- **Fix (the rule):** cut every branch from a freshly-fetched `origin/main`, so the base is never stale; and
  diff against `origin/main` before the PR, so a stale base can never reach `main` silently.

## Class & lineage

This is an instance of the bug archive's **§1.9 doc-drift** class (a stale base is a stale record) crossed with
**§1.4 "passes for the wrong reason"** (a green branch that would nonetheless corrupt `main`). It is also a
direct application of the amend-never-regenerate **"check"** — *diff against the prior version before writing* —
generalized from doc content to git base. A rule born from a bug, guarding against the bug; the recursion holds.
