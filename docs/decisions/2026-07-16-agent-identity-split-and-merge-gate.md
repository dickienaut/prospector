# Agent identity split and the merge gate — rule 2 becomes mechanism

*Decision record, 2026-07-16. Ratified with the design thread and the owner. **Supersedes**
`2026-07-12-code-does-not-merge-human-reviews.md`, which recorded the same rule as a **posture** — Code
*could* merge a green PR and simply *must not*. That record's own escape clause ("requiring 1 approval would
deadlock a solo repo") named the exact thing this decision resolves: once the agents stop running as the
owner, a required review is no longer a deadlock, and the posture becomes a wall. Companion to the CI
merge-gate (`2026-07-11-ci-and-branch-protection.md`) and the four-seat model doc
(`docs/2026-07-16-how-we-work.md`, rule #2).*

## The decision

Rule 2 — **agents propose, the human disposes** — graduated from posture to **mechanism**. No sequence of
agent actions alone lands code on `main`. This rests on two things that had to be built together: an
**identity split** (the agents are not the owner) and a **merge gate** (the `main` ruleset requires the
owner's code-owner approval, covering the most recent push).

## Why the split is a prerequisite, not a parallel item

The posture-era rule could not become a mechanism by tightening the ruleset alone. Requiring one approval on a
repo where the *only* identity is the owner **deadlocks**: GitHub forbids approving your own PR, so a PR the
owner opened — as the sole identity the agents also used — could never be approved, and nothing would ever
merge. The 2026-07-12 record said exactly this and settled for a posture.

The split breaks the deadlock. Give the agents a **separate identity** and the author (agent) and the approver
(owner) are different accounts: a required review becomes satisfiable, and the agent cannot satisfy it for
itself. So the identity split is not a nicety beside the gate — it is the **precondition** that makes the gate
representable at all. A platform cannot require review *from a different identity* when there is only one.

## The identity split

- The agents run under a **machine account** (`claudeatalphalabsengineering`), a collaborator with **write**
  but **no admin** — so the account itself is the outer bound: push to one repo, and no power to change or
  bypass the ruleset that binds it.
- **Role × scope is the real bound.** Each seat's token carries only its role's scope: **Build** holds
  `repo, workflow` (it authors CI changes); **QA** holds only `repo` — no `workflow`, so GitHub rejects any
  push that touches `.github/workflows/`, and QA cannot rewrite the gate that binds it.
- **The fine-grained-PAT blocker.** GitHub's fine-grained PATs do not fully cover a collaborator acting on a
  **personal-account** repo (a documented gap — several operations still require classic scopes), so the
  machine account uses **classic** PATs scoped down per role. The account (one repo, non-admin) is the hard
  bound; token scope is the per-role bound on top of it.

## The gate

`.github/CODEOWNERS` = `* @dickienaut` (the owner is sole code owner). The `main` ruleset carries:

- `required_approving_review_count: 1`
- `require_code_owner_review: true` — the one approval must be the owner's;
- `require_last_push_approval: true` — the approval must cover the *most recent* push;
- `bypass_actors: []` — no exception, the owner included.

An agent's PR therefore cannot merge without the owner's approval, the agent cannot self-approve, and a commit
pushed *after* approval re-blocks the merge.

## Absence as the mechanism

The residual "once approved, the agent could click merge — it must not" was still a note-to-self. Closed by
**removing the owner's credential from the Mini**: `gh auth logout` for the owner account plus a purge of the
cached git credential from the macOS keychain. The Mini now holds only the machine account. An agent cannot
misuse a credential that isn't on the machine; a command that reaches for the owner's identity fails loudly
rather than acting as the owner. The owner approves from a **separate device** — the phone — and never needs
their identity on the Mini (probe 2 confirmed this). Absence is the mechanism, the same shape as removing a
path rather than remembering not to take it.

## Verified — the three probes

The wall was watched rejecting before it was relied on:

1. Bot opens a green PR → **blocked** (`REVIEW_REQUIRED`; the bot's own merge attempt is refused — "the base
   branch policy prohibits the merge").
2. Owner approves as code owner → **mergeable** (`APPROVED` / `CLEAN`).
3. Bot pushes one more commit → **re-blocked** (`REVIEW_REQUIRED` again).

The third probe is the one that mattered: it is the only one that exercises `require_last_push_approval` and
proves the **approve-then-swap** hole is closed — bless a benign diff, push different code behind it.

## The cost — the owner can no longer author

The mechanism binds its author too. The owner is the sole code owner and cannot approve their own PR, so any
PR the *owner* opens is unmergeable. In practice the agents become the only authors and the owner the only
approver. Accepted knowingly — the wall is worth the constraint.

## Deferred upgrades

- **Move the repo to an organization** — orgs expose finer controls (branch-protection actor lists, team
  code-owners) a personal-account repo cannot, and would rest the identity split on org membership rather than
  a collaborator invite.
- **Replace the classic PATs with a GitHub App** — per-repo, per-permission installation tokens, short-lived
  and revocable, are the right long-term credential; the classic PATs are the pragmatic start.

## Supersedes

`2026-07-12-code-does-not-merge-human-reviews.md` — append-only: that record stays as the immutable
posture-era statement; this one supersedes it and does not edit it. The "phone payoff" it described still
holds and is strengthened — the owner reviews and merges from the phone as the *only* place their identity
lives.
