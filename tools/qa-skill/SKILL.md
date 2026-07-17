---
name: prospector-branch-qa
description: Fetch and set up an unmerged Prospector branch for cold-read QA review. Pulls the authoritative code from the GitHub repo dickienaut/prospector via the authenticated tarball API (never the local working folder, never trusting the state-of-project doc), unpacks it, and reports the tree so the suite can be run. Use at the start of any Prospector QA review of a feature branch, or to confirm shipped work against the actual code of record.
---

# Prospector Branch QA

Sets up a Prospector feature branch for cold-read QA review. The authoritative
code of record is the GitHub repo `dickienaut/prospector` — NOT the local
`/Users/lyledickie/prospector` working folder, and NOT the state-of-project
doc (which lags the code per the reduced-doc-cadence convention).

## Workflow

1. **Fetch the branch.** Call `fetch_prospector_branch("<branch>")` (default
   branch `main`). It uses the injected `GITHUB_TOKEN` to pull
   `/repos/dickienaut/prospector/tarball/<branch>`, unpacks it into the
   workspace, and returns `{"dest": ..., "branch": ..., "commit_sha": ...,
   "n_files": ..., "test_files": [...], "has_pyproject": bool}`. The `dest` is
   the unpacked repo root — cd there to run anything. **`commit_sha` is the
   exact 40-hex commit whose bytes you reviewed** — carry it into every finding
   via `provenance_stamp(fetch_result)`, which renders a "reviewed @ commit"
   block for the PR body. This turns "go to the primary source" from a promise
   into a verifiable artifact: the human and the implementer can confirm which
   version QA actually read. `deliver_qa_findings_pr` stamps it automatically.

2. **Stand up the env — read the spec, don't copy it.** Python per the repo's
   `pyproject.toml` `requires-python` (>=3.12 at time of writing, but READ it —
   don't trust this number). Install deps from `pyproject.toml`: the repo uses
   uv (`uv.lock` present), so `uv sync` for the core, and `uv sync --extra
   dashboard` for streamlit — which is an OPTIONAL extra, needed for the
   AppTest-based dashboard tests (`streamlit.testing.v1.AppTest`) and easy to
   miss. Do NOT hardcode the Python version or dep list into this skill or a
   review note — that's artifact state, and it rots (this exact line already
   drifted once: pip → the dashboard extra). It's the doc-drift-with-teeth
   class aimed at the skill itself; point at `pyproject.toml`, the source of
   truth. (Sandbox-practical fallback if uv isn't available: a dedicated conda
   env + `pip install streamlit` installs the same declared set.)

3. **Baseline the suite.** Run `pytest` from the repo root. The tests assume
   repo root as CWD — satisfy that to get a clean baseline, but do NOT mistake
   "I made it pass by cd-ing to root" for "the CWD assumption is acceptable."
   The hidden-CWD dependency is itself a standing finding (N5's class); satisfy
   it to baseline AND note it as a finding — conflating the two is the
   class-4 (test-passes-for-the-wrong-reason) trap. Record the
   pass/skip/xfail counts as the RED-against-live baseline.

4. **Review, then author tests RED/GREEN.** Hunt fixture-validated assumptions,
   especially on the fault/alarm layer. Each regression test is authored RED
   against live code / GREEN against a reference fix and asserts BEHAVIOUR, not
   a specific implementation. Reference fixes ship as a single `git apply`-clean
   unified diff (per-file `diff -u`, `a/`/`b/` labels, source files only),
   verified with `git apply --check` on a pristine checkout and a green suite.

5. **REQUIRED membrane: prove RED-then-GREEN as a script, not a claim.**
   Before delivering, run
   `verify_red_green(repo_root, test_paths, diff_path)`. It runs your RED tests
   against the pristine tree (must FAIL — the bug is real), applies the
   reference `.diff` to a throwaway copy, and re-runs (must PASS — the fix
   resolves it), reporting `membrane_ok`. This is the generate-and-check
   asymmetry pointed at QA's OWN output: a finding whose RED test is
   green-for-the-wrong-reason is meta-bug #4 (a test that passes for the wrong
   reason) landing inside the QA seat, and this is the mechanism that catches
   it. `membrane_ok` is verified to DISCRIMINATE — a no-op fix fails the GREEN
   half, a never-RED test fails the RED half — so a green result means
   something. It uses `--runxfail` so a shipped `xfail(strict=True)` marker
   reports its underlying result; it neutralises host gitconfig so `git apply`
   works in any sandbox. Do not hand a finding to the user until `membrane_ok`
   is True (or, for a decision-dependent finding with no committed fix, until
   the RED half alone is confirmed and the finding is shipped as a standing
   `xfail(strict=True)` contract).

6. **REQUIRED sign-off: exercise the changed path against a RECORDED-REAL
   fixture, not only the synthetic ones.** This is not optional and not
   instinct — a green suite over synthetic fixtures is the project's *signature*
   false-pass (the green-on-synthetic class: H1, H4, P1, 9e-ENR, R1, the exFAT
   backup case). QA's distinguishing power is that it can RUN the code against
   real data; using it is the step that catches the exact bugs QA exists to
   catch. Before signing off any finding or fix, drive the affected code over a
   recorded-real fixture (source-URL + retrieval-date, e.g. the real SPDR
   holdings file — not a hand-built happy-path frame) and confirm the behaviour
   there. If no recorded-real fixture exists for the path, that absence is
   itself a finding.

## Deliver as a PR (the GitHub bridge)

Once tests + reference fix are verified, deliver the finding-set to
`dickienaut/prospector` as a PR — the bridge that lets the user review on
mobile and hand off to their implementer seat without couriering files.

**Composition is Option 2 (QA proposes, implementer applies).** The QA PR
carries the RED-first tests + the reference fix **as a `.diff` file** + the
per-finding records — NOT the applied source change. This preserves the
independent read on every fix: QA finds/reproduces/tests, the implementer
(Claude Code) re-derives the patch against the code before landing it. QA
**never merges** and **never pushes to `main`** or a base branch — only to a
`qa/*` review branch. (The `GITHUB_TOKEN` is the user's own account with push
rights, so this restraint is policy, not a capability limit — the helper
enforces the `qa/*` rule and has no merge call.)

**The xfail-strict handoff (so the gate never goes red).** Ship each RED test
wrapped in `@pytest.mark.xfail(strict=True, reason=...)`. On the branch the
test xfails, so the findings PR is **green in the gate**. The moment the
implementer applies the `.diff`, the test flips to a loud **XPASS(strict)
failure** naming the finding — the mechanical signal the fix worked; the
implementer then removes the xfail marker in the same PR so the test becomes a
real green guard. This is the N9/E2 deferred-work pattern pointed at the
QA->Code seam. A genuinely decision-dependent finding (no committed fix design)
stays `xfail(strict=True)` as a behavioural contract.

**Call.** Stage the files (tests, the `.diff`, records, any README) into the
workspace or `/tmp`, then:

    deliver_qa_findings_pr(
        head_branch="qa/<slug>",              # MUST start with qa/
        base_branch="<feature-branch>",       # the branch of record you reviewed
        base_sha=fr["commit_sha"],             # fr = fetch_prospector_branch(...)
        reviewed_sha=fr["commit_sha"],         # REQUIRED: the commit you fetched+read+tested;
                                               # raises if omitted or != base_sha (rule #3 gate)
        files={"tests/test_x.py": "/tmp/.../test_x.py",
               "docs/notes/fixes.diff": "/tmp/fixes.diff",
               "docs/bugs/YYYY-MM-DD-<slug>.md": "/tmp/.../record.md"},
        title="QA findings: ...", body="<markdown PR body>",
        labels=["qa-findings"])
    # -> {pr_number, pr_url, branch, commit, ...}

Confirm the returned `base_sha` is the head you actually tested against, and
that the `.diff` `git apply --check`s clean against it, before handing the PR
to the user.

**Delivery gate (mechanised, not eyeballed).** `deliver_qa_findings_pr` runs
every `*.diff`/`*.patch` in `files` through `check_diff_hygiene()` and
**raises before any push** if a patch is polluted — recursive-diff noise
(`__pycache__`, `.pyc`, binary hunks) or non-`a/`/`b/` labels, the exact v1
failure that shipped an un-applyable diff.

**Pass `reviewed_sha=<the commit_sha you fetched+tested>`.** Do this on every
real delivery. The call prepends a QA-provenance stamp to the PR body
automatically — but the stamp's SHA is the branch head resolved *at delivery
time*, which is NOT necessarily the commit you reviewed. Passing `reviewed_sha`
makes the call **RAISE (zero writes) if the branch moved** between review and
delivery, so it can never stamp a commit QA never saw. Without it you get
presence-only provenance (`provenance_enforced=False` in the return) — a stamp
whose truth is unchecked, which is the doc-drift class wearing a QA badge. The
canonical flow: `fr = fetch_prospector_branch(branch)` → review/test against
`fr["dest"]` → `deliver_qa_findings_pr(..., base_sha=fr["commit_sha"],
reviewed_sha=fr["commit_sha"])`. You can also run `check_diff_hygiene(path)`
directly while composing the patch.

**Single source of truth.** Author findings/records/tests straight into the PR
branch — not into the local `dev` checkout. Local writes are the pre-bridge
path and create duplicates; the PR is what reaches the user's phone.

## Notes

- **QA proposes, never adjudicates — the more capable the seat, the more it
  stays in its lane.** QA's authority is verification against ground truth:
  it authors findings, tests, and reference patches. It does NOT make design
  or CONTRACT calls. A finding that turns on a design decision goes to the
  design thread as a question, wrapped as a behavioural `xfail(strict=True)`
  contract — never resolved unilaterally inside a patch. (The xfail-strict
  handoff below is the mechanism; this is the principle above it, written down
  so a future session with a strong urge to "just fix the design too" has the
  wall in front of it.)
- To confirm a prior fix landed, verify it in the fetched code, never in the
  state-of-project doc.
- `tests/` is a package with an empty `__init__.py`; no test imports a sibling
  test module — duplicate the small harness, don't `from test_runner import`.
