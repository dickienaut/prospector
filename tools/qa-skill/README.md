# `tools/qa-skill/` — the QA seat's review harness (repo is SOURCE)

This directory holds the Prospector QA seat's procedure **as source of truth**.
The QA seat runs on the Claude Science platform, where the operative copy is a
loaded skill (`prospector-branch-qa`). That copy is a **deployment** of what
lives here — the same shape as Code's worktree pinned at a tag: the repo is the
source, publishing to the platform catalog is the deploy.

Why it moved here (it used to live only in the platform catalog, edited
in-session, unreviewed): the skill *is* the QA membrane — the fetch-the-repo-of-
record procedure, the RED/GREEN gate, the provenance guard, the delivery gate.
It is the one seat-procedure that is **executable**, and it was the only one not
in the repo, not reviewed, not gated. `CLAUDE.md` governs Code in the repo;
`METHOD.md` governs every seat in the repo; this governs QA and now does too.

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The skill's instructions (what the QA seat loads). |
| `kernel.py` | The skill's kernel sidecar — the operative helper functions: `fetch_prospector_branch`, `verify_red_green` (the RED/GREEN membrane), `deliver_qa_findings_pr` (the provenance-gated delivery path), `provenance_stamp`, `check_diff_hygiene`, `qa_git_env`. stdlib-only at import time. |
| `tests/` | The membrane's **negative controls** — the checker checked by something other than itself. |

## The tests (RED/GREEN target for each)

Every test asserts **behaviour**, not implementation, and is proven to
discriminate: RED against a kernel with the historical bug reintroduced, GREEN
against the shipped kernel.

### `tests/test_provenance_gate.py` — the provenance TRUTH gate

A findings PR must bind to the exact commit QA fetched+read+tested. All three
rejection paths are **network-free** (with `base_sha` supplied, no ref lookup
fires and the guards raise before the first request):

- `test_omitted_reviewed_sha_is_refused_not_pushed`
  - **RED** against the historical opt-in guard (`if reviewed_sha is not None:` — omitted sha falls through toward a push).
  - **GREEN** against the shipped hard refusal (`if reviewed_sha is None: raise`).
- `test_malformed_reviewed_sha_is_refused` — a non-40-hex sha cannot be a commit; refuse before pushing.
- `test_reviewed_sha_not_matching_base_is_refused` — valid hex but != base head means the branch moved between review and delivery; the stamp would name a commit QA never saw. Refuse (provenance mismatch).

> Safety property of the design: these call the gate with a nonexistent `files`
> entry, so even against a *regressed* guard the call stops at a local file read
> and never reaches the live GitHub token — the PR #74 failure mode (a mock that
> failed open into a live write) cannot recur from these controls.

### `tests/test_membrane_controls.py` — `verify_red_green` must DISCRIMINATE

A membrane that says "ok" no matter what launders a bad finding. These run
`git apply` + pytest on throwaway trees (no network):

- `test_membrane_fails_a_never_red_test` — a test that passes on the unfixed tree is not a reproduction → `red_ok False`, `membrane_ok False`.
- `test_membrane_fails_a_no_op_fix` — a RED test whose fix does not resolve it → `green_ok False`, `membrane_ok False`.
- `test_membrane_passes_a_real_red_then_green` — positive control: genuine RED + resolving fix → `membrane_ok True`.
  - **RED** against a kernel that hardcodes `membrane_ok True` (or drops the `red_ok`/`green_ok` discriminators): the two negative controls see `membrane_ok True` and fail.
  - **GREEN** against the shipped `membrane_ok = red_ok AND apply_clean AND applied AND green_ok`.

## How CI runs them

`pyproject.toml` `testpaths` is extended to `["tests", "tools/qa-skill/tests"]`,
so the existing `test` job in `.github/workflows/ci.yml` collects these with
**no workflow change**. `tools/qa-skill/tests/` is deliberately **not** a Python
package (no `__init__.py`): the prospector suite's `tests/` is already a package
named `tests`, and a second `tests` package collides under pytest's default
import mode. The two test basenames here are globally unique, so the default
mode collects them cleanly. Verified: 648 collected, 645 passed / 1 skipped
(moto, dev-only) / 2 xfailed (pre-existing, unrelated), zero regressions.

## Publish = deploy (the discipline, named honestly)

After a change here is merged, the QA seat publishes the merged bytes to the
platform catalog via `host.skills.edit(name, path, content=<merged bytes>)` +
publish. That call takes the file content as a string argument, so the publish
is a **byte-for-byte copy**, never a transcription — drift can only come from a
deliberate local edit that skips this PR path.

The honest tiers (for `METHOD.md`):
- *Changes to QA's procedure are reviewed* → **mechanism** (main is gated; a `qa/*` PR is the only path into this source).
- *The published copy matches the source* → **discipline** (byte-copy publish).
- *A drifted publish is caught before it misleads* → **the stamp** (next PR: a per-file `SKILL`/`kernel` hash in the provenance block, warn-loud on DRIFT). It graduates to mechanism when the delivery-path CI gate re-runs against this source — which needs injectable transport first (`deliver_qa_findings_pr` currently hardcodes its transport; a CI job that monkeypatches around a live token is the PR #74 incident with no human watching).

Order for the remaining work: **this PR** (source + network-free membrane
controls) → the stamp → injectable transport → delivery-path guards in CI.
