# CI test-gate + `main` branch-protection

*Decision record, 2026-07-11. Ratifies making the offline 554-test suite a **mechanical merge gate** — CI +
a `main` ruleset so nothing lands on `main` unless the `test` check is green, enforced by mechanism rather
than memory. Implements the setup spec (`docs/notes/2026-07-11-ci-branch-protection-setup.md`). This record
is the decision + config + rationale; the rollout is sequenced below (the ruleset can only be applied once
this workflow has run on `main`).*

## The setup

- **`.github/workflows/ci.yml`** (this PR) — runs on every `pull_request` into `main` **and** on `push: main`
  (the push trigger is required so the `test` check registers on the default branch and becomes selectable as
  a required check). One job `test` on `ubuntu-latest`: `uv sync --locked` → `uv run pytest -ra` → `uv run
  pros --help`. Single Python 3.12, no matrix, **no secrets** (the suite is offline — the network guard fails
  any socket, so CI needs no Tiingo/EDGAR/AWS creds).
- **`main` ruleset** (a GitHub setting, applied via `gh api` **after** this PR merges — see Order below):
  enforcement **Active**, targeting the default branch — **require a PR** (0 approvals), **require status
  check `test`** with **strict / up-to-date-before-merge ON**, **block force pushes**, **restrict deletions**,
  **no bypass actors**. Linear history is **not** enforced (owner preference — merge commits allowed).

## Load-bearing choices

- **`moto[s3]` must install, or it's a false gate.** The full ~554 count depends on `moto` (S3/store tests);
  without it they skip silently and CI goes green on a partial suite — the exact false-green this project
  distrusts. Verified: `moto[s3]`, `pytest`, `hypothesis` are all in the default `[dependency-groups] dev`,
  so `uv sync --locked` installs them; `pytest -ra` also makes any missing-dep skip visible.
- **`uv sync --locked`** (not `--frozen`): fails if the lockfile drifted from `pyproject.toml` — catches a
  "changed a dep, forgot to re-lock" before it reaches `main`.
- **0 required approvals.** For a solo repo, requiring 1 would deadlock — GitHub forbids self-approval and
  there is no second reviewer. The PR requirement + the `test` gate are the mechanism; a review count is not.
- **No bypass actors — deliberately.** The owner *can* exempt themselves and does not. A ruleset the owner
  can bypass is theater, not a gate. Same discipline as the never-execute firewall: the invariant is enforced
  by mechanism, not by a rule someone remembers to follow.

## Order (the gotcha)

1. Add `ci.yml` on a branch → PR. The workflow runs **on the PR itself**, proving green before it's law.
2. **Merge the PR.** The `push: main` trigger then runs `test` on `main`, **registering the check** on the
   default branch (GitHub only offers a check in the required-checks picker after it has run there).
3. **Then** apply the ruleset requiring `test`. Skipping the order makes `test` un-selectable.

## Acceptance (how it will be proven — done when)

- The workflow's own PR shows `test` **green**: ~554 passed / 2 xfailed, **no unexpected skips** (the moto
  false-green check); `pros --help` passes.
- After the ruleset is active, a throwaway PR with a deliberately failing test shows `test` **red** and its
  merge button **blocked** — proving the gate bites, not assuming it.
- `gh api …/rulesets` shows the ruleset **Active** with **no bypass actors**.

## Deferred (spec §6, not part of this)

Release tag `v1.0.0` (cut at v1-complete; the scheduled runner deploys from the tag, not `main` HEAD),
environments + deploy-protection (M7-era), and the GitHub Projects board — sequenced later.
