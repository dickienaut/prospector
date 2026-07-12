# Code does not merge to `main` — the owner reviews and merges

*Decision record, 2026-07-12. A design-thread-ratified workflow posture, added to `CLAUDE.md` (Development
section) by surgical insertion of one bullet. Code's job ends at an open PR with green CI; the owner reviews
the diff and merges (from the Mac or the GitHub mobile app). The companion to the CI merge-gate
(`2026-07-11-ci-and-branch-protection.md`) — the ruleset made the gate binding; this keeps the human eyeball
in the loop.*

## The rule

Code branches, commits, pushes, and opens the PR — then **stops**. It **never merges to `main`**, even though
the `main` ruleset requires **0 approvals** and would let a green PR be merged by anyone holding the token. The
**owner** reviews the diff and merges.

## Why — CI-green is not correctness

The gate proves the suite passes; it does not prove the change is *right*. The failure modes this project
distrusts most all clear CI: **green-on-synthetic** (a slice that passes on a fixture but breaks on the real,
moving substrate), a **test that passes for the wrong reason**, a **regression introduced by the merge itself**
(green on the branch, red once combined — though the ruleset's up-to-date requirement narrows this). Human
review is where that class is caught, and across this project's history it has caught real ones. So the eyeball
stays: **mechanism gates green; the human gates correctness.**

## The phone payoff

Because the ruleset is **active with no bypass actors**, it binds *wherever* the merge is triggered — the Mac,
the API, or the GitHub mobile app. That makes the full loop safe on the go: Code (with the token) runs
branch → commit → push → CI → open PR from the session; the owner glances at the diff and merges in the mobile
app. A red PR can no more be merged from the phone than from the desk — the no-bypass mechanism is what makes
"review anywhere" trustworthy.

## Scope

A **posture**, not a new mechanism — the ruleset already binds Code; this rule adds that Code does not *initiate*
the merge of its own green PR. It does **not** change the 0-approval setting (requiring 1 would deadlock a solo
repo — see the CI record); the owner's review is deliberate practice, not an enforced gate. Recorded so the
"why not just auto-merge on green?" question has a standing answer.
