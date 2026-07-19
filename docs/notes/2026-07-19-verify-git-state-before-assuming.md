# `main` moves — verify git state, never assume it

*2026-07-19. A build-seat (Code) process finding, recorded because the failure mode is **fail-silent**: it
does not break anything visible, it makes you believe a change landed when it did not. Owner-stated as a
working rule: "main moves, that's its default. we need to check before we assume with git."*

## The incident

Code opened PR #115 (a working note), then a few minutes later edited that note to fix a one-line citation
and ran `git commit --amend` + `git push --force-with-lease` on its branch — **believing #115 was still
open.** It had been merged ~minutes earlier. The amend therefore landed on an *already-merged* branch: the
fix was orphaned, `main` never received it, and for one step Code believed the citation was corrected when it
was not. Caught only by a routine `gh pr list` a moment later, which showed #115 absent from the open set.

**Damage: zero.** The merge commit on `main` was untouched; force-pushing a merged branch changes nothing
that matters, and the stale branch was deleted. The cost was a false belief, briefly held and self-caught.

## The class

**Any belief about repo state is stale the moment it is formed.** In this project that is structural, not
incidental: **Code opens PRs and the *owner* merges them** — asynchronously, often from a phone, between any
two of Code's actions. So "is this PR open," "is this branch merged," "where is `main`" are not facts Code
knows; they are facts Code *last observed*. `main` moving is its default state, not an edge case.

**The hazard is not the force-push — it is the silent non-landing.** A force-push to a merged branch is
harmless. Believing a fix landed, and *reporting it as done*, is the real failure: it is the fail-silent
class (register §1b frame 8) wearing a git hat. Nothing errors, nothing goes red, and the record of what was
"fixed" is simply wrong.

**It is also the exact inverse of the same day's cross-seat win.** Hours earlier, Code correctly overrode the
design seat's stale CAP-DRIFT claim by *opening the artifact* — "the seat with eyes on the machine wins."
That advantage is conditional: **it only wins if it actually looks.** Code reasoning from its own minutes-old
memory of PR state is the same error it had just corrected in another seat, pointed at git instead of a note.

## The checks (cheap, and they are the whole fix)

1. **Before amending or force-pushing a branch:** `gh pr view <n> --json state,mergedAt`.
   **Never amend a merged branch** — the change is orphaned and silently does not land. If the PR is merged,
   the fix needs a **new branch off freshly-fetched `origin/main`**, not an amend.
2. **Before branching:** `git fetch origin` and branch from `origin/main` — the existing
   branch-off-fresh-main rule is this one's sibling (`docs/decisions/2026-07-11-branch-off-fresh-main.md`).
3. **Before reporting a change as landed:** verify against the remote, not local state or memory —
   `git merge-base --is-ancestor <sha> origin/main`, or `git show origin/main:<path>`.
4. **Re-check rather than recall.** If a repo-state fact is older than the last tool call, it is an
   assumption. Cost of checking: one command. Cost of assuming: a false "done."

## Scope

A working practice, not a CONTRACT. It adds no mechanism and no gate — the checks are one command each, and
the discipline is the fix. Recorded here because the failure is invisible by construction: the only thing that
catches it is looking.
