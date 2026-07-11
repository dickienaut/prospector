# Note — gate merges on the test suite (Prospector repo)

*Do this when you have ~15 minutes. Requires Pro (done) for branch protection on a private repo. Repo: `dickienaut/prospector`.*

**What it does:** makes `main` un-mergeable unless the full test suite passes — the discipline made structural instead of a thing you remember to run. After this, the SOI branch (and every future one) merges the moment its checks go green, and a red suite blocks the button.

---

## Step 1 — add a CI workflow (so there *is* a check to require)

Branch protection can only require a status check that already exists, and a check only exists once a workflow has run at least once. So the workflow comes first.

Create `.github/workflows/tests.yml`:

```yaml
name: tests
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5   # pin to the current major tag — check the Marketplace
      - run: uv run pytest -q
```

`uv run pytest -q` is your exact local command; `uv run` auto-syncs deps and auto-installs the project's Python, so nothing else is needed. Tests are offline (the socket guard fails any test that opens a real connection), so they run clean on the runner.

Commit and push it (straight to `main` this once, or via a PR). **Let it run at least once** — until it has, the check name won't appear in the Step 2 dropdown. *(This is the #1 gotcha: the required-checks list is empty until a workflow has produced a check.)*

## Step 2 — protect `main` and require the check

**Settings → Branches → Add branch ruleset** (or, under classic "Branch protection rules," **Add rule**) → target branch `main`. Enable:

- **Require a pull request before merging** ✓ — set **Required approvals: `0`**. *(The #2 solo gotcha: you can't approve your own PR, so anything above 0 locks you out of your own repo. Zero still forces the PR flow and the status check; it just doesn't demand a reviewer you don't have.)*
- **Require status checks to pass before merging** ✓ → search for and select **`test`** (the job id from the workflow; that's the check name). Optionally also ✓ *Require branches to be up to date before merging* (forces a rebase on latest `main` before merge — tidy, occasionally annoying solo; your call).
- **Admin bypass:** leave it **available** — i.e. *don't* tick "Do not allow bypassing the above settings" / "Include administrators." That way the gate stops *accidental* red merges but you can still deliberately override in a pinch (broken CI, emergency). Tick it only if you want the gate to bind you too, no exceptions.

Save.

## Step 3 — two workflow niceties (30 seconds, optional)

**Settings → General:**
- ✓ **Allow auto-merge** — then you can click "auto-merge" on a PR and it merges itself the instant checks pass (no babysitting).
- ✓ **Automatically delete head branches** — cleans up merged branches so the branch list doesn't accrete.

---

## Result

Every merge to `main` now waits on green tests. Nothing to remember; the button is simply disabled until the suite passes. Same move as everything else in this project — put the discipline in the structure, not in your memory.

*Applies identically to the Protector and Prophit repos whenever you want the same gate — copy the workflow, repeat Step 2.*
