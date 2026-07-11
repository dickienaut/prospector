# CI + branch protection: setup spec (2026-07-11)

*Setup spec for Claude Code. Stands up the plumbing that makes the test suite a **merge gate** — nothing lands
on `main` unless the full suite is green, enforced by mechanism rather than by remembering. This is the
capstone on the project's own QA philosophy ("the tests are the gate; test the violation; RED-first") — it
makes the gate mechanical. Scope here is **CI + the `main` ruleset** (the QA piece); the release tag,
deploy environments, and the Projects board are sequenced at the end as later, non-blocking work.*

---

## 1. What this buys, in one line

Every PR runs `uv run pytest` automatically; `main` is protected so a PR **cannot merge unless that check
passes**. A slice can no longer land red — even if a review missed something, even if it's your own PR. It
also catches the class of bug a human gate can't: a regression introduced by a *merge* (green on the branch,
red once combined), a locally-skipped test, a lockfile that drifted.

## 2. The CI workflow — a committed file

Create `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]          # REQUIRED — see §4: the check must run on main to become selectable

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true    # supersede stale runs on the same ref; saves minutes

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Install uv (with cache)
        uses: astral-sh/setup-uv@v6      # pin to the current major; confirm latest
        with:
          enable-cache: true

      - name: Sync dependencies (locked, incl. test deps)
        run: uv sync --locked

      - name: Run the suite (offline — the network guard is active)
        run: uv run pytest -ra

      - name: CLI smoke test
        run: uv run pros --help
```

**Deliberate choices, and the QA-load-bearing ones flagged:**

- **No `env:` / secrets block — on purpose.** The suite is offline (the network guard fails any socket), so CI
  needs *no* Tiingo token, *no* EDGAR user-agent, *no* AWS creds. Hermetic and secret-free — the payoff of the
  offline-by-design suite. Do not add secrets to make a test "work"; a test that needs the network in CI is a
  test that needs fixing.
- **[CRITICAL — false-green risk] Confirm `moto` installs, or the S3/store tests SKIP silently.** The full
  count (~554) depends on `moto` being present; without it, the store tests skip and CI goes **green on a
  partial suite** — a false gate, the exact thing this project distrusts. `uv sync --locked` installs the
  default dev group; verify `pytest` **and** `moto` live there. If they're in a separate group/extra, make the
  step `uv sync --locked --group <name>` (or `--extra <name>`). `pytest -ra` surfaces skip reasons in the log,
  so a missing-dep skip is at least *visible* — but the fix is ensuring `moto` installs, not tolerating the
  skip.
- **`uv sync --locked`** (not `--frozen`): installs from the lockfile **and fails if the lock is out of sync
  with `pyproject.toml`** — catching a "changed a dep, forgot to re-lock" drift before it reaches `main`.
  Another small QA win for free.
- **`pytest -ra`**: runs everything and reports skip / xfail / xpass reasons in the summary — so the 2 xfails
  are visible (and an xfail that unexpectedly *passes*, e.g. the E2-flapping test the day the window lands,
  shows up loudly rather than silently).
- **Single Python version** (the project's pinned `.python-version` / `requires-python`) — **no matrix.** You
  deploy on one runtime (the Mac mini); testing across versions is unearned scope.
- Action versions (`checkout@v4`, `setup-uv@v6`) are current majors at writing — confirm latest when you commit.

## 3. The `main` ruleset — a settings change, NOT a committed file

Rulesets live in repo **Settings → Rules → Rulesets**, not in the tree. Configure a ruleset targeting the
default branch (`main`), enforcement **Active**:

- **Require a pull request before merging.** No direct pushes to `main`. *Required approvals:* your call — `0`
  is fine for a solo operator (the PR is still required and auto-mergeable once checks pass); set `1` only if
  you want to force yourself to re-read the diff as a speed-bump (Science's cold read + your review already
  happen upstream, so this is optional friction, not the safety mechanism).
- **Require status checks to pass** → select **`test`** (the CI job). This is the load-bearing rule.
  (Optionally *require branches to be up to date before merging* — catches a semantic conflict with a `main`
  that moved under you; low friction for a solo repo, mild lean toward on, your call. A merge queue is
  overkill here.)
- **Block force pushes.**
- **Restrict deletions** (can't delete `main`).
- Optional: **Require linear history** (squash/rebase only, no merge commits) — keeps the history clean;
  preference, not correctness.

**[Load-bearing] Do NOT add yourself as a bypass actor.** You're the repo owner, so you *can* exempt yourself
— don't. The entire point is that the mechanism binds even you; a ruleset the owner can bypass is theater, not
a gate. This is the "invariant enforced by mechanism, not a comment" discipline applied to the merge itself —
the same reason the never-execute wall is architectural rather than a rule you keep.

## 4. The order — and the gotcha that trips everyone

1. Create `.github/workflows/ci.yml` on a branch → PR. The workflow runs **on the PR itself** (via
   `pull_request`), so you see it work before it's law.
2. **Merge that PR.** Now the workflow also runs on `push: main`, which **registers the `test` check on the
   default branch.**
3. **Then** create the ruleset requiring `test`. GitHub only offers a status check in the required-checks
   picker if it has run on the target branch within the last **7 days** — which is exactly why step 2 comes
   before step 3, and why the workflow triggers on `push: [main]` and not just `pull_request`.

Skip the order and the `test` check won't appear as selectable, and you'll think the workflow is broken when
it isn't.

## 5. Verification (done when)

- The CI workflow's own PR shows the `test` job running and green.
- A deliberately-broken throwaway branch (e.g. a failing assert) opens a PR whose `test` check goes **red** and
  whose merge button is **blocked** — prove the gate bites, don't assume it.
- The `test` run log shows ~554 passed / 2 xfailed and **no unexpected skips** (confirms `moto` is installed —
  the false-green check).
- The ruleset shows enforcement Active with **no bypass actors**.

## 6. The rest of the plumbing — sequenced, not now

Named so it's not forgotten, deferred because it isn't the QA piece and (for the release) isn't yet meaningful:

- **Release tag `v1.0.0`** — cut when **v1 finishes** (rebalance-wiring → M6 → M7). The scheduled runner
  deploys from the tag, not from `main` HEAD, so ongoing v2 work never touches the running monitor. No point
  tagging a release before v1 is build-complete.
- **Environments + deployment protection rules** — the **M7-era** piece (there is no "deploy" to protect until
  the runner is scheduled). A `production` environment deploying from the release ref; optionally require a
  successful staging deploy before a merge to `main`.
- **GitHub Projects board + milestones** — whenever you want the v1/v2 organization; independent of CI. A board
  with a `stream` field (v1-finishing / v2) and milestones (v1 complete, v2 proto-cluster, v2 discourse). This
  is the "two parallel branches" instinct done right — one board, two lanes, not two divergent codebases.

---

*Net: after §§2–5, `main` is always-green and releasable, and the 554-test suite is a gate no one can route
around — the mechanical form of a discipline the project has held by hand all along.*
